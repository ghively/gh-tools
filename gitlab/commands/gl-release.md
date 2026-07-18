---
description: Cut a GitLab release — tag, release notes, and asset links
argument-hint: <project> <version> [ref]
---

Cut a release for **$ARGUMENTS** (project, version/tag, optional ref) using the gitlab MCP tools.

1. Read `references/cicd.md` (Releases section) if unsure of the shape.
2. Establish state: `get_project(project)` for the default branch; `tags(project, action="list")`
   to see existing tags; `list_merge_requests(project, params={"state":"merged","target_branch":<default>})`
   or `commits(project, action="list")` since the last tag to draft notes.
3. Draft release notes from the merged MRs / commits since the previous release — group by
   type (features, fixes, chores), link MRs/issues by `!iid`/`#iid`.
4. Show the user the proposed tag name, ref, and notes. Get explicit approval.
5. Create it: `releases(project, action="create", params={"tag_name": <version>, "ref": <ref>,
   "name": <version>, "description": <notes>, "milestones": [...], "assets": {"links": [...]}},
   confirm=true)`. If the tag doesn't exist yet, `ref` creates it; otherwise omit `ref`.
6. Add any binary/asset links with `releases(..., action="link_create", ...)`.
7. Confirm with `releases(project, action="get", tag_name=<version>)` and report the release URL.

Never create the tag/release without the user approving the exact version + notes.
