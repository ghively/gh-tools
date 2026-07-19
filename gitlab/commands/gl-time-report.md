---
description: Report on time tracking across a project's issues and MRs (estimates vs spent)
argument-hint: <project | group> [--milestone <name>] [--since YYYY-MM-DD]
---

Aggregate time-tracking data for reporting. Read `references/projects-repo-mrs-issues.md`
and `references/members-access-deep.md`. Read-only — no changes.

1. **Scope the query** (read-only): project or group; optional milestone filter or date range.
    For a group: `groups(action="projects", group=...)` to enumerate member projects.
2. **Gather issues + MRs** (GraphQL is dramatically more efficient than REST for this):
    ```graphql
    query($fp:ID!){
      project(fullPath:$fp){
        issues(first:100){ nodes {
          iid title state
          timeStats { estimate spent total }
          assignees(first:3){ nodes { username } }
          milestone { title }
        }}
        mergeRequests(state:merged){ nodes {
          iid title
          timeStats { estimate spent total }
          author { username }
        }}
      }
    }
    ```
3. **Aggregate**:
    - **per assignee**: total estimated vs spent, # items, overrun count (spent > estimate).
    - **per milestone**: total estimated vs spent, # items open vs closed.
    - **per state**: open vs closed time investment.
    - **per type**: issues vs MRs.
4. **Flag**: items with spent >> estimate (re-estimate?), items with spent but no estimate
    (planning gap), items with estimate but no spent (stale?).
5. **Report**: tables + totals. Highlight overruns, unestimated work, and the assignee/
    milestone concentration. Recommend: re-estimating the overruns, setting estimates on the
    unestimated, closing/re-opening stale items.

For cycle-time analysis (time-in-state), pair with `resource_events(...)` which returns the
label/state transition history — compute median time from `opened` to `closed` per milestone.
