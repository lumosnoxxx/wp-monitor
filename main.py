#!/usr/bin/env python3
"""
WordPress core version monitor - command line entry point.

    python main.py check                       # check sites from sites.txt, update DB
    python main.py check https://a.com b.org   # check specific sites
    python main.py list                        # show last known status from the DB
    python main.py remove https://a.com        # delete a site from the DB
    python main.py serve                       # web page on http://127.0.0.1:8000
"""

import argparse
import sys
from contextlib import closing

from wpmon import config, report, storage, web
from wpmon.checker import has_problems
from wpmon.runner import run_check
from wpmon.sites import load_sites, normalize_url


def cmd_check(args):
    sites = load_sites(args.sites, args.file)
    if not sites:
        sys.exit("No sites to check.")
    try:
        results, latest = run_check(args.db, sites, args.workers)
    except RuntimeError as e:
        sys.exit(str(e))
    report.print_check_report(results, latest)
    sys.exit(1 if has_problems(results) else 0)


def cmd_list(args):
    with closing(storage.connect(args.db)) as conn:
        report.print_db_report(storage.get_all(conn))


def cmd_remove(args):
    with closing(storage.connect(args.db)) as conn:
        n = storage.delete_site(conn, normalize_url(args.site))
    print("Removed." if n else "Site not found in database.")


def cmd_serve(args):
    web.serve(args.db, args.file, args.host, args.port)


def build_parser():
    p = argparse.ArgumentParser(description="WordPress core version monitor.")
    p.add_argument("--db", default=config.DEFAULT_DB_FILE, help="SQLite database file")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("check", help="Check sites and update the database")
    c.add_argument("sites", nargs="*", help="Site URLs (overrides the sites file)")
    c.add_argument("-f", "--file", default=config.DEFAULT_SITES_FILE, help="File with one URL per line")
    c.add_argument("-w", "--workers", type=int, default=config.MAX_WORKERS, help="Parallel checks")
    c.set_defaults(func=cmd_check)

    l = sub.add_parser("list", help="Show the last known status of every site")
    l.set_defaults(func=cmd_list)

    r = sub.add_parser("remove", help="Remove a site from the database")
    r.add_argument("site")
    r.set_defaults(func=cmd_remove)

    w = sub.add_parser("serve", help="Serve the web interface")
    w.add_argument("-f", "--file", default=config.DEFAULT_SITES_FILE, help="Sites file edited by the web page")
    w.add_argument("--host", default="127.0.0.1", help="Bind address (default: local only)")
    w.add_argument("--port", type=int, default=8765)
    w.set_defaults(func=cmd_serve)
    return p


def main():
    argv = sys.argv[1:]
    # Backward compatible: no arguments at all means "check".
    if not argv:
        argv = ["check"]
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
