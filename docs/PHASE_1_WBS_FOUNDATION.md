# Phase 1 WBS foundation

## Scope

This slice establishes `Project -> Schedule -> WBS node`. It intentionally does
not add activities, calendars or CPM yet. Those features will reference these
stable UUIDs in later Phase 1 migrations.

## Rules

- One Schedule belongs to one Project.
- WBS codes are unique inside a Schedule; codes and ordering may change without
  changing a node's UUID.
- A WBS parent must belong to the same Project and Schedule.
- The hierarchy is limited to six levels and cycles are rejected in PostgreSQL.
- Reordering is one atomic database function call so partial saves cannot leave
  the tree in an inconsistent state.
- All signed-in Project members may view WBS data. Existing management tiers may
  create, edit, archive and reorder it.
- Archive is soft-delete; referenced planning history is not cascaded away.

## Release gate

Apply `0002_phase1_wbs_foundation.sql` only after a fresh backup and successful
rehearsal on an isolated Supabase Free project. Merge the application branch only
after hierarchy, role/RLS and regression tests pass.
