"""Reading, validating and editing the list of sites (sites.txt).

Editing functions only touch the lines they need to, so comments and blank
lines in sites.txt are preserved. Writes are atomic and protected by a lock.
"""

import os
import re
import sys
import threading
from pathlib import Path
from urllib.parse import urlparse

_lock = threading.Lock()


def normalize_url(url):
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    return url.rstrip("/")


def validate_url(raw):
    """Return the normalized URL or raise ValueError with a readable message."""
    raw = raw.strip()
    if not raw:
        raise ValueError("Please enter a URL.")
    if len(raw) > 2048 or re.search(r"\s", raw):
        raise ValueError("Invalid URL (spaces or too long).")
    if "://" in raw and not raw.lower().startswith(("http://", "https://")):
        raise ValueError("Only http:// and https:// URLs are allowed.")
    url = normalize_url(raw)
    try:
        parsed = urlparse(url)
        parsed.port  # raises ValueError if the port is invalid
    except ValueError:
        raise ValueError(f"Invalid URL: {raw}") from None
    if not parsed.hostname:
        raise ValueError(f"Invalid URL: {raw}")
    return url


# ---------- file helpers ----------

def _read_lines(path):
    p = Path(path)
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


def _entry(line):
    """Normalized URL of a line, or None for blank/comment lines."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    return normalize_url(line)


def _write_lines(path, lines):
    p = Path(path)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text("".join(l + "\n" for l in lines), encoding="utf-8")
    os.replace(tmp, p)


def _dedupe(urls):
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


# ---------- reading ----------

def read_sites(file_path):
    """Sites in the file (normalized, de-duplicated). Empty list if no file."""
    return _dedupe(e for e in map(_entry, _read_lines(file_path)) if e)


def load_sites(cli_sites, file_path):
    """Command line sites win over the sites file (used by the CLI)."""
    if cli_sites:
        return _dedupe(normalize_url(s) for s in cli_sites)
    if not Path(file_path).exists():
        sys.exit(f"Sites file '{file_path}' not found. Create it with one URL per line.")
    return read_sites(file_path)


# ---------- editing ----------

def add_site(path, raw):
    url = validate_url(raw)
    with _lock:
        lines = _read_lines(path)
        if url in {_entry(l) for l in lines}:
            raise ValueError("This site is already in the list.")
        _write_lines(path, lines + [url])
    return url


def update_site(path, old, raw):
    """Replace `old` by `raw`. Returns the new normalized URL."""
    new = validate_url(raw)
    old = normalize_url(old)
    with _lock:
        lines = _read_lines(path)
        idx = [i for i, l in enumerate(lines) if _entry(l) == old]
        if not idx:
            raise ValueError("Site not found in the sites file.")
        if new != old and new in {_entry(l) for l in lines}:
            raise ValueError("This site is already in the list.")
        lines[idx[0]] = new
        for i in reversed(idx[1:]):     # drop accidental duplicates of the old line
            del lines[i]
        _write_lines(path, lines)
    return new


def remove_site(path, url):
    """Remove a site from the file. Returns True if something was removed."""
    url = normalize_url(url)
    with _lock:
        lines = _read_lines(path)
        kept = [l for l in lines if _entry(l) != url]
        if len(kept) == len(lines):
            return False
        _write_lines(path, kept)
    return True
