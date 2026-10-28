# WP Monitor

A lightweight, self-hosted tool for monitoring WordPress core versions across multiple websites.

## What problem does it solve?

Keeping track of WordPress updates across many sites can be tedious. WP Monitor checks publicly available version information, compares detected versions with the latest WordPress release, and displays the results in one place.

**Note:** Version detection is best-effort. Some sites hide their version, and a reported version is not proof that a site is secure or vulnerable.

## Main components

- **Version detector** (`wpmon/detector.py`) — checks public metadata, RSS feeds, readme files, and OPML.
- **Checker and runner** (`wpmon/checker.py`, `wpmon/runner.py`) — compare versions and run checks concurrently.
- **Storage** (`wpmon/storage.py`) — saves site status and metadata in SQLite.
- **Web dashboard** (`wpmon/web.py`) — shows results and lets you manage sites and trigger checks.
- **CLI** (`main.py`) — runs checks and lists stored results from the terminal.

## Deployment

Requires Python 3 and network access to the monitored sites and the WordPress version API.

```bash
git clone https://github.com/lumosnoxxx/wp-monitor.git
cd wp-monitor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `sites.txt` file containing one website URL per line:

```text
https://example.com
https://another-site.com
```

Run a check:

```bash
python main.py check
```

Start the local dashboard:

```bash
python main.py serve
```

Open **http://127.0.0.1:8765** in your browser. You can also add sites from the dashboard's **Manage sites** page.

**Security:** The dashboard has no built-in login. Keep it bound to localhost (the default). If remote access is needed, use an authenticated reverse proxy and restrict network access. Do not expose it directly to the internet.
