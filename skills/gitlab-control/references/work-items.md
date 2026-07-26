# Work items — the modern issue/task layer (and what replaces Premium epics on CE)

Work items are GitLab's newer issue/task/incident/test-case/requirement abstraction.
Introduced to unify the fragmented "issue + epic + iteration + requirement" surface under
one GraphQL-native model. On CE they're a Free, GraphQL-first way to model work that the
older issues API can't express well (hierarchy, custom types, structured widgets).

This file covers what CE has, what's Premium-gated, and how to use work items where issues
fall short.

## Work item types (CE)

| Type | Description | CE |
|---|---|---|
| `ISSUE` | basic issue (backed by an Issue record) | ✅ |
| `TASK` | atomic to-do item | ✅ |
| `INCIDENT` | ops incident (response + timeline) | ✅ |
| `TEST_CASE` | QA test case | ✅ |
| `REQUIREMENT` | compliance requirement (with test case links) | ✅ |
| `OBJECTIVE` | objective with progress | ✅ |
| `KEY_RESULT` | measurable result for an objective | ✅ |
| `EPIC` | cross-project epic (group-scoped) | **Premium** (404s on CE) |
| `REQUIREMENT` (with compliance frameworks) | compliance-pinned | **Premium** |
| Custom work item types | org-defined types | **Premium** |

The hierarchy `OBJECTIVE → KEY_RESULT → ISSUE/TASK` works on Free — that's the CE-friendly
epic alternative. Multi-level parent/child work item hierarchies work on Free for the basic
types.

## Reading work items (GraphQL-first — there's no clean REST surface)

### All work items in a project
```graphql
query {
  project(fullPath: "GROUP/PROJECT") {
    workItems(first: 50) {
      nodes {
        id iid
        workItemType { name }
        title state
        createdAt updatedAt
        assignees(first: 5) { nodes { username } }
        widgets { type }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
```

### A single work item by ID
```graphql
query {
  workItem(id: "gid://gitlab/WorkItem/123") {
    id iid title state description
    workItemType { name icon }
    widgets {
      type
      ... on WorkItemWidgetDescription { content }
      ... on WorkItemWidgetAssignees { assignees(first: 10) { nodes { username } } }
      ... on WorkItemWidgetHierarchy { parent { id } children(first: 10) { nodes { id title } } }
      ... on WorkItemWidgetLabels { labels(first: 10) { nodes { title } } }
      ... on WorkItemWidgetStartAndDueDate { startDate dueDate }
      ... on WorkItemWidgetTimeTracking { timeEstimate spentTime }
    }
  }
}
```

The **widgets** field is the key abstraction — each work item has a set of typed widgets
(description, assignees, labels, hierarchy, dates, time tracking, weight, etc.) that you
query with inline fragments. Introspect a work item type to see which widgets it supports:
```graphql
query { workItemType(id: "gid://gitlab/WorkItem::Type/N") { widgetDefinitions { type name } } }
```

## Creating work items

```graphql
mutation($input: WorkItemCreateInput!) {
  workItemCreate(input: $input) {
    workItem { id iid title state }
    errors
  }
}
```
with `variables: {"input": {"namespacePath": "GROUP/PROJECT", "workItemTypeId":
"gid://gitlab/WorkItem::Type/N", "title": "...", "description": "..."}}`. To get a type's
GID, query `project { workItemTypes { nodes { id name } } }`.

### Hierarchies (parent/child) — the epic replacement
```graphql
mutation($input: WorkItemAddLinkedItemsInput!) {
  workItemAddLinkedItems(input: $input) { errors }
}
```
Link type `"parent"` makes the new item a child. Use `OBJECTIVE` (parent) → `KEY_RESULT`
(children) → `ISSUE`/`TASK` (grandchildren) to model "epic → story → task" without Premium.

## Updating & converting

```graphql
mutation($input: WorkItemUpdateInput!) {
  workItemUpdate(input: $input) { workItem { iid state } errors }
}
mutation($input: WorkItemConvertInput!) {
  workItemConvert(input: $input) { workItem { workItemType { name } } errors }
}
```
Conversion lets an ISSUE become a TASK or INCIDENT without losing history.

## What CE doesn't have (Premium)

- **Epic work item type** — the cross-project epic view (you can build a CE approximation
  using `OBJECTIVE` as a project-internal epic).
- **Custom work item types** — org-defined types with custom widgets.
- **Rollup widgets** — summing story points / progress across children.
- **Linked items beyond hierarchy** (blocks/blocked-by across work items) — Premium.
- **Iteration cadences** for scheduling work items into sprints — Premium.

## When to use work items vs issues/MRs on CE

- **Use issues** for: bug tracking, feature requests, day-to-day engineering work. The
  curated `issues` / `manage_issue` tools handle these. Most teams never need more.
- **Use work items** for: incidents (typed, with timelines), QA test cases (linked to
  requirements), structured objectives & key results, anything needing parent/child
  hierarchy beyond what issue links offer.
- **Use MRs** for: code changes — they're not work items, they're the merge surface. MRs
  link to issues/work items via `closes #N`.

## Practical CE patterns

- **Incident response**: project with `INCIDENT` work items, each linked to its resolution
  MRs and postmortem ISSUE. GraphQL dashboard query surfaces open incidents + their MRs.
- **OKR tracking**: `OBJECTIVE` (top) → `KEY_RESULT` (measurable, with progress) →
  `ISSUE`/`TASK` (the work). One GraphQL query pulls the whole tree.
- **Test case management**: `TEST_CASE` work items, linked to `REQUIREMENT`s; CI jobs query
  the test cases for a requirement and report results back as notes.
- **Sprint approximation** without iterations (Premium): use a milestone + filter work items
  by milestone via GraphQL. Less ergonomic than iterations but workable.

## Tooling notes

- The curated `manage_issue` / `list_issues` / `get_issue` tools work for the `ISSUE` work
  item type specifically (issues ARE work items under the hood, exposed via REST).
- For other types (`TASK`, `INCIDENT`, etc.), use `gitlab_graphql` — there's no curated REST
  tool because the REST surface is being deprecated in favor of GraphQL.
- The `notes` and `award_emoji` tools work on issues/work items interchangeably (they share
  the noteable interface).
