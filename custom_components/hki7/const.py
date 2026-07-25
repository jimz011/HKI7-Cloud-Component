"""Constants for the HKI 7 Cloud integration."""

DOMAIN = "hki7"

# One HA Store file holds every HKI 7 record (backups, and — in later phases —
# shared dashboards, parental-control policies, and family config).
STORAGE_KEY = "hki7_cloud"
STORAGE_VERSION = 1

# Per-user rolling backup cap, matching the app's Google Drive behaviour.
MAX_BACKUPS = 14

# Hard ceiling on a single backup payload (2 MB) so a malformed client can't
# bloat HA's .storage. A real dashboard export is a few tens of KB.
MAX_PAYLOAD_BYTES = 2 * 1024 * 1024
