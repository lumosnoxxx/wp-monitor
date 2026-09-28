"""Central settings. Change values here, not in the other modules."""

USER_AGENT = "WPVersionMonitor/0.2 (self-hosted uptodate check)"
LATEST_API = "https://api.wordpress.org/core/version-check/1.7/"
TIMEOUT = 10            # seconds per HTTP request
MAX_WORKERS = 5         # sites checked in parallel

DEFAULT_SITES_FILE = "sites.txt"
DEFAULT_DB_FILE = "wp_monitor.db"
