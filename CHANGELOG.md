# Changelog

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

