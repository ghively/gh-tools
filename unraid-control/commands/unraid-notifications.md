---
description: Review and triage Unraid notifications (unread alerts/warnings)
argument-hint: (optional) "archive-all" to clear everything after reviewing
---

# Unraid notifications triage

1. `unraid_notifications(type="UNREAD")` — list unread notifications with the
   overview counts (info/warning/alert/total).
2. Present `ALERT` importance ones first, in full (title + description) —
   these are the ones most likely to need action. Then `WARNING`, then a
   count of `INFO`.
3. For anything that looks like a known/benign one-time notice (e.g. a driver
   install reminder), say so plainly but don't auto-dismiss it without being
   asked.

## Archiving

`unraid_notifications_archive_all` (optionally filtered by `importance`) is
non-destructive — archived notifications remain visible/deletable, just out
of the unread list. Reasonable to run without extra confirmation once the
user has reviewed the contents with you, or immediately if `$ARGUMENTS`
contains "archive-all". Report the resulting unread/archive counts.

## Deleting

`unraid_notification_delete` (one) / `unraid_notifications_delete_archived`
(all archived) are **permanent** — only do this if the user explicitly asks,
and pass `confirm=True`.

## Creating a test/custom notification

`unraid_notification_create(title, subject, description, importance)` — note
in the response whether `id_corrected` is `true`; if so the id you got back
from the create call was wrong and the tool already resolved the real one for
you (a known server-side quirk, see `references/conventions.md`) — use the
returned `id` field, not `raw_id`, for any follow-up archive/delete call.
