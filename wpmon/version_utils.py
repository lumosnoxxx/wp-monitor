"""Version parsing and comparison. Pure functions, no network."""


def vtuple(v):
    """'6.4' -> (6, 4, 0) so that 6.4 == 6.4.0."""
    parts = [int(p) for p in v.split(".")]
    return tuple((parts + [0, 0, 0])[:3])


def compare(current, latest):
    """Return a status label for `current` versus `latest`."""
    c, l = vtuple(current), vtuple(latest)
    if c == l:
        return "UP-TO-DATE"
    if c > l:
        return "AHEAD"                  # dev/beta build
    if c[:2] == l[:2]:
        return "OUTDATED (patch)"       # same branch -> usually missing security fixes
    return "OUTDATED (major/minor)"
