# opencode HTTP API — full surface map

Enumerated live from `GET /doc` (OpenAPI 3.1) on opencode **1.x**. **188 operations** across 49 domains.
There are two parallel surfaces: the **legacy** unprefixed API (what the stable SDK uses) and a newer **`/api/*` v2** API. Both work; curated tools use legacy, passthrough (`oc_call`) reaches either.

Reach anything here with `oc_call(method, path, params, body)`; find operations with `oc_discover(query)`; inspect shapes with `oc_schema(operationId)`.

## agent

- `GET /agent` — List agents  ·  `app.agents`

## api-v2/agent

- `GET /api/agent` — List agents  ·  `v2.agent.list`

## api-v2/command

- `GET /api/command` — List commands  ·  `v2.command.list`

## api-v2/credential

- `PATCH /api/credential/{credentialID}` — Update credential  ·  `v2.credential.update`
- `DELETE /api/credential/{credentialID}` — Remove credential  ·  `v2.credential.remove`

## api-v2/event

- `GET /api/event` — Subscribe to events  ·  `v2.event.subscribe`

## api-v2/fs

- `GET /api/fs/find` — Find files  ·  `v2.fs.find`
- `GET /api/fs/list` — List directory  ·  `v2.fs.list`
- `GET /api/fs/read/*` — Read file  ·  `v2.fs.read`

## api-v2/health

- `GET /api/health` — Check server health  ·  `v2.health.get`

## api-v2/integration

- `GET /api/integration` — List integrations  ·  `v2.integration.list`
- `GET /api/integration/attempt/{attemptID}` — Get OAuth attempt status  ·  `v2.integration.attempt.status`
- `DELETE /api/integration/attempt/{attemptID}` — Cancel OAuth connection  ·  `v2.integration.attempt.cancel`
- `POST /api/integration/attempt/{attemptID}/complete` — Complete OAuth connection  ·  `v2.integration.attempt.complete`
- `GET /api/integration/{integrationID}` — Get integration  ·  `v2.integration.get`
- `POST /api/integration/{integrationID}/connect/key` — Connect with key  ·  `v2.integration.connect.key`
- `POST /api/integration/{integrationID}/connect/oauth` — Begin OAuth connection  ·  `v2.integration.connect.oauth`

## api-v2/location

- `GET /api/location` — Get location  ·  `v2.location.get`

## api-v2/model

- `GET /api/model` — List models  ·  `v2.model.list`

## api-v2/permission

- `GET /api/permission/request` — List pending permission requests  ·  `v2.permission.request.list`
- `GET /api/permission/saved` — List saved permissions  ·  `v2.permission.saved.list`
- `DELETE /api/permission/saved/{id}` — Remove saved permission  ·  `v2.permission.saved.remove`

## api-v2/provider

- `GET /api/provider` — List providers  ·  `v2.provider.list`
- `GET /api/provider/{providerID}` — Get provider  ·  `v2.provider.get`

## api-v2/pty

- `GET /api/pty` — List PTY sessions  ·  `v2.pty.list`
- `POST /api/pty` — Create PTY session  ·  `v2.pty.create`
- `GET /api/pty/{ptyID}` — Get PTY session  ·  `v2.pty.get`
- `PUT /api/pty/{ptyID}` — Update PTY session  ·  `v2.pty.update`
- `DELETE /api/pty/{ptyID}` — Remove PTY session  ·  `v2.pty.remove`
- `GET /api/pty/{ptyID}/connect` — Connect to PTY session  ·  `v2.pty.connect`
- `POST /api/pty/{ptyID}/connect-token` — Create PTY WebSocket token  ·  `v2.pty.connectToken`

## api-v2/question

- `GET /api/question/request` — List pending question requests  ·  `v2.question.request.list`

## api-v2/reference

- `GET /api/reference` — List references  ·  `v2.reference.list`

## api-v2/session

- `GET /api/session` — List sessions  ·  `v2.session.list`
- `POST /api/session` — Create session  ·  `v2.session.create`
- `GET /api/session/active` — List active sessions  ·  `v2.session.active`
- `GET /api/session/{sessionID}` — Get session  ·  `v2.session.get`
- `POST /api/session/{sessionID}/agent` — Switch session agent  ·  `v2.session.switchAgent`
- `POST /api/session/{sessionID}/compact` — Compact session  ·  `v2.session.compact`
- `GET /api/session/{sessionID}/context` — Get session context  ·  `v2.session.context`
- `GET /api/session/{sessionID}/event` — Subscribe to session events  ·  `v2.session.events`
- `GET /api/session/{sessionID}/history` — Get session history  ·  `v2.session.history`
- `POST /api/session/{sessionID}/interrupt` — Interrupt session execution  ·  `v2.session.interrupt`
- `GET /api/session/{sessionID}/message` — Get session messages  ·  `v2.session.messages`
- `GET /api/session/{sessionID}/message/{messageID}` — Get session message  ·  `v2.session.message`
- `POST /api/session/{sessionID}/model` — Switch session model  ·  `v2.session.switchModel`
- `POST /api/session/{sessionID}/permission` — Create permission request  ·  `v2.session.permission.create`
- `GET /api/session/{sessionID}/permission` — List session permission requests  ·  `v2.session.permission.list`
- `GET /api/session/{sessionID}/permission/{requestID}` — Get permission request  ·  `v2.session.permission.get`
- `POST /api/session/{sessionID}/permission/{requestID}/reply` — Reply to pending permission request  ·  `v2.session.permission.reply`
- `POST /api/session/{sessionID}/prompt` — Send message  ·  `v2.session.prompt`
- `GET /api/session/{sessionID}/question` — List session question requests  ·  `v2.session.question.list`
- `POST /api/session/{sessionID}/question/{requestID}/reject` — Reject pending question request  ·  `v2.session.question.reject`
- `POST /api/session/{sessionID}/question/{requestID}/reply` — Reply to pending question request  ·  `v2.session.question.reply`
- `POST /api/session/{sessionID}/revert/clear` — Clear staged revert  ·  `v2.session.revert.clear`
- `POST /api/session/{sessionID}/revert/commit` — Commit staged revert  ·  `v2.session.revert.commit`
- `POST /api/session/{sessionID}/revert/stage` — Stage session revert  ·  `v2.session.revert.stage`
- `POST /api/session/{sessionID}/wait` — Wait for session  ·  `v2.session.wait`

## api-v2/skill

- `GET /api/skill` — List skills  ·  `v2.skill.list`

## auth

- `PUT /auth/{providerID}` — Set auth credentials  ·  `auth.set`
- `DELETE /auth/{providerID}` — Remove auth credentials  ·  `auth.remove`

## command

- `GET /command` — List commands  ·  `command.list`

## config

- `GET /config` — Get configuration  ·  `config.get`
- `PATCH /config` — Update configuration  ·  `config.update`
- `GET /config/providers` — List config providers  ·  `config.providers`

## event

- `GET /event` — Subscribe to events  ·  `event.subscribe`

## experimental/capabilities

- `GET /experimental/capabilities` — Get experimental capabilities  ·  `experimental.capabilities.get`

## experimental/console

- `GET /experimental/console` — Get active Console provider metadata  ·  `experimental.console.get`
- `GET /experimental/console/orgs` — List switchable Console orgs  ·  `experimental.console.listOrgs`
- `POST /experimental/console/switch` — Switch active Console org  ·  `experimental.console.switchOrg`

## experimental/control-plane

- `POST /experimental/control-plane/move-session` — Move session  ·  `experimental.controlPlane.moveSession`

## experimental/project

- `POST /experimental/project/{projectID}/copy` —   ·  `v2.projectCopy.create`
- `DELETE /experimental/project/{projectID}/copy` —   ·  `v2.projectCopy.remove`
- `POST /experimental/project/{projectID}/copy/generate-name` — Generate project copy name  ·  `experimental.projectCopy.generateName`
- `POST /experimental/project/{projectID}/copy/refresh` —   ·  `v2.projectCopy.refresh`

## experimental/resource

- `GET /experimental/resource` — Get MCP resources  ·  `experimental.resource.list`

## experimental/session

- `GET /experimental/session` — List sessions  ·  `experimental.session.list`
- `POST /experimental/session/{sessionID}/background` — Background subagents  ·  `experimental.session.background`

## experimental/tool

- `GET /experimental/tool` — List tools  ·  `tool.list`
- `GET /experimental/tool/ids` — List tool IDs  ·  `tool.ids`

## experimental/workspace

- `GET /experimental/workspace` — List workspaces  ·  `experimental.workspace.list`
- `POST /experimental/workspace` — Create workspace  ·  `experimental.workspace.create`
- `GET /experimental/workspace/adapter` — List workspace adapters  ·  `experimental.workspace.adapter.list`
- `GET /experimental/workspace/status` — Workspace status  ·  `experimental.workspace.status`
- `POST /experimental/workspace/sync-list` — Sync workspace list  ·  `experimental.workspace.syncList`
- `POST /experimental/workspace/warp` — Warp session into workspace  ·  `experimental.workspace.warp`
- `DELETE /experimental/workspace/{id}` — Remove workspace  ·  `experimental.workspace.remove`

## experimental/worktree

- `GET /experimental/worktree` — List worktrees  ·  `worktree.list`
- `POST /experimental/worktree` — Create worktree  ·  `worktree.create`
- `DELETE /experimental/worktree` — Remove worktree  ·  `worktree.remove`
- `POST /experimental/worktree/reset` — Reset worktree  ·  `worktree.reset`

## file

- `GET /file` — List files  ·  `file.list`
- `GET /file/content` — Read file  ·  `file.read`
- `GET /file/status` — Get file status  ·  `file.status`

## find

- `GET /find` — Find text  ·  `find.text`
- `GET /find/file` — Find files  ·  `find.files`
- `GET /find/symbol` — Find symbols  ·  `find.symbols`

## formatter

- `GET /formatter` — Get formatter status  ·  `formatter.status`

## global

- `GET /global/config` — Get global configuration  ·  `global.config.get`
- `PATCH /global/config` — Update global configuration  ·  `global.config.update`
- `POST /global/dispose` — Dispose instance  ·  `global.dispose`
- `GET /global/event` — Get global events  ·  `global.event`
- `GET /global/health` — Get health  ·  `global.health`
- `POST /global/upgrade` — Upgrade opencode  ·  `global.upgrade`

## instance

- `POST /instance/dispose` — Dispose instance  ·  `instance.dispose`

## log

- `POST /log` — Write log  ·  `app.log`

## lsp

- `GET /lsp` — Get LSP status  ·  `lsp.status`

## mcp

- `GET /mcp` — Get MCP status  ·  `mcp.status`
- `POST /mcp` — Add MCP server  ·  `mcp.add`
- `POST /mcp/{name}/auth` — Start MCP OAuth  ·  `mcp.auth.start`
- `DELETE /mcp/{name}/auth` — Remove MCP OAuth  ·  `mcp.auth.remove`
- `POST /mcp/{name}/auth/authenticate` — Authenticate MCP OAuth  ·  `mcp.auth.authenticate`
- `POST /mcp/{name}/auth/callback` — Complete MCP OAuth  ·  `mcp.auth.callback`
- `POST /mcp/{name}/connect` —   ·  `mcp.connect`
- `POST /mcp/{name}/disconnect` —   ·  `mcp.disconnect`

## path

- `GET /path` — Get paths  ·  `path.get`

## permission

- `GET /permission` — List pending permissions  ·  `permission.list`
- `POST /permission/{requestID}/reply` — Respond to permission request  ·  `permission.reply`

## project

- `GET /project` — List all projects  ·  `project.list`
- `GET /project/current` — Get current project  ·  `project.current`
- `POST /project/git/init` — Initialize git repository  ·  `project.initGit`
- `PATCH /project/{projectID}` — Update project  ·  `project.update`
- `GET /project/{projectID}/directories` — List project directories  ·  `project.directories`

## provider

- `GET /provider` — List providers  ·  `provider.list`
- `GET /provider/auth` — Get provider auth methods  ·  `provider.auth`
- `POST /provider/{providerID}/oauth/authorize` — Start OAuth authorization  ·  `provider.oauth.authorize`
- `POST /provider/{providerID}/oauth/callback` — Handle OAuth callback  ·  `provider.oauth.callback`

## pty

- `GET /pty` — List PTY sessions  ·  `pty.list`
- `POST /pty` — Create PTY session  ·  `pty.create`
- `GET /pty/shells` — List available shells  ·  `pty.shells`
- `GET /pty/{ptyID}` — Get PTY session  ·  `pty.get`
- `PUT /pty/{ptyID}` — Update PTY session  ·  `pty.update`
- `DELETE /pty/{ptyID}` — Remove PTY session  ·  `pty.remove`
- `GET /pty/{ptyID}/connect` — Connect to PTY session  ·  `pty.connect`
- `POST /pty/{ptyID}/connect-token` — Create PTY WebSocket token  ·  `pty.connectToken`

## question

- `GET /question` — List pending questions  ·  `question.list`
- `POST /question/{requestID}/reject` — Reject question request  ·  `question.reject`
- `POST /question/{requestID}/reply` — Reply to question request  ·  `question.reply`

## session

- `GET /session` — List sessions  ·  `session.list`
- `POST /session` — Create session  ·  `session.create`
- `GET /session/status` — Get session status  ·  `session.status`
- `GET /session/{sessionID}` — Get session  ·  `session.get`
- `DELETE /session/{sessionID}` — Delete session  ·  `session.delete`
- `PATCH /session/{sessionID}` — Update session  ·  `session.update`
- `POST /session/{sessionID}/abort` — Abort session  ·  `session.abort`
- `GET /session/{sessionID}/children` — Get session children  ·  `session.children`
- `POST /session/{sessionID}/command` — Send command  ·  `session.command`
- `GET /session/{sessionID}/diff` — Get message diff  ·  `session.diff`
- `POST /session/{sessionID}/fork` — Fork session  ·  `session.fork`
- `POST /session/{sessionID}/init` — Initialize session  ·  `session.init`
- `GET /session/{sessionID}/message` — Get session messages  ·  `session.messages`
- `POST /session/{sessionID}/message` — Send message  ·  `session.prompt`
- `GET /session/{sessionID}/message/{messageID}` — Get message  ·  `session.message`
- `DELETE /session/{sessionID}/message/{messageID}` — Delete message  ·  `session.deleteMessage`
- `DELETE /session/{sessionID}/message/{messageID}/part/{partID}` —   ·  `part.delete`
- `PATCH /session/{sessionID}/message/{messageID}/part/{partID}` —   ·  `part.update`
- `POST /session/{sessionID}/permissions/{permissionID}` — Respond to permission  ·  `permission.respond`
- `POST /session/{sessionID}/prompt_async` — Send async message  ·  `session.prompt_async`
- `POST /session/{sessionID}/revert` — Revert message  ·  `session.revert`
- `POST /session/{sessionID}/share` — Share session  ·  `session.share`
- `DELETE /session/{sessionID}/share` — Unshare session  ·  `session.unshare`
- `POST /session/{sessionID}/shell` — Run shell command  ·  `session.shell`
- `POST /session/{sessionID}/summarize` — Summarize session  ·  `session.summarize`
- `GET /session/{sessionID}/todo` — Get session todos  ·  `session.todo`
- `POST /session/{sessionID}/unrevert` — Restore reverted messages  ·  `session.unrevert`

## skill

- `GET /skill` — List skills  ·  `app.skills`

## sync

- `POST /sync/history` — List sync events  ·  `sync.history.list`
- `POST /sync/replay` — Replay sync events  ·  `sync.replay`
- `POST /sync/start` — Start workspace sync  ·  `sync.start`
- `POST /sync/steal` — Steal session into workspace  ·  `sync.steal`

## tui

- `POST /tui/append-prompt` — Append TUI prompt  ·  `tui.appendPrompt`
- `POST /tui/clear-prompt` — Clear TUI prompt  ·  `tui.clearPrompt`
- `GET /tui/control/next` — Get next TUI request  ·  `tui.control.next`
- `POST /tui/control/response` — Submit TUI response  ·  `tui.control.response`
- `POST /tui/execute-command` — Execute TUI command  ·  `tui.executeCommand`
- `POST /tui/open-help` — Open help dialog  ·  `tui.openHelp`
- `POST /tui/open-models` — Open models dialog  ·  `tui.openModels`
- `POST /tui/open-sessions` — Open sessions dialog  ·  `tui.openSessions`
- `POST /tui/open-themes` — Open themes dialog  ·  `tui.openThemes`
- `POST /tui/publish` — Publish TUI event  ·  `tui.publish`
- `POST /tui/select-session` — Select session  ·  `tui.selectSession`
- `POST /tui/show-toast` — Show TUI toast  ·  `tui.showToast`
- `POST /tui/submit-prompt` — Submit TUI prompt  ·  `tui.submitPrompt`

## vcs

- `GET /vcs` — Get VCS info  ·  `vcs.get`
- `POST /vcs/apply` — Apply VCS patch  ·  `vcs.apply`
- `GET /vcs/diff` — Get VCS diff  ·  `vcs.diff`
- `GET /vcs/diff/raw` — Get raw VCS diff  ·  `vcs.diff.raw`
- `GET /vcs/status` — Get VCS status  ·  `vcs.status`
