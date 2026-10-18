## Risk
**<low | medium | high | critical>** — <one line: why>
<!-- Floor: pipeline config, migrations and auth are never below high. Any deploy step other than "None" is at least medium. -->

## Summary
<one sentence: what changes in behavior, and why>

## Behavior
<!-- max 5, most critical first. Business rules and observable behavior, not code. -->
- **<rule or behavior>:** <before> → <after> · evidence: `<test or file:function>`

**Unchanged:** <what a reviewer might fear broke, or "behavior-preserving refactor">

## Look here
1. `<file:function>` — <why it deserves human eyes>

## Deploy steps
<!-- Always present. If nothing is needed, write: None: normal merge and deploy. -->
- [ ] Before merge: <migration order, new env vars or secrets, flags>
- [ ] After deploy: <backfill, external config, checks>
- [ ] Rollback: <how to revert>

**Not verified:** <what the author could not check, or "nothing">
<!-- Only if the diff contradicts the author's handoff notes, add: **Mismatch:** <what the notes said vs what the diff does> -->
