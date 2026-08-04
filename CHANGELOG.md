# Changelog

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

