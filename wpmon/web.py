"""Small web interface: shows the database, edits sites.txt, runs checks.

Standard library only. Every change goes through a POST form protected by a
per-run token, and (when bound to localhost) the Host header is verified.
There is NO login: keep it on localhost, or put it behind an authenticating proxy.
"""

import hmac
import html
import secrets
import threading
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from . import storage
from .runner import BackgroundCheck
from .sites import add_site, read_sites, remove_site, update_site

REFRESH_IDLE_MS = 60_000
REFRESH_RUNNING_MS = 5_000
MAX_BODY = 8 * 1024
LOOPBACK_HOSTS = ("127.0.0.1", "localhost")

CSS = """
:root { --bg:#f6f7f9; --card:#fff; --text:#1c2430; --muted:#6b7686; --line:#e3e7ed; --accent:#2563eb;
        --ok:#1a7f4b; --ok-bg:#e3f4ea; --bad:#b42318; --bad-bg:#fde8e6;
        --warn:#9a6700; --warn-bg:#fff3cd; --muted-bg:#eceff3; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#12161c; --card:#1b212a; --text:#e6eaf0; --muted:#8b96a5; --line:#2a323d; --accent:#3b82f6;
          --ok:#5fd394; --ok-bg:#12301f; --bad:#ff8a80; --bad-bg:#3a1a17;
          --warn:#f5c451; --warn-bg:#382d0f; --muted-bg:#262d37; }
}
* { box-sizing: border-box; }
body { margin:0; padding:24px 16px; background:var(--bg); color:var(--text);
       font:15px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
main { max-width:1040px; margin:0 auto; }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; margin-bottom:16px; }
header.card { padding:20px 24px; }
.top { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; flex-wrap:wrap; }
.label { color:var(--muted); font-size:13px; text-transform:uppercase; letter-spacing:.05em; }
.version { font-size:40px; font-weight:700; line-height:1.1; }
.meta { color:var(--muted); font-size:13px; margin-top:6px; }
.meta.err { color:var(--bad); }
.counts { display:flex; gap:8px; flex-wrap:wrap; margin-top:12px; }
.flash { padding:10px 16px; border-radius:10px; margin-bottom:12px; font-size:14px; }
.flash.ok { color:var(--ok); background:var(--ok-bg); }
.flash.err { color:var(--bad); background:var(--bad-bg); }
form.add { display:flex; gap:8px; padding:14px 16px; }
form.add input { flex:1; }
input[type=text] { font:inherit; padding:6px 10px; border-radius:8px; border:1px solid var(--line);
                   background:var(--bg); color:var(--text); min-width:0; }
.btn { font:inherit; font-size:13px; padding:5px 12px; border-radius:8px; border:1px solid var(--line);
       background:var(--card); color:var(--text); cursor:pointer; display:inline-block; }
.btn.primary { background:var(--accent); border-color:var(--accent); color:#fff; }
.btn.danger { color:var(--bad); }
.btn:disabled { opacity:.6; cursor:default; }
.table-wrap { overflow-x:auto; }
table { width:100%; border-collapse:collapse; }
th, td { text-align:left; padding:10px 16px; border-bottom:1px solid var(--line); white-space:nowrap; vertical-align:top; }
th { color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.05em; }
tr:last-child td { border-bottom:none; }
a { color:inherit; }
.badge { display:inline-block; padding:2px 10px; border-radius:999px; font-size:13px; font-weight:600; }
.ok { color:var(--ok); background:var(--ok-bg); }
.bad { color:var(--bad); background:var(--bad-bg); }
.warn { color:var(--warn); background:var(--warn-bg); }
.muted { color:var(--muted); background:var(--muted-bg); }
.actions { display:flex; gap:8px; align-items:flex-start; }
.actions form { margin:0; }
details.edit summary { list-style:none; }
details.edit summary::-webkit-details-marker { display:none; }
details.edit form { display:flex; gap:6px; margin-top:6px; }
details.edit input { min-width:300px; }
.empty { padding:32px; text-align:center; color:var(--muted); }
"""

SCRIPT = """
setTimeout(function tick() {
  var typing = [].some.call(document.querySelectorAll('input[type=text]'),
                             function (i) { return i.value !== i.defaultValue; });
  var busy = document.querySelector('details[open]') || typing ||
             document.activeElement.tagName === 'INPUT';
  if (busy) { setTimeout(tick, __MS__); } else { location.reload(); }
}, __MS__);
"""


# ---------------------------------------------------------------- data

def _status_class(status):
    if status in ("UP-TO-DATE", "AHEAD"):
        return "ok"
    if status.startswith("OUTDATED") or status == "ERROR":
        return "bad"
    if status == "NOT CHECKED":
        return "muted"
    return "warn"  # UNKNOWN


def _sort_key(e):
    rank = {"bad": 0, "warn": 1, "muted": 2, "ok": 3}[_status_class(e["status"])]
    return (rank, e["site"])


def build_entries(conn, sites_file):
    """Sites in sites.txt (with their last status, if any) + DB rows no longer in the file."""
    rows = {r["site"]: r for r in storage.get_all(conn)}
    entries = []
    for site in read_sites(sites_file):
        r = rows.pop(site, None)
        if r:
            entries.append({"site": site, "in_file": True, "version": r["version"],
                            "status": r["status"], "last_checked": r["last_checked"],
                            "detail": r["detail"] or ""})
        else:
            entries.append({"site": site, "in_file": True, "version": "", "status": "NOT CHECKED",
                            "last_checked": "-", "detail": "Run the checks to get a status"})
    for site, r in rows.items():
        entries.append({"site": site, "in_file": False, "version": r["version"],
                        "status": r["status"], "last_checked": r["last_checked"],
                        "detail": ((r["detail"] or "") + " (not in sites file)").strip()})
    return entries


# ---------------------------------------------------------------- rendering

def _row(e, csrf):
    esc = html.escape
    site = esc(e["site"])
    if e["in_file"]:
        edit = f"""<details class="edit"><summary class="btn">Edit</summary>
<form method="post" action="/sites/edit">{csrf}<input type="hidden" name="old" value="{site}">
<input type="text" name="url" value="{site}" required maxlength="2048">
<button class="btn primary">Save</button></form></details>"""
        del_label = "Delete"
    else:
        edit, del_label = "", "Remove"
    delete = f"""<form method="post" action="/sites/delete" onsubmit="return confirm('Delete this site?')">{csrf}
<input type="hidden" name="url" value="{site}"><button class="btn danger">{del_label}</button></form>"""
    return (
        "<tr>"
        f'<td><a href="{site}" target="_blank" rel="noopener noreferrer">{site}</a></td>'
        f'<td>{esc(e["version"]) or "-"}</td>'
        f'<td><span class="badge {_status_class(e["status"])}">{esc(e["status"])}</span></td>'
        f'<td>{esc(e["last_checked"])}</td>'
        f'<td>{esc(e["detail"])}</td>'
        f'<td><div class="actions">{edit}{delete}</div></td>'
        "</tr>"
    )


def render_page(entries, last_check, state, token, flashes):
    esc = html.escape
    csrf = f'<input type="hidden" name="csrf" value="{esc(token)}">'
    entries = sorted(entries, key=_sort_key)

    latest = esc(last_check["latest"]) if last_check else "-"
    checked = esc(last_check["last_checked"]) if last_check else "never"

    counts = {"ok": 0, "bad": 0, "warn": 0, "muted": 0}
    for e in entries:
        counts[_status_class(e["status"])] += 1

    if state["running"]:
        status_line = '<div class="meta">Check in progress...</div>'
        button = '<button class="btn primary" disabled>Check running...</button>'
    else:
        status_line = ""
        if state["last_error"]:
            status_line = f'<div class="meta err">Last manual check failed: {esc(state["last_error"])}</div>'
        button = '<button class="btn primary">Run checks now</button>'

    pending = f'<span class="badge muted">{counts["muted"]} not checked</span>' if counts["muted"] else ""
    flash_html = "".join(f'<div class="flash {k}">{esc(t)}</div>' for k, t in flashes)

    if entries:
        rows = "".join(_row(e, csrf) for e in entries)
        table = ('<div class="table-wrap"><table><thead><tr><th>Site</th><th>Version</th><th>Status</th>'
                 '<th>Last checked (UTC)</th><th>Detail</th><th>Actions</th></tr></thead>'
                 f"<tbody>{rows}</tbody></table></div>")
    else:
        table = '<div class="empty">No sites yet. Add one above.</div>'

    ms = REFRESH_RUNNING_MS if state["running"] else REFRESH_IDLE_MS
    script = SCRIPT.replace("__MS__", str(ms))

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WordPress monitor</title>
<style>{CSS}</style>
</head><body><main>
<header class="card">
  <div class="top">
    <div>
      <div class="label">Latest WordPress release</div>
      <div class="version">{latest}</div>
      <div class="meta">Last check: {checked} UTC</div>
      {status_line}
    </div>
    <form method="post" action="/check">{csrf}{button}</form>
  </div>
  <div class="counts">
    <span class="badge ok">{counts["ok"]} up to date</span>
    <span class="badge bad">{counts["bad"]} outdated / error</span>
    <span class="badge warn">{counts["warn"]} unknown</span>
    {pending}
  </div>
</header>
{flash_html}
<div class="card">
  <form class="add" method="post" action="/sites/add">{csrf}
    <input type="text" name="url" placeholder="https://example.com" required maxlength="2048">
    <button class="btn primary">Add site</button>
  </form>
</div>
<div class="card">{table}</div>
</main><script>{script}</script></body></html>"""


# ---------------------------------------------------------------- server

class App:
    """State shared by all requests."""

    def __init__(self, db_path, sites_file, allowed_hosts):
        self.db_path = db_path
        self.sites_file = sites_file
        self.allowed_hosts = allowed_hosts       # None = don't check the Host header
        self.token = secrets.token_urlsafe(32)
        self.runner = BackgroundCheck(db_path, sites_file)
        self._flashes = []
        self._lock = threading.Lock()

    def flash(self, kind, text):
        with self._lock:
            self._flashes.append((kind, text))

    def pop_flashes(self):
        with self._lock:
            out, self._flashes = self._flashes, []
        return out


class Handler(BaseHTTPRequestHandler):
    @property
    def app(self):
        return self.server.app

    # ----- helpers
    def _host_ok(self):
        allowed = self.app.allowed_hosts
        if allowed is not None and self.headers.get("Host") not in allowed:
            self.send_error(403, "Forbidden host")
            return False
        return True

    def _redirect(self):
        self.send_response(303)
        self.send_header("Location", "/")
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ----- GET
    def do_GET(self):
        if not self._host_ok():
            return
        if self.path.split("?")[0] not in ("/", "/index.html"):
            self.send_error(404)
            return
        app = self.app
        with closing(storage.connect(app.db_path)) as conn:
            entries = build_entries(conn, app.sites_file)
            last = storage.get_last_check(conn)
        page = render_page(entries, last, app.runner.snapshot(), app.token, app.pop_flashes())
        data = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    # ----- POST
    def do_POST(self):
        if not self._host_ok():
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self.send_error(400)
            return
        if length > MAX_BODY:
            self.send_error(413)
            return
        form = parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
        field = lambda k: (form.get(k) or [""])[0].strip()

        if not hmac.compare_digest(field("csrf"), self.app.token):
            self.send_error(403, "Invalid form token. Reload the page and try again.")
            return

        actions = {
            "/sites/add": self._add,
            "/sites/edit": self._edit,
            "/sites/delete": self._delete,
            "/check": self._check,
        }
        action = actions.get(self.path.split("?")[0])
        if action is None:
            self.send_error(404)
            return
        try:
            action(field)
        except ValueError as e:
            self.app.flash("err", str(e))
        except OSError as e:
            self.app.flash("err", f"File error: {e}")
        self._redirect()

    def _add(self, field):
        url = add_site(self.app.sites_file, field("url"))
        self.app.flash("ok", f"Added {url}. Run the checks to get its status.")

    def _edit(self, field):
        old = field("old")
        new = update_site(self.app.sites_file, old, field("url"))
        if new != old:
            with closing(storage.connect(self.app.db_path)) as conn:
                storage.delete_site(conn, old)      # the old status no longer applies
            self.app.flash("ok", f"Updated to {new}. Run the checks to get its status.")
        else:
            self.app.flash("ok", "No change.")

    def _delete(self, field):
        url = field("url")
        in_file = remove_site(self.app.sites_file, url)
        with closing(storage.connect(self.app.db_path)) as conn:
            in_db = storage.delete_site(conn, url) > 0
        if in_file or in_db:
            self.app.flash("ok", f"Removed {url}.")
        else:
            self.app.flash("err", "Site not found.")

    def _check(self, field):
        if not read_sites(self.app.sites_file):
            self.app.flash("err", "No sites to check. Add one first.")
        elif self.app.runner.start():
            self.app.flash("ok", "Check started. The page refreshes while it runs.")
        else:
            self.app.flash("err", "A check is already running.")


def create_server(db_path, sites_file, host="127.0.0.1", port=8000):
    server = ThreadingHTTPServer((host, port), Handler)
    real_port = server.server_address[1]
    allowed = None
    if host in LOOPBACK_HOSTS:
        allowed = {f"127.0.0.1:{real_port}", f"localhost:{real_port}"}
    server.app = App(db_path, sites_file, allowed)
    return server


def serve(db_path, sites_file, host="127.0.0.1", port=8000):
    server = create_server(db_path, sites_file, host, port)
    print(f"Serving on http://{host}:{port}  (Ctrl+C to stop)")
    if host not in LOOPBACK_HOSTS:
        print("WARNING: there is no login. Anyone who can reach this address can edit "
              "the sites list and run checks.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
