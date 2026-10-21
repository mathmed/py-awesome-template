<!-- High or critical risk only, as the first line: Risk high: <what can break, for whom>. Otherwise the
risk lives only in the risk:<level> label. Stacked PRs only: Stacked on #<number>; merge it first. -->
## Summary
<1-2 sentences: what changes and why. Must stand alone. End with what was not verified, only if it matters.>

<!-- ONE visual, picked by the type of change, or none when the summary says it all:
rule or behavior: What | Before | After table (max 3 rows, 12 words per cell); flow or state: small Mermaid
diagram; numbers or limits: before/after values table; contract or config: diff block of max 15 lines. -->
| What | Before | After |
| ---- | ------ | ----- |
| <rule, in plain words> | <before> | <after> |

<!-- Only with a real step (migration, env var or secret, flag, merge order, external config); else delete. -->
**Deploy:** <the step; rollback only when it is not a plain revert>
