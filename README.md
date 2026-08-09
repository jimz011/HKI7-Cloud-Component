# HKI 7 Cloud

<img width="1024" height="500" alt="play_feature_graphic_1024x500" src="https://github.com/user-attachments/assets/ef15a0ed-1b1a-4390-94f0-99c7380d6e67" />

A local companion backend for the [HKI 7](https://github.com/jimz011/android-hki7)
Home Assistant app. It stores app data **on your own Home Assistant instance**
and exposes it over Home Assistant's authenticated WebSocket API.

Because every request is authenticated by Home Assistant, the integration always
knows *which HA user* is calling. That is what makes the app's family features
possible without the app ever handling passwords or accounts itself:

- **HA-local backups** — back up your dashboard to your own HA instance, as an
  addition to (not a replacement for) the app's Google Drive backups.
- **Family dashboard sharing** — the admin builds one dashboard and shares it with
  specific family members (or everyone), instead of passing backup files between
  phones. Recipients import a copy into their own app.
- **Parental controls** — hide certain views or rooms from certain people and limit global search
  to selected Home Assistant domains or individual entities. This
  is UX-level hiding for a friendlier dashboard, **not** a Home Assistant
  security boundary.
- **Family devices** — each install records which HKI 7 version it runs, so the admin can see at a
  glance who is behind on updates. Nothing is added to Home Assistant's entity list; a device only
  ever reports itself, filed under the Home Assistant account it is signed in as.
- **Minimum app version** — the admin can require the household to be on a given HKI 7 version, and
  each app prompts anyone below it to update. Only a version some device already reports running can
  be required, so the requirement can never be one nobody is able to satisfy.

Everything is set up **from inside the HKI 7 app**. This integration is just the
wiring Home Assistant needs to store and serve that data.

## Installation

### HACS (recommended)

1. In HACS, add this repository as a **Custom repository** (category: *Integration*).
2. Install **HKI 7 Cloud**.
3. Restart Home Assistant.
4. Go to **Settings → Devices & Services → Add Integration → HKI 7 Cloud** and
   confirm. There is nothing to configure here.

### Manual

Copy `custom_components/hki7` into your Home Assistant `config/custom_components/`
directory and restart, then add the integration as above.

## Requirements

- Home Assistant 2024.1 or newer.
- The HKI 7 app, signed in to this Home Assistant instance.

## WebSocket API

All commands are namespaced `hki7/*` and require an authenticated connection.
Writes that affect other users (sharing, policies) require an **admin** user;
per-user reads are always filtered to the calling user server-side.

| Command | Access | Purpose |
| --- | --- | --- |
| `hki7/whoami` | any | Identify the calling HA user. |
| `hki7/backup/put` | any | Store the caller's UI backup blob. |
| `hki7/backup/list` | any | List the caller's backups (metadata only). |
| `hki7/backup/get` | any | Fetch one of the caller's backup payloads. |
| `hki7/users/list` | admin | List HA users for the "share with" picker. |
| `hki7/dashboard/publish` | admin | Create a shared dashboard, or update one owned by the caller. |
| `hki7/dashboard/unpublish` | admin | Remove a shared dashboard owned by the caller. |
| `hki7/dashboard/list` | any | Dashboards visible to the caller (metadata). |
| `hki7/dashboard/get` | any | Fetch a dashboard payload the caller may see. |
| `hki7/policy/set` | admin | Set a user's hidden views/rooms, app permissions, visible/invisible global-search domains or entities, and room-following settings. |
| `hki7/policy/get` | any | The **caller's own** policy (never anyone else's). |
| `hki7/policy/list` | admin | Every stored policy, for the admin editor. |
| `hki7/room_follow/roster` | any | The household's room-presence sensor ids, for the people-per-room counter. |
| `hki7/adaptive_lighting/list` | any | Each Adaptive Lighting profile's light membership, so non-admins get the same per-room controls. |
| `hki7/device/report` | any | Record the **calling device's** HKI 7 version; answers with the update it is being asked for. |
| `hki7/device/list` | admin | Every reported install in the household. |
| `hki7/device/forget` | admin | Drop one remembered install (a replaced or uninstalled phone). |
| `hki7/device/nudge` | admin | Ask one device to update, or clear that request. |
| `hki7/app_update/get` | any | The household's minimum HKI 7 version. |
| `hki7/app_update/set` | admin | Set or clear that minimum. |

Publishing or unpublishing fires the Home Assistant event `hki7_dashboard_updated`.
Foreground HKI 7 clients use it as an invalidation signal and then fetch only dashboards their
authenticated Home Assistant user may access; clients that were offline reconcile on app startup.

## Data storage

All data is kept in a single Home Assistant storage document
(`.storage/hki7_cloud`). Nothing leaves your Home Assistant instance.

## License

[Mozilla Public License 2.0](LICENSE) — matching the HKI 7 app's open-core model.
