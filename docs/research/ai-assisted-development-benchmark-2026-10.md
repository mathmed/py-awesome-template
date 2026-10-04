# AI-assisted development: our pipeline benchmarked against the market (October 2026)

> **Status: draft in progress.** Sections 3 to 8 are being written; section 2 (current state) is complete.
>
> **Disclosure note.** This repository is public. The report deliberately leaves out credentials, account
> identifiers, hostnames, internal URLs and step-by-step attack paths. Security findings are written as
> control gaps with their remediation. Anything more specific than that belongs in a private channel.

**Evidence labels used throughout**

| Label | Meaning |
| --- | --- |
| **[S] strong** | Data: controlled studies, large surveys with published method, incident post-mortems, or several independent first-hand practitioner reports that agree. |
| **[P] practitioner** | Credible first-hand experience from one or a few teams or engineers (HN/Reddit/lobste.rs threads, engineering blogs describing their own system, conference talks). |
| **[V] vendor** | Claims by a vendor about its own product, marketing, or listicles. Treated as hypotheses, not facts. |

---

## 1. Executive summary

_To be written last._

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
and repository variables; `gh` for the last ≤60 merged PRs and ≤30 CI runs per repo. The core money-moving
services (Pix, boleto, CNAB) were **not** in scope: what follows describes the template and the repos above,
not the bank's core systems.

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
  duration. Limits: a global concurrency semaphore and an 8-hour wall-clock timeout. Questions to the owner go
  through an MCP `ask_user`/`notify_user` tool.
- **Workspace model.** One shared clone per project; every job starts with `git checkout <default>` +
  `pull --ff-only` in that same directory. There is **no per-job isolation** (no git worktree, container or
  ephemeral VM) and no OS-level sandbox or network egress restriction; the agent process inherits the
  orchestrator service's environment.
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
  container image scanning, SBOM or build provenance, SHA-pinned GitHub Actions, a dependency cooldown
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
  analyse incidents with an LLM, open Jira tickets, alert on Slack/WhatsApp, and **open fix PRs automatically**,
  gated by an LLM `PRReviewer` (approve/reject). Budget check per cycle, status-page signals, weekly reports. Eval
  cases recorded the same way as hulk.
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

---

## 3. Market landscape

_In progress._

## 4. Gap analysis

_In progress._

## 5. Prioritized recommendations

_In progress._

## 6. Practices to deliberately not adopt

_In progress._

## 7. Open questions and what could not be verified

_In progress._

## Appendix A. Sources

_In progress._
