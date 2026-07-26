# Projects, repository, merge requests, issues & the shared notes model

All paths relative to `/api/v4`. `:id` = numeric project id or URL-encoded path
(`group%2Fsub%2Fproj`). `iid` = project-internal id shown in the UI (use for issues/MRs).
Verified against docs.gitlab.com ~19.x. Everything here is **Free/CE** unless flagged EE.

## Projects
- CRUD/lifecycle: `GET/POST/PUT/DELETE /projects[/:id]`, `POST .../{archive,unarchive,restore}`,
  `PUT .../transfer?namespace=`, `GET .../transfer_locations`, `POST .../housekeeping?task=prune|eager`,
  `GET .../languages`, `POST /projects/user/:user_id` (admin create-for-user).
- Delete now: `DELETE /projects/:id?permanently_remove=true&full_path=<path>` (Free since 18.0).
- Create key attrs: `name`/`path`, `namespace_id`, `visibility`, `default_branch`,
  `initialize_with_readme`, `merge_method` (`merge|rebase_merge|ff`), `squash_option`,
  `only_allow_merge_if_pipeline_succeeds`, `only_allow_merge_if_all_discussions_are_resolved`,
  `remove_source_branch_after_merge`, `*_access_level` feature-visibility (`disabled|private|enabled`),
  `container_expiration_policy_attributes` (registry cleanup), `topics`, `import_url`.
- Fork: `POST /projects/:id/fork` (creates fork; poll `import_status`), `GET .../forks`,
  `POST/DELETE .../fork/:forked_from_id` (relationship). Star: `POST .../{star,unstar}`, `.../starrers`.
- Share with group: `POST /projects/:id/share {group_id, group_access, expires_at}` · `DELETE .../share/:group_id`.
- Import/export: `POST/GET .../export`, `GET .../export/download`, `POST /projects/import` (multipart),
  `/projects/remote-import`, `GET .../import` (status), granular `POST /projects/import-relation`.
- Stats: `GET /projects/:id?statistics=true` (repository_size, commit_count, storage, artifacts, packages...).

## Repository
- Tree/blobs: `GET .../repository/tree` (`path`, `ref`, `recursive`, keyset), `.../blobs/:sha[/raw]`,
  `.../archive[.tar.gz|.zip]`, `.../compare?from=&to=[&straight]`, `.../contributors`,
  `.../merge_base?refs[]=`, `GET/POST .../changelog`.
- **Files**: `/projects/:id/repository/files/:path_urlencoded` — `GET`(`?ref=`, base64 content),
  `HEAD` (metadata in headers), `GET .../raw`, `GET .../blame`, `POST`/`PUT`/`DELETE`
  (`branch`, `commit_message`, `content`; PUT accepts `last_commit_id` for conflict check).
- **Commits**: `GET/POST .../repository/commits` (create supports **multi-action**: an `actions[]`
  array of `{action: create|update|delete|move|chmod, file_path, content, previous_path,
  execute_filemode}`), `GET .../commits/:sha[/diff|/comments|/discussions|/refs|/statuses|/merge_requests|/signature]`,
  `POST .../commits/:sha/{cherry_pick,revert}`, `POST /projects/:id/statuses/:sha` (set commit CI status).
- **Branches/tags**: `GET/POST/DELETE .../repository/branches[/:branch]`,
  `DELETE .../repository/merged_branches` (bulk), `GET/POST/DELETE .../repository/tags[/:tag]` (annotated
  via `message`).
- **Protected branches/tags**: `GET/POST/PATCH/DELETE /projects/:id/protected_branches[/:name]`
  — granular `allowed_to_push[]`/`allowed_to_merge[]`/`allowed_to_unprotect[]` of
  `{access_level}|{user_id}|{group_id}|{deploy_key_id}`, `allow_force_push` (Free),
  `code_owner_approval_required` (**EE**). Protected tags: `/protected_tags[/:name]` (`create_access_level`).

## Merge requests
- List: `GET /merge_requests` (instance; `scope=assigned_to_me|reviews_for_me|created_by_me`),
  `/groups/:id/merge_requests`, `/projects/:id/merge_requests` (`state`, `labels`, `milestone`,
  `author_id`, `reviewer_id`, `search&in=title`).
- CRUD: `GET/POST/PUT/DELETE /projects/:id/merge_requests[/:iid]`. Create: `{source_branch,
  target_branch, title, assignee_ids, reviewer_ids, labels, milestone_id, remove_source_branch, squash}`.
  **Draft** = prefix title `Draft: ` (no boolean).
- Merge: `PUT .../:iid/merge {auto_merge, squash, squash_commit_message, should_remove_source_branch, sha}`
  (`auto_merge` = merge-when-pipeline-succeeds, replaces the deprecated flag; `merge_after` schedules).
  `.../merge_ref` (preview), `POST .../cancel_merge_when_pipeline_succeeds`, `PUT .../rebase`.
- Inspect: `.../changes`, `.../diffs`, `.../raw_diffs`, `.../commits`, `.../versions`, `.../pipelines`
  (`POST` creates a detached MR pipeline), `.../participants`, `.../reviewers`, `.../closes_issues`,
  `.../related_issues`, `.../blocks`/`.../blockees` (dependency graph), time tracking, `.../subscribe`,
  `.../todo`.
- **Approvals**: Free — `POST .../:iid/{approve,unapprove}`, `PUT .../:iid/reset_approvals`,
  `GET .../:iid/approvals|approval_state`, `GET/POST /projects/:id/approvals` (config:
  `reset_approvals_on_push`, `merge_requests_author_approval`, ...). **EE** — multi-rule
  `approval_rules` (project/MR/group). **Merge trains**: `/projects/:id/merge_trains/*` (**EE**).
- **Suggested changes**: no endpoint — post a discussion whose body has a ```` ```suggestion ````
  block; apply via the normal note flow.

## Issues
- List: `GET /issues` | `/groups/:id/issues` | `/projects/:id/issues` (`state`, `labels`,
  `milestone`, `assignee_id`, `author_id`, `confidential`, `iids[]`, `my_reaction_emoji`, `search&in=`).
- CRUD: `GET/POST/PUT/DELETE /projects/:id/issues[/:iid]`. Update close/reopen via `state_event`.
  Actions: `POST .../:iid/{move,clone,subscribe,unsubscribe,todo}`, `.../reorder`, time tracking
  (`time_estimate`, `add_spent_time` accept `"3h30m"`), `GET .../:iid/{related_merge_requests,closed_by,participants}`.
  Links: `GET/POST/DELETE /projects/:id/issues/:iid/links[/:link_id]` (`link_type: relates_to|blocks|is_blocked_by`).
  Stats: `/issues_statistics`. **EE**: `assignee_ids` (multiple), `weight`, `epic_id`.

## Boards / labels / milestones
- Boards: `GET/POST/PUT/DELETE /projects\|groups/:id/boards[/:bid]`, `.../boards/:bid/lists[/:lid]`.
- Labels: `GET/POST/PUT/DELETE /projects\|groups/:id/labels[/:lid]`, `POST .../promote`, `.../subscribe`.
- Milestones: `GET/POST/PUT/DELETE /projects\|groups/:id/milestones[/:mid]`, `.../{issues,merge_requests,burndown_events}`, `POST .../promote`.
- **EE**: epics (`/groups/:id/epics`), iterations (`/projects\|groups/:id/iterations`, cadences).

## Members & access
`GET /projects\|groups/:id/members` (direct) · `/members/all` (inherited) · `POST` (`user_id(s)`/
`username(s)`, `access_level`, `expires_at`, `member_role_id`=EE) · `PUT`/`DELETE .../:user_id`.
Invitations (by email): `POST/GET/PUT/DELETE /projects\|groups/:id/invitations[/:email]`. Access
requests: `GET/POST /projects\|groups/:id/access_requests`, `PUT .../:user_id/approve`, `DELETE .../:user_id`.

## Packages, registry, deploy creds, webhooks, wikis, snippets, releases
- Packages: `GET /projects\|groups/:id/packages`, `GET .../packages/:pid[/package_files|/pipelines]`,
  `DELETE .../packages/:pid[/package_files/:fid]`.
- Container registry: `GET /projects\|groups/:id/registry/repositories`, `GET /registry/repositories/:id`,
  `.../repositories/:rid/tags[/:tag]`, `DELETE .../tags` (bulk: `name_regex_delete`, `keep_n`, `older_than`),
  `DELETE .../repositories/:rid`.
- Deploy keys: `GET/POST /projects/:id/deploy_keys`, `POST .../:kid/enable`. Deploy tokens:
  `GET/POST/DELETE /projects\|groups/:id/deploy_tokens` (scopes: `read_repository`, `read/write_registry`,
  `read/write_package_registry`).
- Webhooks: `GET/POST/PUT/DELETE /projects/:id/hooks[/:hid]`, `GET .../:hid/events`,
  `POST .../:hid/test/:trigger`, custom headers/url variables; 19.0 adds `signing_token` (HMAC).
  Event toggles: `push_events`, `merge_requests_events`, `pipeline_events`, `job_events`,
  `releases_events`, `deployment_events`, etc.
- Wikis: `GET/POST/PUT/DELETE /projects/:id/wikis[/:slug]`, `POST .../wikis/attachments`. Snippets:
  `/projects/:id/snippets` (+ personal `/snippets`).

## Notes / discussions (uniform across issues, MRs, commits, snippets, epics, wiki pages)
For `{R}` = `issues/:iid` | `merge_requests/:iid` | `repository/commits/:sha` | `snippets/:sid`:
- Notes (flat): `GET/POST /projects/:id/{R}/notes`, `GET/PUT/DELETE .../notes/:note_id`.
- Discussions (threaded): `GET/POST .../{R}/discussions`, `POST .../discussions/:did/notes` (reply),
  `PUT .../merge_requests/:iid/discussions/:did {resolved:true}` (resolve).
- Award emoji (reactions): `GET/POST/DELETE .../award_emoji`. Resource label events (audit trail):
  `.../resource_label_events`.
