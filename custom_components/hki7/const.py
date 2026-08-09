"""Constants for the HKI 7 Cloud integration."""

import json
from pathlib import Path

DOMAIN = "hki7"

# Read straight from manifest.json rather than duplicating the version string here, so a release
# can never bump one and forget the other — whatever HACS/HA core report is what hki7/whoami reports.
VERSION: str = json.loads((Path(__file__).parent / "manifest.json").read_text(encoding="utf-8"))["version"]

# One HA Store file holds every HKI 7 record (backups, and — in later phases —
# shared dashboards, parental-control policies, and family config).
STORAGE_KEY = "hki7_cloud"
STORAGE_VERSION = 1

# Per-user rolling backup cap, matching the app's Google Drive behaviour.
MAX_BACKUPS = 14

# Hard ceiling on a single backup payload (2 MB) so a malformed client can't
# bloat HA's .storage. A real dashboard export is a few tens of KB.
MAX_PAYLOAD_BYTES = 2 * 1024 * 1024

# Per-user cap on remembered app installs. A reinstall gives the app a new install id, so
# without a cap this section would grow forever in a household that reinstalls often.
MAX_DEVICES_PER_USER = 12

# A device re-reports on every app foreground. When nothing about it has changed, rewriting
# .storage just to move its "last seen" clock is pure disk churn, so an unchanged report is
# only persisted once this many seconds have passed.
DEVICE_REPORT_MIN_INTERVAL_SECONDS = 3600
