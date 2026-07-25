# HKI 7 Cloud

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
- **Parental controls** — hide certain views or rooms from certain people. This
  is UX-level hiding for a friendlier dashboard, **not** a Home Assistant
  security boundary.

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
| `hki7/dashboard/publish` | admin | Create/update a shared dashboard. |
| `hki7/dashboard/unpublish` | admin | Remove a shared dashboard. |
| `hki7/dashboard/list` | any | Dashboards visible to the caller (metadata). |
| `hki7/dashboard/get` | any | Fetch a dashboard payload the caller may see. |
| `hki7/policy/set` | admin | Set a user's hidden views/rooms. |
| `hki7/policy/get` | any | The **caller's own** policy (never anyone else's). |
| `hki7/policy/list` | admin | Every stored policy, for the admin editor. |

A later phase adds `hki7/config/*` for in-app family setup.

## Data storage

All data is kept in a single Home Assistant storage document
(`.storage/hki7_cloud`). Nothing leaves your Home Assistant instance.

## License

[Mozilla Public License 2.0](LICENSE) — matching the HKI 7 app's open-core model.
