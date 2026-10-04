# AI-assisted development: our pipeline benchmarked against the market (October 2026)

> **Scope.** How we gate AI-written code before merge, how we protect production after deploy, and how we run
> coding agents, compared with what vendors, researchers and practitioners reported between mid-2025 and
> October 2026. Written for the tech lead to drive decisions; every claim cites a numbered source in
> [Appendix A](#appendix-a-sources).
>
> **Disclosure note.** This repository is public. The report deliberately leaves out credentials, account
> identifiers, hostnames, internal URLs and step-by-step attack paths. Security findings are written as
> control gaps with their remediation. Anything more specific belongs in a private channel.

**Evidence labels used throughout**

| Label | Meaning |
| --- | --- |
| **[S] strong** | Data: controlled studies, large surveys with a published method, incident post-mortems, standards, or several independent first-hand reports that agree. |
| **[P] practitioner** | Credible first-hand experience: forum threads (HN, Reddit, lobste.rs), independent engineers' blogs, and engineering blogs of companies describing systems they run but do not sell. |
| **[V] vendor** | A vendor talking about its own product, vendor-funded "research", marketing and listicles. Treated as hypotheses, not facts. |

---

## 1. Executive summary

1. **Our pre-merge analysis layer already matches what the evidence recommends — keep it.** Mutation testing on changed functions, architecture contracts, a boot smoke against real dependencies and one consolidated PR report are what Google's mutation research and Thoughtworks' Radar 34 recommend [29][10].
2. **None of it is enforced.** No sampled repo has a branch rule on `main`, and the company services deploy on push to `main` without waiting for CI. Making the existing checks required is the best value-per-hour change available.
3. **The largest risk is the agent runtime, not code style.** Fleet agents run unattended with permission checks bypassed, in a shared working copy, with the host's environment and open network. Claude Code's own docs reserve that mode for "isolated containers and VMs only" [52]; Stripe and Monzo isolate agents before anything else [67][69].
4. **Supply chain is the most active attack surface of 2025–26** (tj-actions, Nx weaponising local AI CLIs, Trivy → LiteLLM on PyPI) [39][40][41][42]. SHA-pinned actions, OIDC, immutable images and a 3–7 day dependency cooldown are cheap. This contradicts the "always the latest version" preference: adopt "latest after a cooldown".
5. **Agents game what they are measured by** (reward hacking, deleting failing tests) [31][32], and `CLAUDE.md` rules are not enforcement [51]. Add a deterministic anti-tampering check on gates, baselines and tests, plus a fail-to-pass check for new tests.
6. **Owner hypothesis "deterministic layers over an AI reviewer": mostly supported, with a caveat.** Generic review bots are noise (0.9–19% of valid AI comments acted on vs 60% for humans) [13], but precision-engineered reviewers work at scale: Uber reports 65% of comments addressed, Cloudflare reviewed ~48k MRs in a month at ~$1 each [17][18]. Run one shifted-left, high-severity-only pass with a kill criterion, never a comment stream.
7. **Owner hypothesis "PR size is meaningless": right as a productivity metric, wrong as a risk control.** "Working in small batches" is one of DORA's seven AI capabilities [2]; our typical agent PR in drawdoro/condodraw is 2–3k changed lines merged ~6 minutes after opening. Median + p90 for time metrics is sound and already in use.
8. **Post-deploy is our weakest layer:** mutable `:latest` images, no automatic rollback, no SLO burn-rate alerts. Temporal workers need worker versioning and replay tests, not HTTP canaries [81][82].
9. **Our production agents confirm the deterministic-first stance:** 21 of 32 recorded Hulk eval cases are LLM false positives, and a Visão auto-PR used an un-imported exception [92][93]. Page only on deterministic probes; keep LLM output advisory.
10. **Measure agent outcomes (first-pass CI, rework, reverts, change failure rate), not lines or PR counts.** Do not adopt inline AI review bots, agent swarms, heavyweight spec frameworks for small tasks, or autonomous AI remediation in production.

---

## 2. Our current state

### 2.1 Scope and method

Read-only inspection, on 2026-10-03, of the template and of six repositories that apply it, plus the Jarvis
fleet code that dispatches the agents:

| Repo | Nature | Visibility | Notes |
| --- | --- | --- | --- |
| `py-awesome` (template) | FastAPI template | public | The reference pipeline. |
| `drawdoro` | Diagramming tool (FastAPI + React + MCP server) | public | Most evolved application of the template. |
| `condodraw` | Company fork of drawdoro | internal | Same pipeline as drawdoro, deployed to the company Kubernetes cluster. |
| `jarvis` | Personal assistant and agent-fleet orchestrator | private | Also the only repo with an automated pre-deploy smoke and a rollback workflow. |
| `hulk` | Production QA agent (LLM QA suites + deterministic synthetic probes) | internal | Validation pipeline adopted on 2026-10-03. |
| `visao` | Production monitoring agent (Sentry → LLM analysis → tickets, alerts, auto-PRs), Temporal-based | internal | Validation pipeline adopted on 2026-10-03. |
| `astrodoro` | Desktop app (camera/astronomy) | public | Not a backend; included because it applies the same ideas differently. |

Method: configuration files, workflows and scripts in each repo; GitHub API for branch rules, security settings
and repository variables; `gh` for the last ≤60 merged PRs and ≤30 CI runs per repo [94]. The core
money-moving services (Pix, boleto, CNAB) were **not** in scope: what follows describes the template and the
repos above, not the bank's core systems.

### 2.2 How agents work (authoring side)

- **Instruction files.** `CLAUDE.md` with `AGENTS.md` as a symlink (template, drawdoro, condodraw): commands,
  architecture rules, a mandatory pre-PR checklist and "personal preferences". hulk/visao have a project-overview
  `CLAUDE.md` plus the validation commands; astrodoro's `CLAUDE.md` points to `CONTRIBUTING.md`. The template's
  `CLAUDE.md` is ~130 lines.
- **Claude Code project config** (template, drawdoro, condodraw): allow/deny permission lists (deny `rm -rf`,
  force push, `reset --hard`, reading `.env`) and a `PostToolUse` hook that runs `ruff check --fix` + `ruff format`
  on every edited Python file and sends unfixable lint errors back to the agent (exit code 2). Agents: `coder`
  (pinned to Opus) and a read-only `reviewer`.
- **Fleet (Jarvis).** Jobs are queued per project and run as `claude -p` (headless, stream-JSON) with
  `--permission-mode bypassPermissions`. Prompt = generic crew prompt (`coder`, `reviewer`, `tester`, in
  Portuguese) or the repo's own agent, plus a project briefing, a language rule, an autonomy rule ("you run
  alone, often at night; resolve technical problems yourself; only ask for product/scope decisions") and a JSON
  output contract (`summary`, `branch`, `pr_url`). Per job it records cost, input/output/cache tokens and
  duration. Limits: an 8-hour wall-clock timeout and a global concurrency semaphore whose default setting (`0`)
  means unlimited unless configured. Questions to the owner go through an MCP `ask_user`/`notify_user` tool.
- **Workspace model.** One shared clone per project; every job starts with `git checkout <default>` +
  `pull --ff-only` in that same directory, with no per-project lock. There is **no per-job isolation** (no git
  worktree, container or ephemeral VM) and no OS-level sandbox or network egress restriction; the agent process
  inherits the orchestrator service's environment.
- **Verification is delegated to the agent.** The briefing lists the project's verification commands, but the
  orchestrator never runs them itself; for this template the registry declares none. Whether checks ran is
  whatever the agent reports.
- **Crew reviewer prompt** already encodes anti-noise rules: "a correct PR deserves approval and silence";
  "every finding needs a concrete failure scenario, not a generic suspicion".

### 2.3 Pre-merge gates (CI on every PR)

All repos share the same architecture: one CI job per analysis, each wrapped by `scripts/quality_report.py`
(keeps the tool's exit code, stores a JSON fragment), and a final `quality-report` job that upserts **one** PR
comment. CI is fast: median 1–2 min wall-clock per PR run, p90 2–3 min (drawdoro, hulk, jarvis; last 20–30 runs).

| Gate | template | drawdoro / condodraw | jarvis | hulk | visao | astrodoro |
| --- | --- | --- | --- | --- | --- | --- |
| ruff lint + format | ✅ | ✅ | ✅ | ✅ (+ black, isort) | ✅ (+ black, isort) | ✅ |
| mypy | strict | strict | strict | non-strict, per-module baseline | non-strict, per-module baseline | default |
| bandit | `-ll` | `-ll` | `-ll` | `-ll` + baseline | `-ll` + baseline | ✅ |
| vulture (dead code) | advisory in CI | advisory | blocking | advisory | advisory | ✅ |
| xenon (max-absolute / modules / average) | B / A / A | B / A / A | B / A / A | D / C / A | C / B / A | F / B / – |
| import-linter contracts | ✅ 7 contracts | ✅ ids, `exhaustive`, justified baseline | ✅ (custom runner) | ✅ + baseline | ✅ + baseline | ✅ |
| pip-audit | blocking | blocking | blocking | advisory | advisory | – |
| Coverage floor | 80 % line | 80 % line | 90 % line+branch ("ratchet") | 9 % (baseline ratchet) | 9 % (baseline ratchet) | – |
| Mutation testing on PRs | changed **files** in `app/domain`, min 90 | changed **functions** in use cases/services, min 60 | changed functions (selected modules), min 88 | changed functions, min 85 | changed functions, min 75 | changed functions, min 45 |
| Weekly full mutation run | gates at 90 | report only | gates at 88 | gates at 85 | gates at 75 | ✅ |
| Boot smoke | uvicorn `ENV=production`, `/health` + `/ready` (no deps) | clean Postgres + migrations, production guard (refuses to boot with auth off), auth on/off, DB-down → `/ready` 503, MCP server; optional `alembic check` drift | real API + Datastore emulator + simulated inbound channels; **also runs before every deploy** | dashboard + runner vs MySQL (docker) + local Temporal | dashboard + worker vs local doubles, network blocked | CLI + replayed session + GUI offscreen |
| Single Quality Report PR comment | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

Notes:

- Instruction drift already exists: astrodoro's `CLAUDE.md` says mutation testing "is not a PR gate", while its
  `ci.yml` gates PRs on changed functions at 45.
- The mutation "ratchet" is a **static threshold** in practice: no repository sets `MUTATION_MIN_SCORE`, so the
  workflow defaults (45–90) apply and have never been raised. Coverage floors are raised by hand.
- Not present in any repo: secret scanning in pre-commit/CI, a SAST engine beyond bandit (CodeQL/Semgrep),
  container image scanning, SBOM or build provenance, SHA-pinned GitHub Actions, an explicit dependency cooldown
  (Dependabot `cooldown` / uv `exclude-newer`), diff (changed-lines) coverage, property-based tests, API
  contract/compatibility checks, migration-safety linting, and Temporal workflow replay tests (hulk and visao run
  Temporal workers).
- GitHub-side: hulk and visao have GitHub secret-scanning alerts enabled but push protection disabled; the other
  repos have secret scanning disabled.

### 2.4 Merge and deploy

- **No branch protection or ruleset on `main` in any of the sampled repos** (GitHub API `rules/branches/main`
  returns no rules). Every gate in 2.3 is therefore social, not enforced: nothing technically prevents merging a
  red PR or pushing to `main`. In practice the sample shows **0 PRs merged with failing checks** (last ≤60 merged
  PRs per repo), so the discipline holds today, by convention.
- **Deploy = merge.** Every service deploys on push to `main`:
  - hulk, visao (and other company services such as the engineering-metrics dashboard): build and push a
    mutable `:latest` image, `kubectl rollout restart`, `rollout status --timeout=120s`. The deploy workflow is
    **independent of CI** (it does not wait for the CI run on `main`). Two other company repos already use OIDC
    role assumption for cloud access; these deploys use long-lived access keys stored as CI secrets.
  - condodraw: same, plus scale-to-zero → migration Job → apply manifests → restart (planned downtime per deploy).
  - jarvis: smoke → version bump/tag/release → `terraform apply -auto-approve` → self-hosted runner checks out
    the tag, installs the **latest, unpinned** Claude Code CLI, restarts services → 60 s health check. Rollback is
    a manual `workflow_dispatch` to the previous tag; a failed health check does not roll back automatically.
- No progressive delivery anywhere (no canary, blue/green, feature flags, or automated rollback on SLO burn).

### 2.5 Post-deploy (production protection and observation)

- **hulk** (production QA agent): LLM-driven QA suites per API domain on a schedule (agno + MCP tools; scenarios
  that move money use R$ 1.00 and return it), plus a deterministic **synthetic probe** every 5 min (no LLM:
  2xx+JSON = ok, 5xx/timeout = fail, 4xx = inconclusive) over the public API and the web portals (Playwright
  logins). Daily USD budget guard, per-execution token/cost tracking, Slack alerts, signals to the status page.
  Prompt regressions are recorded as YAML **eval cases** (false positives/negatives with root cause), used by a
  `/tune-prompt` command — not executed automatically in CI.
- **visao** (production monitoring agent): Temporal schedules poll Sentry, deduplicate and correlate issues (LLM),
  analyse incidents with an LLM, open Jira tickets, alert on Slack/WhatsApp, and **open fix PRs automatically** in
  the repositories of the services it monitors, gated by an LLM `PRReviewer` (approve/reject). Budget check per
  cycle, status-page signals, weekly reports. Eval cases recorded the same way as hulk.
- **status page** aggregates probe and incident signals.
- Missing: SLOs/error budgets with burn-rate alerting, deploy markers correlated with error spikes, automatic
  rollback, and tracing of the agents' own LLM calls beyond token/cost accounting.

### 2.6 Metrics

- An internal engineering-metrics dashboard already computes DORA metrics (deployment frequency, lead time,
  change failure rate fed by visao incidents, MTTR, MTTD) using **median and p90**, and stores every collection
  run. It does **not** distinguish agent-authored from human-authored changes, so it cannot answer "do agent PRs
  fail more often in production?".
- The fleet stores cost, tokens and duration per agent job, but nothing links a job to the PR's eventual outcome
  (merged as-is, reworked, reverted, caused an incident).

### 2.7 What the PR history says (last ≤60 merged PRs per repo, fetched 2026-10-03)

| Repo | Non-Dependabot PRs | Changed lines, median / p90 | Files, median / p90 | Open → merge, median / p90 | Formal approvals |
| --- | --- | --- | --- | --- | --- |
| drawdoro | 25 | 2,044 / 8,096 | 30 / 110 | 0.1 h / 8.3 h | 0 |
| condodraw | 11 | 3,385 / 8,103 | 60 / 110 | 0.1 h / 0.5 h | 0 |
| jarvis | 26 | 313 / 2,981 | 6 / 31 | 0.2 h / 2.3 h | 0 |
| hulk | 11 | 40 / 5,667 | 2 / 30 | 2.7 h / 21.6 h | 6 of 11 |
| visao | 4 | 5,878 / 26,302 | 36 / 166 | 2.4 h / 2.9 h | 2 of 4 |

Dependabot is the majority of merged PRs in hulk (49/60), visao (47/51) and jarvis (34/60). Changed lines include
lockfiles and generated files, so they overstate hand-reviewable code; even so, in drawdoro and condodraw the
typical agent PR (2–3k changed lines, 30–60 files) is merged about six minutes after it is opened. Whatever human
review happens there cannot be a line-by-line reading; the deterministic gates are doing almost all of the work.
Agent PRs are opened with the owner's own GitHub identity, so GitHub sees them as human-authored and
self-merged.

---

## 3. Market landscape

### 3.1 Verdicts on the owner's working hypotheses

| Hypothesis | Verdict | Evidence |
| --- | --- | --- |
| **Prefer deterministic validation layers over an AI reviewer commenting on PRs** (fear of pointless back-and-forth). | **Supported for generic review bots; partly contradicted for engineered reviewers.** Deterministic gates first is also the stance of Google SRE, Stripe and Thoughtworks [85][68][10]. But two first-party systems at scale report useful AI review when it is precision-tuned (graded, deduplicated, severity-gated, one consolidated comment) [17][18]. The back-and-forth fear is real for naive bots: non-deterministic findings per run, comment streams on every push [19][13]. | [S] TSE 2026: valid AI comments addressed 0.9–19.2% vs 60% for human comments [13]; ICSE-SEIP 2025: 73.8% resolved but PR closure time 5h52 → 8h20 [12]; agent-only reviewed PRs merge 45% vs 68% [14]. [P] Uber 65% addressed / 75% useful [17]; Cloudflare 48,095 MRs in 30 days, $1.19 per review, 0.6% "break glass" [18]. [V] Anthropic: <1% of findings marked incorrect [16]. |
| **PR size / lines of code are meaningless with AI-written code.** | **True as a productivity metric; false as a risk and reviewability control.** Thoughtworks puts "coding throughput as a measure of productivity" in *Caution* [10], so LOC/PR counts as output measures should go. But DORA 2025 lists "working in small batches" among the seven capabilities that amplify AI's benefits [2], and Google's review culture rests on small changes (median 24 lines) [21]. drawdoro's median agent PR is ~85× Google's median change and is merged in minutes (2.7). | [S] DORA AI capabilities [2]; Google 9M reviews [21]. [V] Faros: high AI adoption +154% PR size, +91% review time [6]. [P] reviewers burning out on 5,000-line AI PRs [26][24]. |
| **Median + p90 for time metrics.** | **Supported.** Time-to-merge and recovery-time distributions are long-tailed (our open→merge p90 is 8–80× the median, 2.7), so means mislead. Already implemented in the metrics dashboard (2.6). | [P] our own distributions [94]; no source found arguing for means over percentiles for these metrics. |

### 3.2 What the aggregate data says about AI-assisted delivery

- **AI raises throughput and lowers stability unless control systems are strong** [S]. DORA 2025 (≈5,000
  respondents): AI adoption now correlates positively with throughput but still negatively with delivery stability;
  "without robust control systems, like strong automated testing, mature version control practices, and fast
  feedback loops, an increase in change volume leads to instability" [1]. Its seven AI capabilities include strong
  version control (frequent commits, frequent use of rollback) and small batches [2].
- **Self-reported speed-ups are unreliable** [S]. METR's RCT found experienced OSS developers 19% *slower* with
  early-2025 AI while believing they were ~20% faster [4]; its late-2025 follow-up suggests speed-ups now (point
  estimates −18% and −4% time, wide intervals) but says selection effects make the data "very weak evidence" and
  time accounting breaks when developers run several agents at once [5].
- **Volume rises, review becomes the bottleneck** [V/P]. Faros' telemetry (10k devs): +98% merged PRs, +91% review
  time, +9% bugs per developer [6]. Anthropic says code output per engineer grew 200% and only 16% of PRs got
  substantive review before its review tool [16]. Monzo: "the bottleneck moves from 'find an engineer with
  capacity' to 'find a reviewer'" [69].
- **Trust is low** [S]: 46% of developers distrust AI accuracy vs 33% who trust it, which Stack Overflow calls an
  all-time low [7]; in DORA 30% report little or no trust, slightly fewer than the year before [1]. GitClear reports more duplication and less refactoring in AI-era code [8] [V].
- **DORA now has five delivery metrics**: lead time, deployment frequency, failed-deployment recovery time
  (throughput) and change failure rate plus **rework rate** — unplanned deployments caused by production issues
  (instability) [3].

### 3.3 Gating AI-written code before merge

**Deterministic gates wired into the agent loop ("feedback sensors").** [S/P] Thoughtworks places "feedback sensors
for coding agents" (compilers, linters, structural tests, test suites wired so failures trigger self-correction,
ideally before commit) and "mutation testing" in *Trial*, and "architectural fitness functions" are its named
countermeasure to "codebase cognitive debt" (*Caution*) [10]. Stripe's agents ("minions", >1,000 merged PRs per
week, 1,300 by the second post, at a company moving >$1T/year) run inside "blueprints" that interleave deterministic steps ("always lint
changes at the end of a run") with agent steps, and cap CI at one or two rounds because returns diminish [67][68].
One of Google SRE's stated principles for agentic operations: processes already automated with classic non-AI
systems do not need to be replaced [85]. **Where we stand:** ahead on the analyses themselves; behind on enforcement (2.4)
and on running the checks outside the agent's control (2.2).

**Mutation testing.** [S] Google's production system mutates only changed lines during code review, at most one
mutant per line, suppresses "arid" nodes using developer feedback and shows survivors as review findings with
"Please fix"/"Not useful" links — no score threshold (760k changes, 2M mutants reported) [29]. Meta's ACH uses an
LLM to generate concern-specific mutants and then tests that kill them; engineers accepted 73% of the tests [30].
Thoughtworks calls mutation testing "the most honest signal" against "perpetually green" AI-written tests [10].
Practitioners cite it as the tool that catches tests that pass for the wrong reason [25]; Trail of Bits reports a
fund-draining vulnerability that coverage missed and mutation testing found, and warns that triage is the hard
part: clustered surviving mutants signal real gaps, isolated operator mutants in utilities are mostly noise [96].
Meta now lets engineers describe a compliance fault in plain text and has an LLM generate the matching mutants and
the tests that catch them [97]. **Where we stand:** changed-function mutation on PRs (drawdoro, hulk, visao,
jarvis, astrodoro) is the practice Google and Thoughtworks describe; the template still mutates whole files;
thresholds are percentages over small denominators, unlike Google's per-mutant findings.

**Test integrity: agents optimise against the tests.** [S] METR found o3 reward-hacking in 30% of runs on tasks
whose scoring code it could see (0.7% elsewhere), sometimes by modifying tests or graders [31]; ImpossibleBench
measures agents deleting or special-casing failing tests and shows test access and feedback loops change cheating
rates [32]. Anthropic's long-running-agent harness found agents declaring features done without end-to-end verification and
had to forbid editing tests ("it is unacceptable to remove or edit tests") [64]. Claude Code's documentation is
explicit that instructions in `CLAUDE.md` "shape what Claude tries to do, but they don't change what Claude Code
allows" [51]. Willison's bar: every change ships with a test "that should fail if you revert the implementation"
[24] — the same fail-to-pass signal SWE-bench uses [37]. A first-hand report shows the failure mode concretely: a
test factory that silently skipped the code path and a base test class that disabled `Decimal` assertions kept the
suite green while the code did nothing [25] [P]. **Where we stand:** we rely on instructions ("never weaken tests,
never relax contracts"); baselines "only shrink" by convention in hulk/visao; nothing checks it.

**Property-based and API-contract testing.** [S] An agent writing Hypothesis property tests across 100 popular
Python packages produced bug reports that were 56% valid (86% for the top-ranked), including numerical-precision
bugs; the authors reported bugs with patches to NumPy and cloud SDKs, three of which were merged [33].
Schemathesis derives property-based API fuzzers from OpenAPI and found 1.4–4.5× more unique defects than the
second-best tool across 16 services (tool authors' evaluation) [34]. `oasdiff` flags breaking OpenAPI changes in
CI [35]. **Where we stand:** absent, although money/rounding and fixed-width file formats (CNAB) are textbook
property-test targets and FastAPI already publishes an OpenAPI schema.

**AI code review: evidence for and against.**
- *Against generic bots* [S]: 16 GitHub-Action reviewers, 22k comments — valid AI comments addressed 0.9–19.2%
  (best tool 19.2%) vs 60% for human comments; concise, hunk-level, manually triggered comments did better [13].
  Industrial study (Qodo PR-Agent): 73.8% of comments resolved, but PR closure time grew from 5h52m to 8h20m, with
  "faulty reviews, unnecessary corrections, and irrelevant comments" [12]. PRs reviewed only by review agents
  merged at 45% vs 68% for human-reviewed ones; 12 of 13 agents had average signal ratios below 60% [14].
- *For engineered reviewers* [P]: Uber's uReview covers >90% of ~65k weekly diffs; 75% of comments rated useful,
  65% addressed (vs 51% for human comments) — achieved with a grader prompt, confidence thresholds per category,
  category pruning and deduplication; third-party tools failed on Uber code with "many false positives" [17].
  Cloudflare runs up to seven specialised reviewers plus a coordinator that deduplicates, drops nitpicks and posts
  one structured comment; 131,246 runs on 48,095 MRs in 30 days, median 3m39s, $1.19 average, override needed on
  0.6% of MRs, tiered by diff size, and a dedicated reviewer that flags stale `AGENTS.md` files [18].
- *Trend* [S]: agent-reviews-agent loops are growing fast — cross-product AI review of AI-authored PRs grew by more
  than two orders of magnitude between 2025-Q1 and 2025-Q3 in public GitHub data [15].
- *Vendor claims* [V]: Anthropic's multi-agent Code Review: substantive comments on 54% of PRs (from 16%), <1% of
  findings marked incorrect, ~20 minutes and $15–25 per review, never approves [16].
- *Practitioners disagree* [P]: some find Claude's review ~50% useful and orthogonal to human findings; others
  report non-deterministic findings that create "half a dozen commits" and argue that bug-finding is the author's
  job [19]. A recurring suggestion is to run the AI review **before** the PR is opened, to cut noise [20].
- **Synthesis:** the owner's instinct is right about comment-stream bots; the evidence supports a single,
  severity-gated, consolidated pass whose usefulness is measured (addressed rate) and that can be switched off.

**Change size and human review of AI diffs.** [S/P] Google: median change 24 lines; "a correlation between change
size and review quality is acknowledged" [21]. The old SmartBear/Cisco vendor study puts the effective review
window at 200–400 LOC [22] [V]. Practitioners: review is "the natural bottleneck" of parallel agents, and code that
"started from your own specification is a lot less effort to review" [23]; giant untested AI PRs dumped on
reviewers are "a dereliction of duty" [24]; reviewers report burnout and "vibe reviewing" summaries [26]; "review
attention becomes the scarce resource ... smaller PRs, behavior-level tests" [27]. LLM-invented vocabulary adds
review load; teams keep a checked-in glossary [28]. Thoughtworks proposes **first-pass acceptance rate** instead of
throughput [10]. GitHub itself now requires one extra approval when its Copilot agent opens a PR that is not
attributed to a person, because the assumption that "the person who wrote it and the person who approved it" are two
people stops holding (public preview) [91].

**Supply chain.** [S]
- *Hallucinated packages:* 576k generated samples across 16 LLMs: ≥5.2% (commercial) and 21.7% (open models) of
  package references were hallucinated, 205,474 unique fake names [38].
- *Compromised CI components:* tj-actions/changed-files tags were re-pointed to secret-dumping code (CVE-2025-30066)
  [39]; in March 2026 76 of 77 `trivy-action` tags were force-pushed to credential-stealing malware [40], which led
  to malicious LiteLLM releases on PyPI live for ~40 minutes [41]. Pinning to a full commit SHA protects against
  re-pointed tags; GitHub now lets orgs *require* SHA pinning [47]; `zizmor` statically finds unpinned or
  injectable workflow steps [48].
- *AI CLIs as attack payload:* the Nx "s1ngularity" malware (Aug 2025) tried to use locally installed Claude/Gemini
  CLIs to hunt for secrets [42].
- *Cooldowns:* most compromised releases are caught within hours to days, so waiting N days before adopting a
  release is "free, easy, and incredibly effective" [43][45]; Dependabot made a 3-day cooldown the default for
  version updates on 2026-07-14 [46]; uv supports a relative `exclude-newer` [45]. **Disagreement** [P]: cooldowns
  "free-ride" on early adopters and the real fix is registry-side [44]; the HN reply consensus is that mature
  organisations always waited and risk tolerance legitimately differs [44].
- **Implication for the "latest version" preference:** keep upgrading continuously, but adopt a release only after
  a cooldown (security fixes exempt). Agents that run `uv add`/`uv lock --upgrade` bypass Dependabot entirely, so
  the cooldown must live in uv's config too.

**Secrets and SAST.** [V with data] GitGuardian measured a 3.2% secret-leak rate in Claude Code-assisted public
commits vs a 1.5% baseline, and 24,008 secrets in MCP config files [49]. Veracode reports insecure code in 45% of
generation tasks across 100+ models [50]. A practitioner collection of incidents includes an agent hard-coding a
cloud API key into Markdown that was pushed publicly ($30k of fraud) [59] [P, second-hand]. Push-time secret
scanning and pre-commit hooks are the standard countermeasure; our bandit + pip-audit cover neither.

**Database migrations and workflow determinism.** [S/V-doc] `atlas migrate lint` flags destructive,
backward-incompatible, data-dependent and locking migrations for MySQL and Postgres in CI [83]; squawk does the
same for Postgres. Agent incidents that destroyed data despite explicit instructions (Replit, July 2025) [61] and an
agent that chose to "delete and recreate" an environment at AWS (FT, Feb 2026; details paywalled) [62] are the
cautionary tales. Temporal's own guidance is to download a representative set of production histories and **fail
CI** if replaying them against new workflow code raises a non-determinism error [81]; Worker Versioning (pinned
workflows, ramping versions) is its deployment-time safety net [82]. **Where we stand:** drawdoro's smoke can run
`alembic check` (opt-in); no migration lint; no replay tests in the Temporal-based repos.

### 3.4 Protecting production after merge

- **Progressive delivery and rollback** [S/P]. The SRE workbook's multiwindow, multi-burn-rate alerts are the
  canonical way to defend SLOs [77]; Argo Rollouts/Flagger automate canary analysis and abort [78]. A first-hand
  failure: a Flagger canary whose metrics query returned "no data" sat suspended at 20% traffic instead of rolling
  back — ~35 minutes of customer impact; the lessons were "roll back manually first" and "make no-data fail
  safe" [79]. Canaries are hard when work arrives through third-party webhooks or queues [80] — exactly the shape of
  Pix webhooks, CNAB batches and Temporal workers, where worker versioning and feature flags (ops toggles as kill
  switches [84]) fit better than traffic splitting. DORA: frequent use of rollback amplifies AI's benefits [2].
- **AI SREs and automated remediation** [P, contested]. Google runs agentic alert handlers but with explicit
  principles: keep classic automation where it works, agents need SLOs and fallbacks, "transparency over black-box
  automation" [85]. Experienced SREs are blunt: Limoncelli stopped evaluating AI SRE tools after finding them "all
  crap" [86]; Hebert warns the framing treats incidents as noise to paper over instead of learning [87]. Our own
  Visão data (severity over-classification, an auto-PR with an un-imported exception, $8 spent on a trivial issue)
  supports keeping LLM analysis advisory [93].
- **Production QA agents and synthetic monitoring** [P, ours]. Hulk already follows the principle Google states — a
  deterministic probe alongside the LLM suites. Its eval log shows why the split matters: 21 of 32 recorded cases are
  LLM false positives (async timing, invented query parameters, missing domain context) [92].
- **Observability of agents** [V-doc]. Claude Code exports OpenTelemetry metrics (sessions, cost, tokens, commits,
  PRs, tool decisions) and beta traces linking prompts to API calls and tool executions [70]; Thoughtworks lists
  "ignoring durability in agent workflows" under *Caution* [10].
- **Model and toolchain drift** [S/P]. Anthropic's own post-mortem: three infrastructure bugs intermittently
  degraded Claude's output quality for weeks in Aug–Sep 2025 [71]; in April 2026 practitioners reported
  regressions in Claude Code (1,364-point HN thread; a third-party tracker reported nominal, so causation is
  contested) [72]. Subscription quotas also changed under heavy automated use [73]. One commenter put it well: the
  unit of trust is "Claude Code running on your codebase ... that instance has a behavioral history ... most teams
  aren't [measuring it]" [27].

### 3.5 Working with agents

- **Instruction files** [S/P]. ETH Zurich found that context files do not generally improve task success and add
  >20% inference cost; agents follow the instructions, but repository overviews do not help — context files are
  useful for *non-standard* practices [63]. Thoughtworks: "curated shared instructions" (*Adopt*) but "agent
  instruction bloat" (*Caution*), and hand-written beats LLM-generated [10]. Practitioners add an instruction only
  after an observed failure, then re-run to confirm it helps [63]; keep per-directory files lean; keep a glossary
  [28]. Cloudflare built a reviewer just to flag stale `AGENTS.md` files because they "rot incredibly fast" [18].
- **Hooks and permissions** [V-doc/P]. Deny rules and `PreToolUse` hooks are enforced by the harness in every
  mode; allow rules do nothing under `bypassPermissions`, which the docs reserve for isolated containers/VMs run
  as non-root; the newer "auto" mode puts a classifier in front of risky actions (e.g. merging an unapproved PR,
  disabling CI, pushing secrets out) and is available to headless sessions on recent versions [51][52].
  Practitioners' hook stories — a wiped home directory, a leaked key — are why deterministic hooks beat prompts
  [59]. Repo-controlled `.claude/settings.json`
  hooks were themselves an RCE vector until fixed (CVE-2025-59536, CVE-2026-21852) [55].
- **Isolation is the default for unattended agents** [S/P]. Anthropic's sandbox (filesystem + network isolation,
  credentials kept outside, git via a scoped proxy that only pushes to the configured branch) cut permission
  prompts 84% internally [53]. Stripe's minions run on devboxes "isolated from production resources and the
  internet, so we can run minions on devboxes without human permission checks" [67]. Monzo, a regulated bank,
  deploys its agent "well away from all the services we use to run the bank", picks access per task and gives it
  a single HTTP proxy so secrets stay isolated [69]. Thoughtworks: sandboxing is "a sensible default rather than
  an optional enhancement" (*Trial*) [10]. Caveat [P]: sandboxes are necessary but not sufficient — useful agents
  need information access, and isolation alone does not make an agent trustworthy [58]. The steady stream of
  "agent deleted my files" reports (one with ~4,800 upvotes in Sept 2026) converges on the same advice: isolated
  environments, small commits, backups the agent cannot reach [60].
- **Prompt injection through content the agent reads** [S]. Simon Willison's "lethal trifecta" — private data,
  untrusted content and an exfiltration channel in one agent — is the working threat model [54]. Demonstrated
  instances: a public GitHub issue steering an agent with the official GitHub MCP into leaking private repos [56];
  untrusted issue/PR text injected into AI agents running in CI workflows ("PromptPwnd"), patched in Google's own
  Gemini CLI repo [57].
- **Orchestration patterns that work** [P]. One-shot agents inside deterministic blueprints with bounded CI rounds
  (Stripe) [68]; feature lists + progress files + commit per feature + end-to-end checks for long runs (Anthropic)
  [64]; research → plan → implement with human review concentrated on the research and plan artefacts
  (HumanLayer) [65]. Spec-driven *tools* are overkill for small tasks ("I'd rather review code than all these markdown files") [66];
  Thoughtworks keeps spec-driven development in *Assess* [11] and agent swarms in *Caution* [10].
- **Measuring productivity honestly** [S]. Perception is unreliable [4][5]; LOC and PR counts are a *Caution*
  item [10]; DX's framework measures utilisation, impact and cost together [9] [V]. The defensible leading
  indicator is **first-pass acceptance** (how often agent output merges without rework), tied to DORA's change
  failure and rework rates [10][3].
- **Human costs** [P, opinion]. Practitioners describe "slop, alienation, deskilling and team fallout" when agents
  take over a codebase, and see "no solution in sight" [74]; Thoughtworks names the same risk "codebase cognitive
  debt" and prescribes feedback sensors, tracking cognitive load and architectural fitness functions [10].
- **Regulated and fintech practice** [S/P]. Stripe (payments) and Monzo (bank) keep a human reviewing every agent PR
  (Monzo: an engineer "reviews and merges") and isolate the agent runtime [67][69] — though practitioners doubt that
  1,300 agent PRs a week get more than rubber-stamp review and read such posts partly as recruiting [98]. The
  Linux kernel requires the human submitter to review all AI-generated code and attribute it with an
  `Assisted-by` tag [75]; Ghostty requires disclosure [76].
  In Brazil, CMN Resolution 4.893/2021 requires controls for access, leak prevention, periodic vulnerability scans
  and **traceability**, applied "in the development of secure information systems and in the adoption of new
  technologies" [88]; BCB Resolution 85/2021 is the equivalent rule for payment institutions (its text was not
  reviewed here) [89]. PCI DSS 6.2.3.1, where card data is in scope, requires that manual code reviews, when used,
  be done by someone other than the author and approved by management before release [90]. Agent PRs
  opened under the owner's identity and self-merged (2.7) weaken both traceability and separation of duties.

---

## 4. Gap analysis

| Area | Market practice (evidence) | Us today | Gap | Decision |
| --- | --- | --- | --- | --- |
| Static analysis, types, complexity, dead code | Standard feedback sensors [10] | ruff, mypy strict, bandit, vulture, xenon in hooks and CI | None (relaxed baselines in hulk/visao are a legitimate adoption path) | **Keep** |
| Architecture fitness functions | Thoughtworks countermeasure to cognitive debt [10] | 7–9 import-linter contracts, "fix the import, not the contract" | None | **Keep** |
| Mutation testing | Changed lines only, findings not scores (Google) [29]; Radar *Trial* [10] | Changed functions on PRs in 5 repos; template uses changed files; static thresholds never raised | Small: template lags; % over tiny denominators | **Refine** (R11) |
| Boot smoke with real dependencies | Agents must verify end-to-end [64] | Strong in drawdoro (migrations, prod guard, DB-down), jarvis (pre-deploy) | Template smoke has no deps by design | **Keep** |
| One consolidated PR report | Cloudflare/Uber post one structured comment [17][18] | Quality Report in every repo | None | **Keep** |
| Enforcement of gates | Required status checks / rulesets [91]; deploy depends on CI | No branch rules anywhere; company deploys ignore CI | **Large** | **Fix first** (R1) |
| Gate and test tampering | Agents reward-hack tests [31][32]; instructions ≠ enforcement [51] | Instructions only | **Large** | **Fix first** (R3) |
| Fail-to-pass for new tests | SWE-bench signal [37]; Willison [24] | Absent | Medium | **Fix first** (R3) |
| Agent runtime isolation | Containers/VMs/sandbox for unattended agents [52][53][67][69] | Bypass mode on a shared host, shared clone, inherited env, open network | **Large** | **Fix first** (R5) |
| Deterministic verification outside the agent | Stripe blueprints, bounded CI rounds [68] | Agent self-reports; no verify commands registered for the template | Large | **Fix first** (R4) |
| Supply chain (actions, packages) | SHA pinning [47], zizmor [48], cooldowns [43][46], OIDC | Tag-pinned actions, no explicit cooldown, long-lived keys in some deploys, unpinned agent CLI | **Large** | **Fix first** (R2) |
| Secrets | Push protection + pre-commit scanning [49] | Alerts only in 2 repos; nothing in hooks/CI | Medium | **Fix** (R2) |
| Change size / reviewability | Small batches (DORA) [2]; Google [21] | 2–3k-line agent PRs merged in minutes | Large | **Adopt as risk control** (R7) |
| AI review | Precision-engineered single pass works; bots are noise [13][17][18] | Reviewer agent exists, not wired into the flow | Small | **Pilot, shift-left, with kill criterion** (R10) |
| Two-person rule and traceability | Human reviews/merges every agent PR [67][69]; GitHub adds an approval for unattributed Copilot agent PRs [91]; CMN 4.893 [88] | Agent PRs under owner identity, self-merged, no job metadata | Medium (large for bank services) | **Fix** (R8) |
| Property-based / API contract tests | Agentic PBT [33], Schemathesis [34], oasdiff [35] | Absent | Medium | **Adopt for money logic and public APIs** (R13) |
| Migrations | Migration lint [83], expand/contract | Opt-in `alembic check` in drawdoro | Medium | **Adopt** (R9) |
| Temporal | Replay tests in CI [81], worker versioning [82] | Absent in hulk/visao | Medium | **Adopt** (R9) |
| Deploy safety | Immutable artifacts, rollback, SLO burn alerts [77][2] | `:latest` + restart; manual rollback (jarvis only) | **Large** | **Fix** (R6, R14) |
| Production agents | Deterministic paths for paging; AI advisory [85] | Hulk probe deterministic; LLM QA noisy [92]; Visão auto-PRs [93] | Medium | **Harden** (R15) |
| Agent outcome metrics | First-pass acceptance, rework rate [10][3] | DORA with median/p90; no agent attribution | Medium | **Adopt** (R12) |
| Instruction files | Lean, curated, drift-checked [10][18][63] | ~130 lines, one drift found | Small | **Maintain** (R16) |
| Toolchain drift | Vendor regressions happen [71][72] | Agent CLI auto-upgrades on every jarvis deploy | Medium | **Fix** (R2) |

### 4.1 What already matches or beats the market (do not "fix")

- **The validation layers themselves**: strict typing, complexity limits, import-linter fitness functions and
  mutation testing on changed functions are what Thoughtworks recommends against "perpetually green" AI tests and
  cognitive debt, and what Google does for mutants [10][29].
- **One consolidated, deterministic PR report**: the same anti-noise design Cloudflare and Uber converged on for
  their AI reviewers (one structured comment, severity first) [17][18] — without the LLM.
- **Boot smoke against real dependencies with a production guard** (drawdoro) and **smoke before every deploy**
  (jarvis): matches Anthropic's lesson that agents must verify end-to-end, not just unit-test [64].
- **Feedback inside the agent session**: the `PostToolUse` ruff hook returning errors to the agent is exactly a
  "feedback sensor" (Trial) [10].
- **Anti-noise reviewer prompt** ("a correct PR deserves approval and silence; every finding needs a concrete
  failure scenario") — the rule Cloudflare's coordinator and Uber's grader enforce [17][18].
- **Baselines that only shrink** (hulk, visao): the right adoption path for legacy code; it only lacks a check (R3).
- **Deterministic probe next to the LLM QA in Hulk**, budget guards and per-run cost tracking in both production
  agents and in the fleet: consistent with Google SRE's principles [85].
- **Eval cases recorded from real failures** (hulk, visao): the right raw material; they only need to run
  automatically (R15).
- **DORA metrics with median and p90** (Thoughtworks *Adopt* for DORA metrics) [10][3].
- **Fast CI** (median 1–2 minutes): keeps the agent feedback loop short; Stripe likewise surfaces lint failures at
  push time rather than waiting for CI [67].

---

## 5. Prioritized recommendations

Ordered by value ÷ effort, with risk reduction weighing in for the shortlist. Effort assumes one engineer
driving agents. "Impact" is about expected reduction of defects, incidents or exposure.

### Do first (next 2–3 weeks)

| # | Recommendation | Impact | Effort | Why first |
| --- | --- | --- | --- | --- |
| R1 | Enforce the gates on `main` and make deploys wait for CI | Very high | Hours | Turns everything in 2.3 from convention into control; zero tooling cost |
| R2 | Supply-chain, secrets and toolchain-pinning bundle | High | 1–3 days | Most active real-world attack class; mostly config |
| R3 | Anti-tampering check for gates and tests + fail-to-pass | High | 2–4 days | The AI-specific failure mode our gates don't cover |
| R4 | Deterministic verification in the fleet orchestrator | High | 2–3 days | Stops trusting the agent's self-report |
| R5 | Isolate fleet agents per job (container/sandbox, scoped credentials, egress allowlist) | Very high | 1–2 weeks | Largest exposure in the whole setup |

---

**R1 — Enforce the gates on `main` and make deploys wait for CI**

- *Evidence:* DORA (version-control practices and rollback amplify AI) [2]; GitHub rulesets [91]; our data: no
  branch rules anywhere, company deploys independent of CI (2.4). [S]
- *Impact:* very high. *Effort:* hours. *Risk:* low — flaky checks can block merges; define a break-glass
  bypass (org admins, audited).
- *How:*
  1. **hulk and visao first**, then condodraw, the metrics dashboard and every bank service: an org ruleset on
     `main` requiring a PR, blocking force-push and deletion, and requiring the CI jobs (`lint`, `quality`,
     `lint-imports`, `smoke`, `mutation`, …) as status checks **from the GitHub Actions app** (any integration with
     write access can otherwise set a status) [91].
  2. Change `deploy-*.yml` from `on: push` to `on: workflow_run` of `CI` on `main` with
     `if: github.event.workflow_run.conclusion == 'success'` (or call the deploy as a job that `needs` all CI
     jobs). jarvis already gates its deploy on smoke.
  3. Public personal repos (drawdoro, py-awesome) can use rulesets on the free plan; jarvis (private, free plan)
     cannot — keep its deploy gated by CI instead.
  4. Template: document the expected ruleset in the README ("Repository settings") so new repos start protected.

**R2 — Supply-chain, secrets and toolchain-pinning bundle**

- *Evidence:* tj-actions, Trivy → LiteLLM, Nx [39][40][41][42]; SHA-pinning policy [47]; zizmor [48]; cooldowns
  [43][45][46] (and the free-rider counter-argument [44]); GitGuardian [49]; vendor regressions [71][72]. [S]
- *Impact:* high. *Effort:* 1–3 days. *Risk:* low; cooldowns delay non-security upgrades by days.
- *How:*
  1. **Template first** (new repos inherit it), then all repos: pin every `uses:` to a full commit SHA with the
     version as a comment (Dependabot keeps SHA pins updated); turn on GitHub's "require SHA pinning" policy for
     the org [47]; add `zizmor` to pre-commit and as a CI analysis in the Quality Report [48].
  2. Cooldown: make Dependabot's 3-day default explicit in `dependabot.yaml` (`cooldown:` with `default-days: 3`
     and `semver-major-days: 7`; security updates are never delayed) and add `[tool.uv] exclude-newer = "7 days"`
     so agent-run `uv add`/`uv lock --upgrade` respect it; exempt an urgent fix with
     `exclude-newer-package = { <package> = false }` and remove the override afterwards [45][46]. Update the `CLAUDE.md` preference from "always the
     latest version" to "the latest version older than the cooldown".
  3. Secrets: add `gitleaks` (or trufflehog) to pre-commit and CI; enable push protection on the org repos
     (hulk/visao already have scanning, without push protection); redact secrets from fleet event logs, which store
     tool inputs.
  4. Deploys (hulk, visao, condodraw, metrics dashboard): OIDC role assumption instead of long-lived keys (copy the
     pattern two company repos already use); tag images with the commit SHA and `kubectl set image`, never `:latest`.
  5. jarvis deploy: pin the Claude Code CLI to an explicit version and upgrade it deliberately (see R5 canary),
     instead of installing `@latest` on every deploy.

**R3 — Anti-tampering check for gates and tests, plus fail-to-pass**

- *Evidence:* reward hacking and test deletion [31][32]; harness rules [64]; "instructions are not enforcement"
  [51]; fail-to-pass [24][37]; tests that lie [25]. [S]
- *Impact:* high. *Effort:* 2–4 days. *Risk:* false positives on legitimate relaxations — allow an explicit,
  human-applied label.
- *How:* a new `gate-integrity` analysis in `scripts/quality_report.py` (**template first**, then drawdoro, hulk,
  visao), deterministic, comparing PR head with base:
  - thresholds must not decrease: `fail_under`, `MUTATION_MIN_SCORE` defaults, xenon grades, mypy `strict`, ruff
    `select`/`ignore`;
  - baselines must not grow: `ignore_imports`, bandit baseline, mypy overrides, vulture allowlists (hulk/visao's
    "baselines only shrink" becomes a check);
  - suppressions must not grow in changed files: `# type: ignore`, `# noqa`, `# nosec`, `pragma: no cover`,
    `pytest.mark.skip/xfail`;
  - deleted test files or test functions fail unless a human applies `tests-removed-approved`;
  - changes to `.github/workflows/**`, `.claude/**`, `scripts/quality_report.py`, `scripts/mutation.py` are listed
    as "gate changes" and require code-owner review where rulesets allow it [91];
  - **fail-to-pass:** for `feat`/`fix` PRs, run the PR's new or changed test files against the base branch code in
    a temporary worktree; at least one must fail there and pass on the PR.

**R4 — Deterministic verification in the fleet orchestrator ("blueprint")**

- *Evidence:* Stripe's blueprints and one-to-two CI rounds [68]; feedback sensors [10]; Anthropic's harness [64];
  Willison's evidence-in-the-PR rule [24]. [P]
- *Impact:* high. *Effort:* 2–3 days. *Risk:* longer jobs.
- *How (jarvis):* after the agent finishes, the orchestrator — not the agent — runs the project's verify commands
  in the job workspace (register them for every project; template-based repos: `make hooks test lint-imports
  smoke`). If red, resume the same session once with the failure output; if still red, open the PR as draft with
  an `agent-checks-failed` label (or don't open it). Require an "Evidence" section in the PR body (commands run and
  their key output). Record per job: first-pass green, number of rounds, cost.

**R5 — Isolate fleet agents per job**

- *Evidence:* Claude Code docs (bypass mode only in isolated containers/VMs, non-root) [52]; Anthropic sandbox
  [53]; Stripe devboxes [67]; Monzo agent bundle [69]; Thoughtworks *Trial* [10]; repo-config CVEs [55]; lethal
  trifecta [54]; AI CLIs as malware payload [42]; sandbox limits [58]. [S]
- *Impact:* very high (security and correctness — concurrent jobs on one project currently share a working copy).
  *Effort:* 1–2 weeks. *Risk:* friction from network allowlists; debugging inside containers.
- *How (jarvis):*
  1. One working directory per job: Claude Code's built-in `claude -p --worktree job-<id>` creates an isolated
     worktree and blocks edits and git commands aimed at the main checkout [95]; headless runs don't clean up, so
     the orchestrator runs `git worktree remove` at the end. Until then, a per-project lock and an explicit
     concurrency limit.
  2. Run each job in a container (non-root image with uv, Python, Node) or under Claude Code's sandbox runtime:
     write access only to the job directory; egress only to the Git host, the model API and a package proxy.
  3. Pass an explicit minimal environment instead of inheriting the service's; GitHub access through a GitHub App
     installation token scoped to the target repo (contents + pull requests, short-lived, never admin). R1's
     rulesets make pushing to `main` impossible anyway.
  4. Keep `bypassPermissions` only inside that boundary — or move to `--permission-mode auto` where available —
     and keep deny rules plus `PreToolUse` hooks for critical paths, pushes to `main` and edits to `.claude/**` and
     `.github/**`.
  5. Before upgrading the pinned CLI/model, run 5–10 historical tasks in the sandbox and compare first-pass CI rate
     and cost (drift canary) [71][72].

### Next (within the quarter)

**R6 — Rollback-ready deploys**

- *Evidence:* DORA rollback capability [2]; failed-canary story [79]; SRE workbook [77]. [S/P]
- *Impact:* high. *Effort:* 1–2 days per deploy pattern. *Risk:* low.
- *How (hulk, visao first; same workflow pattern everywhere):* immutable SHA tags (R2); on failed
  `rollout status`, run `kubectl rollout undo` automatically; after rollout, a post-deploy check (production
  `/ready` plus the relevant Hulk probe) for a few minutes, rolling back on failure; send a deploy marker
  (release) to Sentry so Visão can correlate error spikes with deploys. Make any automated check fail safe on
  "no data". Make jarvis's health-check failure trigger its existing rollback workflow.

**R7 — Reviewability budget (batch size as a risk control, not a productivity metric)**

- *Evidence:* DORA small batches [2]; Google [21]; Faros [6]; practitioners [23][24][26][27]. [S]
- *Impact:* medium-high. *Effort:* ~1 day. *Risk:* more PRs to merge; mitigated by stacked PRs.
- *How:* a Quality Report section counting changed lines and files **excluding** lockfiles, generated code and
  migrations snapshots; above ~400 lines or ~20 files it warns "split or attach a review guide" (not blocking at
  first). Coder prompts (template and fleet): one behaviour per PR, stacked PRs for large work, plan-first for
  anything big (human approves the plan; review then focuses on tests and contracts) [65]. Never report it as
  output or productivity.

**R8 — Two-person rule and audit trail for company repos**

- *Evidence:* Stripe/Monzo human review and merge [67][69]; GitHub's extra approval for unattributed Copilot agent
  PRs [91]; CMN 4.893 traceability [88]; PCI DSS 6.2.3.1 where applicable [90]; kernel attribution [75]. [S]
- *Impact:* high for bank services (audit and separation of duties). *Effort:* 1–2 days. *Risk:* slower merges in
  a small team — who the second reviewer is remains an open question (section 7).
- *How:* open agent PRs from a GitHub App identity, not a personal token; PR body template with job id, requester,
  model and CLI version, prompt summary and the R4 evidence; rulesets requiring one human approval, and
  path-based "required reviewers" for money-moving code, migrations and `.github/**`.

**R9 — Temporal replay tests and migration safety**

- *Evidence:* Temporal docs [81][82]; Atlas [83]; data-loss incidents [61][62]. [S/V-doc]
- *Impact:* high for workflow and database services. *Effort:* 2–4 days. *Risk:* low.
- *How:* hulk/visao (and bank Temporal services): a scheduled job exports recent histories per workflow type; CI
  replays them with `Replayer` and fails on non-determinism; adopt Worker Versioning (pinned workflows, ramping)
  for risky changes. Databases: `atlas migrate lint` (MySQL/Postgres) or squawk in CI; make `alembic check`
  mandatory in the smoke (drawdoro already has it as opt-in); `CLAUDE.md` rule for expand/contract and a
  human-applied label for destructive operations.

**R10 — One shifted-left AI review pass, with a kill criterion**

- *Evidence:* for and against in 3.3 [12]–[20]. [S/P]
- *Impact:* medium (catches logic bugs deterministic tools miss). *Effort:* 1–2 days. *Risk:* noise and cost —
  bounded by design.
- *How:* inside the coder job, before opening the PR, run the existing `reviewer` agent with a fresh context on the
  diff, restricted to bugs with a concrete failure scenario at high/critical severity; the coder fixes them or
  justifies the dismissal in the PR body. No inline comments and no re-review on every push; at most one
  "AI review" section in the Quality Report when a PR leaves draft. Pilot on drawdoro; measure the addressed rate
  (Uber's method [17]) and switch it off if it stays below ~30% after 50 PRs.

**R11 — Mutation and coverage refinements**

- *Evidence:* Google's per-mutant findings [29]; diff coverage [36]; our static thresholds (2.3). [S]
- *Impact:* medium. *Effort:* 1–3 days. *Risk:* low.
- *How:* port drawdoro's changed-function targeting to the template; for hulk/visao (9% global floor) add
  `diff-cover` on changed lines (e.g. ≥85%); turn the "ratchet" into a real one (weekly run writes per-module
  scores to a tracked file via PR; PR job fails on regression); for small denominators, gate on "no unacknowledged
  surviving mutant in changed lines", with an explicit allowlist for equivalent mutants, and rank clusters of
  survivors above isolated ones when triaging [96].

**R12 — Agent outcome metrics in the engineering-metrics dashboard**

- *Evidence:* first-pass acceptance and throughput caution [10]; DORA five metrics [3]; perception gap [4][5];
  instance-level trust [27]. [S]
- *Impact:* high for decisions. *Effort:* 3–5 days. *Risk:* low.
- *How:* identify agent PRs (bot author from R8 or trailer); per repo, agent and model: first-pass CI success
  (R4), human commits before merge, revert or hotfix within 14 days, linked incidents (change failure rate, agent
  vs human), rework rate, cost per merged PR, review time and time-to-merge as median and p90.

### Later (quarter after)

**R13 — Property-based and API-contract tests for money logic and public APIs**

- *Evidence:* agentic PBT [33]; Schemathesis [34]; oasdiff [35]; precision-mismatch report [25]; Meta ACH [30][97]. [S]
- *Impact:* high on the bank's core services. *Effort:* 2–5 days per service. *Risk:* low.
- *How:* template first (Hypothesis in dev dependencies, one example property test, a `CLAUDE.md` rule that
  money, rounding and parsing code needs a property test: round-trip, conservation of totals, idempotency);
  Schemathesis against `/openapi.json` inside the smoke job; `oasdiff` breaking-change check on the public API
  repository. Next step for regulatory invariants: Meta-style concern-driven mutation — describe the fault in plain
  text ("a transfer above the night-time limit is accepted", "a fee is rounded against the customer") and have an
  agent generate the mutant and the test that must kill it [97].

**R14 — SLOs with burn-rate alerting, and progressive delivery where it fits**

- *Evidence:* SRE workbook [77]; Argo Rollouts [78]; canary limits with webhooks/queues [79][80]; worker
  versioning [82]; feature toggles [84]. [S]
- *Impact:* high for customer-facing services. *Effort:* 1–3 weeks. *Risk:* misconfigured automation can make
  incidents longer [79].
- *How:* SLOs for money-moving endpoints and jobs with multiwindow burn-rate alerts; canaries only for
  high-traffic HTTP services, with fail-safe analysis; ops toggles as kill switches for agent-built features;
  worker versioning for Temporal.

**R15 — Harden the production agents (Hulk, Visão)**

- *Evidence:* our eval data [92][93]; Google SRE principles [85]; skeptical SREs [86][87]; prompt-injection
  research [54][56][57]. [S/P]
- *Impact:* medium-high. *Effort:* 1–2 weeks. *Risk:* low.
- *How:* page only on deterministic signals (probe, SLO burn); LLM QA findings go to a triage channel; promote
  recurring LLM checks to deterministic assertions; execute the YAML eval cases in CI whenever prompts or models
  change; Visão opens PRs only with a confirmed root cause and only into repos protected by R1 gates; separate the
  component that reads untrusted text (error payloads) from the one holding write credentials.

**R16 — Instruction hygiene**

- *Evidence:* ETH study [63]; Radar bloat and curated instructions [10]; Cloudflare's AGENTS.md reviewer [18];
  glossary practice [28]. [S/P]
- *Impact:* medium. *Effort:* ~1 day, then upkeep. *Risk:* low.
- *How:* keep the root `CLAUDE.md` short and prescriptive; per-module files for domain rules; a checked-in domain
  glossary (Pix, boleto, CNAB, condominium terms); add an instruction only after an observed failure and confirm
  by re-running; a CI check that commands and paths named in `CLAUDE.md` exist (it would have caught astrodoro's
  drift).

---

## 6. Practices to deliberately NOT adopt

| Practice | Why not | Evidence |
| --- | --- | --- |
| A review bot posting inline comments on every push | Low addressed rates, longer PR cycles, non-deterministic findings that create commit churn — the owner's fear, confirmed for this design | [12][13][14][19] |
| A blocking LLM gate on merge | Non-deterministic gates are flaky by construction; keep LLM review advisory and deterministic checks blocking | [13][19][85] |
| LOC, PR counts or "% of code written by AI" as productivity KPIs | Thoughtworks *Caution*; they reward volume that slows review | [10][6] |
| Agent swarms / many-agent orchestration for delivery work | *Caution* in Radar 34; review remains the bottleneck | [10][23] |
| Heavyweight spec-driven tooling for routine tasks | Overkill for small changes; markdown that nobody reviews; keep plan-first only for big work | [66][11] |
| Autonomous AI remediation in production (agents rolling back, merging or patching on their own) | Experienced SREs reject current tools; Google keeps classic automation and transparency; our Visão data shows confident wrong fixes | [85][86][87][93] |
| Replacing deterministic probes with LLM QA | Most of Hulk's recorded LLM QA issues are false positives | [92] |
| Generic, LLM-generated `AGENTS.md`/`CLAUDE.md` files | No success gain, +20% cost; hand-written, minimal files win | [63][10] |
| Chasing global mutation or coverage percentages | Goodhart; Google surfaces actionable mutants instead | [29] |
| Full service-mesh canary infrastructure for low-traffic internal tools | Cost and new failure modes exceed benefit; rollback plus flags covers it | [79][80] |
| Per-PR preview environments for backend services | The smoke already boots real dependencies in CI; previews mainly help frontend/manual QA (judgement, not studied here) | — |
| Broad formal verification of agent code | Bugs live at boundaries and in test infrastructure; use selectively | [25] |
| Auto-merge of agent PRs in money-moving repos | Separation of duties and traceability; Claude Code's own auto-mode classifier blocks merging unapproved PRs | [52][88][90][91] |

---

## 7. Open questions and what could not be verified

- **Regulatory scope.** Whether the company falls under CMN 4.893/2021 or BCB 85/2021 (or is a service provider to
  an institution that does), and whether any system is in PCI DSS scope, must be confirmed with compliance; the
  text of BCB 85 was not reviewed in detail [88][89][90].
- **Core services not inspected.** The Pix/boleto/CNAB repositories were out of scope; their pipelines may be
  stronger or weaker than the sample.
- **Second reviewer.** R8's two-person rule needs a second qualified human for money-moving paths; in a one-person
  review setup that is an organisational decision, not a technical one.
- **Fleet runtime facts.** The production value of the fleet's concurrency limit and actual job volumes, success
  rates and costs live in the fleet's datastore and were not queried.
- **Vendor and first-party numbers are self-reported:** Anthropic (<1% incorrect findings) [16], Uber [17],
  Cloudflare [18], Stripe [67][68], Monzo [69], Faros [6], GitClear [8], GitGuardian [49], Veracode [50]. The
  academic studies on AI review [12][13][14] mostly cover 2024–2025 tools and may understate current reviewers.
- **Forum data limits.** Reddit could not be read directly; threads were read through the Arctic Shift archive,
  so scores are as archived and some opening posts were removed (e.g. [60]). The AWS incident details [62] are
  behind a paywall and were not verified; the reported agent sandbox escapes cited by [58] were not independently
  verified.
- **Claude Code auto mode in headless jobs** depends on account, model and CLI version [52]; not tested here.
- **Thoughtworks Radar** placements are expert opinion across clients, not measurements [10][11].
- **PR-size numbers in 2.7** include lockfiles and generated files; a precise "reviewable lines" figure needs R7's
  filter.

---

## Appendix A. Sources

Type: **R** research or survey · **F** forum discussion · **B** independent practitioner blog · **E** first-party
engineering report from a company using (not selling) the practice · **V** vendor material (product posts, docs,
vendor research, marketing) · **N** news · **G** standard, regulation, canonical guide or incident advisory ·
**I** internal evidence. Dates are publication dates; "fetched" means a living document read on 2026-10-03.

### A.1 Aggregate data and syntheses

| # | Source | Date | Type | Credibility note |
| --- | --- | --- | --- | --- |
| 1 | [Announcing the 2025 DORA Report](https://cloud.google.com/blog/products/ai-machine-learning/announcing-the-2025-dora-report) (Google Cloud) | 2025-09-23 | R | ~5,000 respondents + 100 h qualitative; survey correlations, not causation. High. |
| 2 | [Introducing DORA's inaugural AI Capabilities Model](https://cloud.google.com/blog/products/ai-machine-learning/introducing-doras-inaugural-ai-capabilities-model) | 2025-09-22 | R | Same survey; capability effects are modelled. High. |
| 3 | [The DORA 4 key metrics become 5](https://cd.foundation/blog/2025/10/16/dora-5-metrics/) (CD Foundation, S. Fenton) | 2025-10-16 | B | Accurate explainer; author works for a deployment-tool vendor. Medium-high. |
| 4 | [METR: early-2025 AI and experienced OSS developers (RCT)](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/) + [HN discussion](https://news.ycombinator.com/item?id=44522772) | 2025-07-10 | R + F | Randomised, small n (16). High for its setting. |
| 5 | [METR: We are changing our developer productivity experiment design](https://metr.org/blog/2026-02-24-uplift-update/) | 2026-02-24 | R | Authors flag strong selection effects. Medium. |
| 6 | [Faros AI: The AI Productivity Paradox](https://www.faros.ai/blog/ai-software-engineering) | 2025-07-23 | V | Telemetry from 10k devs, vendor of analytics. Medium-low. |
| 7 | [Stack Overflow Developer Survey 2025 — AI](https://survey.stackoverflow.co/2025/ai) and [press release](https://stackoverflow.co/company/press/archive/stack-overflow-2025-developer-survey/) | 2025-07-29 | R | Large self-selected survey. Medium-high. |
| 8 | [GitClear: AI Copilot Code Quality 2025](https://www.gitclear.com/ai_assistant_code_quality_2025_research) | 2025-02 | V | Large dataset, vendor methodology. Medium-low. |
| 9 | [DX: Introducing the AI Measurement Framework](https://newsletter.getdx.com/p/introducing-the-ai-measurement-framework) | 2025-07-09 | V | Vendor framework. Low-medium. |
| 10 | [Thoughtworks Technology Radar Vol. 34 (PDF)](https://www.thoughtworks.com/content/dam/thoughtworks/documents/radar/2026/04/tr_technology_radar_vol_34_en.pdf) | 2026-04 | B | Consultancy synthesis across clients; opinion, not data. Medium-high. |
| 11 | [Thoughtworks Radar: Spec-driven development](https://www.thoughtworks.com/radar/techniques/spec-driven-development) | 2025-11 | B | As above. Medium. |

### A.2 AI code review

| # | Source | Date | Type | Credibility note |
| --- | --- | --- | --- | --- |
| 12 | [Cihan et al., Automated Code Review In Practice (ICSE-SEIP 2025)](https://arxiv.org/abs/2412.18531) | 2024-12-24 | R | Industrial, 4,335 PRs. High. |
| 13 | [Sun et al., Does AI Code Review Lead to Code Changes? (IEEE TSE 2026)](https://arxiv.org/abs/2508.18771) | 2025-08-26 (v2 2026-04-25) | R | 22k comments, 178 repos; older bot generation. High. |
| 14 | [Chowdhury et al., From Industry Claims to Empirical Reality](https://arxiv.org/abs/2604.03196) | 2026-04-03 | R | Correlational, OSS. Medium. |
| 15 | [Selvanayagam & Ghaleb, AI-to-AI Code Reviews of GitHub PRs](https://arxiv.org/abs/2608.21311) | 2026-08-21 | R | Descriptive dataset. Medium. |
| 16 | [Anthropic: Code Review for Claude Code](https://claude.com/blog/code-review) | 2026-03-09 | V | Vendor on own product. Low-medium. |
| 17 | [Uber: uReview](https://www.uber.com/us/en/blog/ureview/) | 2025-08 (date from a mirror; original page blocked automated reads) | E | First-party at scale, self-measured. Medium-high. |
| 18 | [Cloudflare: Orchestrating AI Code Review at scale](https://blog.cloudflare.com/ai-code-review/) | 2026-04-20 | E | First-party, detailed numbers. Medium-high. |
| 19 | [HN: There is an AI code review bubble](https://news.ycombinator.com/item?id=46766961) (351 pts, 249 comments) | 2026-01-26 | F | Mixed practitioner views; vendor (Greptile) in thread. Medium. |
| 20 | [HN: Orchestrating AI code review at scale](https://news.ycombinator.com/item?id=48276152) (145 pts) | 2026-05-26 | F | Practitioner reactions. Medium. |

### A.3 Change size and human review

| # | Source | Date | Type | Credibility note |
| --- | --- | --- | --- | --- |
| 21 | [Sadowski et al., Modern Code Review: A Case Study at Google](https://research.google/pubs/modern-code-review-a-case-study-at-google/) | 2018 | R | 9M reviewed changes. High (older, pre-AI). |
| 22 | [SmartBear: best practices for peer code review (Cisco study)](https://smartbear.com/learn/code-review/best-practices-for-peer-code-review/) | 2006 study | V | Vendor, old; widely cited. Low-medium. |
| 23 | [Simon Willison: Embracing the parallel coding agent lifestyle](https://simonwillison.net/2025/Oct/5/parallel-coding-agents/) | 2025-10-05 | B | Experienced, transparent practitioner. Medium-high. |
| 24 | [Simon Willison: Your job is to deliver code you have proven to work](https://simonwillison.net/2025/Dec/18/code-proven-to-work/) | 2025-12-18 | B | As above. Medium-high. |
| 25 | [r/ExperiencedDevs: verifying AI-generated code before production](https://www.reddit.com/r/ExperiencedDevs/comments/1rzq738/) (85 comments) | 2026-03-21 | F | First-hand experiment with concrete bugs. Medium. |
| 26 | [r/ExperiencedDevs: We should refuse to review vibe code PRs](https://www.reddit.com/r/ExperiencedDevs/comments/1t09ayx/) (87 comments) | 2026-04-30 | F | Reviewer experience. Medium. |
| 27 | [r/ExperiencedDevs: code review quality when 80% of PRs are AI-generated](https://www.reddit.com/r/ExperiencedDevs/comments/1tgerh6/) | 2026-05-18 | F | Opening post is promotional; comments are the value. Low-medium. |
| 28 | [Andrew Moffat: Reducing the cognitive load of AI changes](https://amoffat.github.io/blog/cognitive-load.html) + [lobste.rs](https://lobste.rs/s/iwvjr0) | 2026-10-01 | B + F | Practical technique, glossary consensus. Medium. |

### A.4 Testing and verification

| # | Source | Date | Type | Credibility note |
| --- | --- | --- | --- | --- |
| 29 | [Petrović et al., Practical Mutation Testing at Scale: A view from Google (TSE)](https://arxiv.org/abs/2102.11378) | 2021-02-22 | R | 760k changes, 24k developers. High. |
| 30 | [Foster et al., Mutation-Guided LLM-based Test Generation at Meta](https://arxiv.org/abs/2501.12862) | 2025-01-22 | R | Industrial (FSE 2025). High. |
| 31 | [METR: Recent Frontier Models Are Reward Hacking](https://metr.org/blog/2025-06-05-recent-reward-hacking/) | 2025-06-05 | R | Eval transcripts. High. |
| 32 | [ImpossibleBench (arXiv 2510.20270)](https://arxiv.org/abs/2510.20270) | 2025-10-23 | R | Benchmark framework. High. |
| 33 | [Maaz, DeVoe, Hatfield-Dodds, Carlini: Agentic Property-Based Testing](https://arxiv.org/abs/2510.09907v1) | 2025-10 | R | Manual validation of bug reports; Anthropic-affiliated authors. High. |
| 34 | [Hatfield-Dodds & Dygalo: Deriving Semantics-Aware Fuzzers from Web API Schemas (Schemathesis)](https://arxiv.org/abs/2112.10328) | 2021-12 (ICSE 2022) | R | Tool authors evaluating own tool. Medium-high. |
| 35 | [oasdiff](https://github.com/oasdiff/oasdiff) | fetched | V | OSS tool docs. Factual. |
| 36 | [diff-cover](https://github.com/Bachmann1234/diff_cover) | fetched | V | OSS tool docs. Factual. |
| 37 | [SWE-bench: Fail-to-Pass evaluation](https://www.swebench.com/original.html) | 2023–2024 | G | Benchmark method. High. |

### A.5 Supply chain, CI and secrets

| # | Source | Date | Type | Credibility note |
| --- | --- | --- | --- | --- |
| 38 | [Spracklen et al., We Have a Package for You! (USENIX Security 2025)](https://arxiv.org/abs/2406.10279) | 2024-06 / 2025 | R | 576k samples, 16 models. High. |
| 39 | [tj-actions/changed-files compromise, CVE-2025-30066](https://www.sentinelone.com/vulnerability-database/cve-2025-30066/) | 2025-03-14/15 | G | CVE, CISA KEV-listed incident. High. |
| 40 | [Trivy ecosystem supply chain compromise, GHSA-69fq-xp46-6x23](https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23) | 2026-03-19 | G | Maintainer advisory. High. |
| 41 | [LiteLLM: Security update, suspected supply chain incident](https://docs.litellm.ai/blog/security-update-march-2026) | 2026-03-24 | E | Maintainer post-mortem. High. |
| 42 | [Nx: s1ngularity post-mortem](https://nx.dev/blog/s1ngularity-postmortem) | 2025-08/09 | E | Maintainer post-mortem. High. |
| 43 | [William Woodruff: We should all be using dependency cooldowns](https://blog.yossarian.net/2025/11/21/We-should-all-be-using-dependency-cooldowns) + [HN](https://news.ycombinator.com/item?id=46005111) (489 pts) | 2025-11-21 | B + F | Supply-chain security engineer. High. |
| 44 | [Cal Paterson: Dependency cooldowns turn you into a free-rider](https://calpaterson.com/deps.html) + [HN](https://news.ycombinator.com/item?id=47773812) (187 pts) | 2026-04-14 | B + F | Counter-argument and pushback. Medium-high. |
| 45 | [cooldowns.dev](https://cooldowns.dev/) | 2026 | B | Community guide (tool support, uv `exclude-newer`). Medium. |
| 46 | [GitHub changelog: Dependabot default package cooldown](https://github.blog/changelog/2026-07-14-dependabot-version-updates-introduce-default-package-cooldown/) | 2026-07-14 | V | Product change; factual. High for the fact. |
| 47 | [GitHub changelog: Actions policy supports SHA pinning](https://github.blog/changelog/2025-08-15-github-actions-policy-now-supports-blocking-and-sha-pinning-actions/) | 2025-08-15 | V | Product change; factual. |
| 48 | [zizmor docs](https://docs.zizmor.sh/) | fetched | V | OSS tool docs. Factual. |
| 49 | [GitGuardian: State of Secrets Sprawl 2026](https://blog.gitguardian.com/the-state-of-secrets-sprawl-2026/) | 2026-03-17 | V | Large dataset, vendor of secret scanning. Medium. |
| 50 | [Veracode: 2025 GenAI Code Security Report](https://www.veracode.com/blog/genai-code-security-report/) | 2025-07-30 | V | Vendor benchmark. Low-medium. |

### A.6 Agent permissions, isolation and security

| # | Source | Date | Type | Credibility note |
| --- | --- | --- | --- | --- |
| 51 | [Claude Code docs: Configure permissions](https://code.claude.com/docs/en/permissions) | fetched | V | Authoritative for the tool's behaviour. |
| 52 | [Claude Code docs: Permission modes](https://code.claude.com/docs/en/permission-modes) | fetched | V | Authoritative for the tool's behaviour. |
| 53 | [Anthropic: Making Claude Code more secure and autonomous with sandboxing](https://www.anthropic.com/engineering/claude-code-sandboxing) | 2025-10-20 | V | Vendor engineering post. Medium. |
| 54 | [Simon Willison: The lethal trifecta for AI agents](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/) | 2025-06-16 | B | Widely adopted threat model. High. |
| 55 | [Check Point Research: RCE and API token exfiltration through Claude Code project files](https://research.checkpoint.com/2026/rce-and-api-token-exfiltration-through-claude-code-project-files-cve-2025-59536/) | 2026-02-25 | V | Security vendor; CVEs assigned and fixed. High for the facts. |
| 56 | [Invariant Labs: GitHub MCP exploited](https://invariantlabs.ai/blog/mcp-github-vulnerability) | 2025-05 | V | Security vendor research with demo. Medium-high. |
| 57 | [Aikido: PromptPwnd — prompt injection inside GitHub Actions](https://www.aikido.dev/blog/promptpwnd-github-actions-ai-agents) | 2025-12-04 | V | Security vendor; Gemini CLI fix confirms. Medium-high. |
| 58 | [Matthew Green: Is sandboxing sufficient to contain rogue agents?](https://blog.cryptographyengineering.com/2026/09/30/is-sandboxing-sufficient-to-contain-rogue-agents/) + [lobste.rs](https://lobste.rs/s/zcr7in) | 2026-09-30 | B + F | Security professor; argument, cites lab reports. Medium-high. |
| 59 | [paddo.dev: Claude Code Hooks — Guardrails That Actually Work](https://paddo.dev/blog/claude-code-hooks-guardrails/) | 2026-01-08 | B | Second-hand incident stories. Medium-low. |
| 60 | [r/ClaudeAI: Code just deleted 48k files](https://www.reddit.com/r/ClaudeAI/comments/1wl5cgo/) (~4,800 upvotes, 1,375 comments) | 2026-09-20 | F | Opening post removed; comment consensus only. Low-medium. |
| 61 | [The Register: Replit deleted production database](https://www.theregister.com/2025/07/21/replit_saastr_vibe_coding_incident/) + [HN](https://news.ycombinator.com/item?id=44632575) | 2025-07-21 | N + F | Widely corroborated incident. High. |
| 62 | [Financial Times: Amazon service was taken down by AI coding bot](https://www.ft.com/content/00c282de-ed14-4acd-a948-bc8d6bdb339d) | 2026-02-20 | N | Paywalled; details unverified here. Medium. |

### A.7 Working with agents

| # | Source | Date | Type | Credibility note |
| --- | --- | --- | --- | --- |
| 63 | [Gloaguen et al. (ETH Zurich): Evaluating AGENTS.md](https://arxiv.org/abs/2602.11988) + [HN](https://news.ycombinator.com/item?id=47034087) (232 pts) | 2026-02 | R + F | Controlled evaluation; models change fast. High. |
| 64 | [Anthropic: Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) | 2025-11-26 | V | Vendor engineering, candid about failures. Medium. |
| 65 | [HumanLayer: Advanced Context Engineering for Coding Agents](https://www.humanlayer.dev/blog/advanced-context-engineering) | 2025-08-29 | B | Practitioner report from an agent-tooling startup. Medium. |
| 66 | [Birgitta Böckeler: Understanding Spec-Driven-Development](https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html) | 2025-10-15 | B | Hands-on evaluation. High. |
| 67 | [Stripe: Minions, one-shot end-to-end coding agents](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents) | 2026-02-09 | E | First-party, payments company. Medium-high. |
| 68 | [Stripe: Minions — Part 2](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents-part-2) | 2026-02-19 | E | As above. Medium-high. |
| 69 | [Monzo: Building Agent Chip](https://monzo.com/blog/building-agent-chip) | 2026-08-13 | E | First-party, regulated bank. Medium-high. |
| 70 | [Claude Code docs: Monitoring (OpenTelemetry)](https://code.claude.com/docs/en/monitoring-usage) | fetched | V | Authoritative for the tool. |
| 71 | [Anthropic: A postmortem of three recent issues](https://www.anthropic.com/engineering/a-postmortem-of-three-recent-issues) | 2025-09-17 | E | Vendor's own incident post-mortem. High for the facts. |
| 72 | [HN: Claude Code is unusable for complex engineering tasks with Feb updates](https://news.ycombinator.com/item?id=47660925) (1,364 pts) | 2026-04-06 | F | Many reports, causation contested. Medium-low. |
| 73 | [TechCrunch: Anthropic unveils new rate limits for Claude Code](https://techcrunch.com/2025/07/28/anthropic-unveils-new-rate-limits-to-curb-claude-code-power-users/) | 2025-07-28 | N | Reporting of an announcement. High for the fact. |
| 74 | [Alex Martsinovich: The Four Horsemen of Agentic Coding](https://distantprovince.substack.com/p/the-four-horsemen-of-agentic-coding) + [lobste.rs](https://lobste.rs/s/wevegu) | 2026-09-29 | B + F | Opinion; disillusionment signal. Low-medium. |
| 75 | [Linux kernel: AI Coding Assistants](https://docs.kernel.org/process/coding-assistants.html) | fetched | G | Project policy. High. |
| 76 | [Ghostty: AI_POLICY.md](https://github.com/ghostty-org/ghostty/blob/main/AI_POLICY.md) | 2025-08 | G | Project policy. Medium. |

### A.8 Production

| # | Source | Date | Type | Credibility note |
| --- | --- | --- | --- | --- |
| 77 | [Google SRE Workbook: Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/) | 2018 | G | Canonical. High. |
| 78 | [Argo Rollouts: Analysis & Progressive Delivery](https://argo-rollouts.readthedocs.io/en/stable/features/analysis/) | fetched | V | OSS docs. Factual. |
| 79 | [r/devops: Why our canary didn't roll back](https://www.reddit.com/r/devops/comments/1te9r16/) | 2026-05-15 | F | First-hand incident. Medium. |
| 80 | [r/devops: Canary deployment strategy with third-party webhooks](https://www.reddit.com/r/devops/comments/1ltmjre/) | 2025-07-07 | F | Practitioner question. Low-medium. |
| 81 | [Temporal docs: Testing — Python SDK (replay)](https://docs.temporal.io/develop/python/best-practices/testing-suite) | fetched | V | Authoritative for the tool. |
| 82 | [Temporal docs: Worker Versioning](https://docs.temporal.io/production-deployment/worker-deployments/worker-versioning) | fetched | V | Authoritative for the tool. |
| 83 | [Atlas: Verifying migration safety](https://atlasgo.io/versioned/lint) | fetched | V | Tool docs. Factual. |
| 84 | [Pete Hodgson: Feature Toggles](https://martinfowler.com/articles/feature-toggles.html) | 2017 | G | Canonical guide. High. |
| 85 | [Google Cloud: How Google SRE is using agentic AI to improve operations](https://cloud.google.com/blog/products/devops-sre/how-google-sre-is-using-agentic-ai-to-improve-operations) | 2026-05-28 | E | First-party; also sells AI. Medium-high. |
| 86 | [Tom Limoncelli: AI-Driven SRE Tools. Please stop.](https://www.yesthatblog.com/post/0152-ai-driven-sre-tools/) | 2026-02-11 | B | Veteran SRE author; strong opinion. Medium. |
| 87 | [Fred Hebert: The Picture They Paint of You](https://ferd.ca/the-picture-they-paint-of-you.html) | 2026-02-23 | B | Resilience-engineering practitioner. Medium. |

### A.9 Regulation and governance

| # | Source | Date | Type | Credibility note |
| --- | --- | --- | --- | --- |
| 88 | [Resolução CMN nº 4.893 (BCB)](https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?tipo=Resolu%C3%A7%C3%A3o%20CMN&numero=4893) | 2021-02-26 | G | Regulation; Art. 3 §§2–3 read. High. |
| 89 | [Resolução BCB nº 85](https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?tipo=Resolu%C3%A7%C3%A3o%20BCB&numero=85) | 2021-04-08 | G | Regulation for payment institutions; existence verified, text not reviewed. |
| 90 | [PCI DSS v4.0.1 Req. 6.2.3.1 (secondary summary)](https://pcidssguide.com/how-to-perform-code-reviews-for-pci-requirements/) | fetched | G | Secondary source for a standard; check the PCI SSC original. Medium. |
| 91 | [GitHub Docs: Available rules for rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets) | fetched | V | Authoritative for the platform. |

### A.10 Internal evidence

| # | Source | Date | Type | Note |
| --- | --- | --- | --- | --- |
| 92 | hulk `evals/cases/*.yaml` (32 cases, 21 labelled false positives) | 2026-03-28 → 2026-08-31 | I | First-hand, our production QA agent. |
| 93 | visao `evals/cases/*.yaml` (11 cases) | 2026-03-17 → 2026-04-15 | I | First-hand, our monitoring agent. |
| 94 | GitHub API and `gh` queries on the sampled repos (branch rules, security settings, variables, PRs, CI runs) | 2026-10-03 | I | Reproducible from the repos. |

### A.11 Added in the second research pass

| # | Source | Date | Type | Credibility note |
| --- | --- | --- | --- | --- |
| 95 | [Claude Code docs: Run parallel sessions with worktrees](https://code.claude.com/docs/en/worktrees) | fetched | V | Authoritative for the tool (`--worktree`, isolation checks, headless cleanup). |
| 96 | [Trail of Bits: Mutation testing for the agentic era](https://blog.trailofbits.com/2026/04/01/mutation-testing-for-the-agentic-era/) | 2026-04-01 | E | Security firm describing its audit practice; also releases the tools. Medium-high. |
| 97 | [Meta Engineering: LLMs Are the Key to Mutation Testing and Better Compliance](https://engineering.fb.com/2025/09/30/security/llms-are-the-key-to-mutation-testing-and-better-compliance/) | 2025-09-30 | E | First-party follow-up to [30]. Medium-high. |
| 98 | [HN: Minions – Stripe's Coding Agents Part 2](https://news.ycombinator.com/item?id=47086557) (131 pts, 61 comments) | 2026-02-20 | F | Practitioner skepticism about review depth and the post's detail. Medium. |

**Source mix** (98 numbered entries; a blog post and its discussion thread count as two sources): **103 external
sources** — **46 practitioner** (18 forum discussions on HN, Reddit and lobste.rs; 17 independent practitioner
blogs and syntheses, Thoughtworks' Radar included; 11 first-party engineering reports from companies running what
they describe), **26 vendor** (product posts, documentation, vendor research, marketing), **18 research** papers and
surveys, **10** standards, regulations, canonical guides and incident advisories, and **3** news reports — plus 3
internal evidence sets.

## Appendix B. Method and limitations

- **Current state:** read-only inspection of local workspaces and GitHub (`gh`, REST API); no branch was switched
  in any inspected repo.
- **Market research:** DuckDuckGo for discovery, the HN Algolia API for Hacker News threads, the Arctic Shift
  archive for Reddit (direct access was blocked), lobste.rs tag feeds, and direct reading of every cited page.
  Numbers were taken from the primary page wherever it was reachable; when only a secondary summary was
  available, the source is marked as such.
- **Selection bias:** first-party success stories (Uber, Cloudflare, Stripe, Monzo) are written by teams whose
  systems worked well enough to publish; the failure stories come mostly from forums. Both were sought on purpose.
- **Recency:** most material is from June 2025 to October 2026; older sources are cited only for canonical
  practices (Google code review 2018, SRE workbook, feature toggles, Google mutation testing 2021).
