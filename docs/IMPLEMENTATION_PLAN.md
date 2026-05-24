# Hermes Continuity Implementation Plan

## Implemented Spine

- Project/domain routing manifest.
- Context resolver CLI and API.
- Worker context injection.
- Dashboard chat and Open WebUI context injection.
- Telegram conversation context injection.
- Repo cache sync from GitHub.
- Data continuity documentation.
- Starter approval policy file.
- Outreach artifact expectations for lead/flyer/email tasks.

## Next Build Items

1. Dashboard continuity tab: show VPS queue state, stale dashboard tasks, failed callbacks, and current repo cache SHAs.
2. Trends tab: store daily trend reports and convert recommendations to tasks.
3. Outreach event ledger: durable events per lead: gathered, researched, preview generated, approved, sent, follow-up needed, draft ready, responded, bounced, won/lost/snoozed.
4. Email integration: send approved emails from dashboard and fetch replies into lead events.
5. Project approval editor: edit `approval-policies.json` through dashboard with Git-backed review.
6. Ambiguous task UI: when Hermes says `needsClarification`, show project choices instead of queueing execution.
