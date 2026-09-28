"""Console output."""


def _table(headers, rows):
    widths = [max(len(str(x)) for x in col) + 2 for col in zip(headers, *rows)]
    line = lambda cells: "".join(f"{str(c):<{w}}" for c, w in zip(cells, widths))
    print(line(headers))
    print("-" * sum(widths))
    for r in rows:
        print(line(r))
    print()


def print_check_report(results, latest):
    print(f"\nLatest WordPress release: {latest}\n")
    _table(
        ["SITE", "VERSION", "STATUS", "DETAIL"],
        [(r["site"], r["version"] or "-", r["status"], r["detail"]) for r in results],
    )


def print_db_report(rows):
    if not rows:
        print("\nDatabase is empty. Run a check first.\n")
        return
    print()
    _table(
        ["SITE", "VERSION", "LATEST", "STATUS", "LAST CHECKED (UTC)"],
        [(r["site"], r["version"] or "-", r["latest"], r["status"], r["last_checked"]) for r in rows],
    )
