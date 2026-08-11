# Common non-curated tasks — `unraid_graphql` recipes

Copy-paste-ready calls for jobs that don't have a dedicated curated tool.
Always confirm destructive/renaming actions with the user first — these
mutations run immediately, with no gate of their own beyond what you build in
around the call.

## Rename the server / set its model & comment
```graphql
mutation($n: String!, $c: String, $m: String) {
  updateServerIdentity(name: $n, comment: $c, sysModel: $m) { name comment sysModel }
}
```
variables: `{"n": "MyServer", "c": "living room", "m": "Custom"}`

## Read OIDC (SSO) provider configuration
```graphql
{ oidcConfiguration { providers { id name issuer buttonText } defaultAllowedOrigins } }
```
There's no dedicated mutation in this schema version for OIDC providers —
manage them through `unraid_settings_update` against the same JSON shape
`unraid_settings` returns under `unified.values.sso`, matching
`unified.dataSchema`'s `sso` section.

## Docker container organizer (folders/grouping in the webGUI)
Purely cosmetic grouping of containers in the dashboard, not container
control:
```graphql
mutation($name: String!, $parent: String, $children: [String!]) {
  createDockerFolder(name: $name, parentId: $parent, childrenIds: $children) { version }
}
```
Also available: `setDockerFolderChildren`, `deleteDockerEntries`,
`moveDockerEntriesToFolder`, `moveDockerItemsToPosition`,
`renameDockerFolder`, `updateDockerViewPreferences`.

## Docker template/digest maintenance
```graphql
mutation { syncDockerTemplatePaths { scanned matched skipped errors } }
mutation { resetDockerTemplateMappings }
mutation { refreshDockerDigests }
```

## Onboarding / fresh-install state (only relevant on a brand-new box)
```graphql
{ internalBootContext { __typename } }
mutation { onboarding { completeOnboarding { __typename } } }
```
See `schema.graphql`'s `OnboardingMutations` for the full set
(`resetOnboarding`, `openOnboarding`/`closeOnboarding`,
`createInternalBootPool`, etc.) — not relevant once a server is configured.

## Enabling Unraid Connect (to unlock remote-access / cloud fields)
`connect`/`cloud`/`remoteAccess`/`network{accessUrls}` are absent from the
live schema on servers without the Connect plugin (see `api-map.md`'s Hard
Limits). Installing Connect is a webGUI action (Settings → Connect →
"Enable"), not something to script blindly — it links the server to an
Unraid.net account. If the user wants this, point them at the webGUI rather
than trying to script the sign-in mutation (`connectSignIn` needs a
Unraid.net-issued API key you don't have).

## Probing an unfamiliar mutation/field safely
Before running an unfamiliar write, check its shape:
```
unraid_schema_type(name="ArrayMutations")   # or DockerMutations, VmMutations, ...
```
Then call a read-only field with deliberately-empty/fake args first if you're
unsure whether it exists at all — `GRAPHQL_VALIDATION_FAILED` means the field
truly isn't there; any other error code (`FORBIDDEN`, `BAD_USER_INPUT`,
`INTERNAL_SERVER_ERROR`) means it exists and you just need the right
arguments.
