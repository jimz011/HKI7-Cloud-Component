# Changelog

## 0.7.0

- New `hki7/device/report`, so each HKI 7 install can record which app version it is running. Any authenticated user may call it, but only for themselves: the account a device is filed under is the authenticated caller, never anything the client sends. The record holds the app's own stable install id, the device name, app version and version code, the Android version and the model.
- New `hki7/device/list` (admin only) returns every reported install in the household — what the app's Settings › Family Sharing › Devices tab shows: who is running which HKI version, and who is behind.
- New `hki7/device/forget` (admin only) drops one remembered install, for a phone that has been replaced or had the app uninstalled. A device still in use simply reports itself again the next time its app opens.
- The app previously reported its version as a `mobile_app` diagnostic sensor, which only covered devices doing `mobile_app` telemetry at all — a phone with both Location and Notifications switched off was invisible. This path uses the WebSocket connection the app already holds, so it reaches every signed-in device and creates no entities in Home Assistant.
- Remembered installs are capped at 12 per user (a reinstall gets a new install id), every text field is length-capped before it reaches `.storage`, and an unchanged report is only written to disk once an hour, so reporting on every app foreground costs no disk churn.

## 0.6.2

- `hki7/whoami` now returns `version`, the installed component's own version string (read from `manifest.json`, so it can never drift out of sync with what HACS reports). Lets the app show which HKI 7 Cloud version is installed and warn when a feature needs a newer one, instead of only finding out after a save is silently rejected.

## 0.6.1

- `hki7/policy/set` now accepts `continue_after_launch` on a person's room-following settings: when `false`, `open_on_launch` is the only thing that person's following does — no prompts, no silent moves once the app is already open. Older app builds that never send it keep the previous always-on tracking behavior (defaults to `true`).

## 0.6.0

- Added per-user room following to `hki7/policy/set`, so an admin can configure the whole family from one place. Each person's policy carries the room-presence sensor tracking their phone (ESPresense and `mqtt_room` both publish the room name as the sensor's state), whether following is on, whether it opens that room when the app launches, whether moving rooms prompts to switch views, and how long a new room must hold before it counts as a move.
- `state_rooms` stores only overrides: the app matches a sensor state against the Home Assistant area names itself, so a household whose ESPresense rooms are named after its areas needs no mapping at all.
- Following can never be enabled without a sensor, and the dwell time is clamped to 0–600 seconds regardless of what a client sends.
- New `hki7/room_follow/roster` returns the household's tracked sensor ids to any authenticated user, which is what the app's people-per-room counter needs. It exposes no user ids and no other policy field, and every id it returns is an entity the caller can already read directly from Home Assistant.
- Room-following settings are backfilled for older stored records and preserved when an older app client updates some other permission.

## 0.5.5

- Ships the 0.5.3 and 0.5.4 work, which was committed but never released: HACS installs by release, so 0.5.2 remained the newest version anyone could get.
- Without those changes `hki7/policy/set` rejects the per-user Visible and Invisible lists, the stored hidden item IDs, and the re-import permission, which made the app's Parental Controls report that the policy could not be updated.
- No behavior changes of its own — update to this version to make those parental-control settings save.

## 0.5.4

- Added per-user Visible and Invisible global-search policies for complete Home Assistant domains and individual entities.
- Invisible selections take precedence over visible selections, while an empty Visible list keeps the unrestricted default.
- Search policy fields are backfilled for older stored records and preserved when older app clients update another permission.
- Persisted the existing hidden item IDs used by parental controls.

## 0.5.3

- Added the per-user permission for manually re-importing or clearing dashboard view data.

