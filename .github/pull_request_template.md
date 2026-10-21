## Risk
**<low | medium | high | critical>** — <one line: why>
<!-- Most PRs are low or medium. Any deploy step other than "None" is at least medium. High or critical needs
one concrete sentence naming what can break; without it, lower the level. -->

## Summary
<one sentence: what changes in behavior, and why>

## Behavior
<!-- Max 5, most critical first. Plain words for a person who has not read the code: rules and observable
behavior, short and objective. No backticks, paths, file, function or test names: evidence goes in Look here. -->
- **<rule or behavior, in plain words>:** <before> → <after>

**Unchanged:** <what a reviewer might fear broke, or "behavior-preserving refactor">

## Look here
<!-- Most important first. The only place for file, function and test references. Every Behavior item has its
evidence here: the test that asserts it, or the code that implements it when no test does (one item may
cover several Behavior items). Each item says which behavior it proves or contains and why it deserves human
eyes. Also list changes to pipeline config or checks, mismatches and anything that departs from the task. -->
1. `<test or file:function>` — <which behavior it proves or contains, and why it deserves human eyes>

## Review
<!-- From the reviewer's report (.handoff/<branch>.review.md): the verdict and, one per line, the findings the diff
still has, with the severity and why they stayed open. With no open finding: "No open findings." Without a report:
"No review." (and "no review" under Not verified). -->
**<reviewer's verdict>**
- **<blocking | should fix | nit>:** <the finding, in plain words> — <why it stayed open>

## Deploy steps
<!-- Always present. If nothing is needed, write: None: normal merge and deploy. -->
- [ ] Before merge: <migration order, new env vars or secrets, flags>
- [ ] After deploy: <backfill, external config, checks>
- [ ] Rollback: <how to revert>

**Not verified:** <what the author could not check, or "nothing">
<!-- Only if the diff contradicts the author's handoff notes, add: **Mismatch:** <what the notes said vs what the diff does> -->
