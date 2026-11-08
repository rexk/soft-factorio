# Metrics over time: research

Key: `metrics`

How it feels to work with the factory matters, but feelings drift. This
note is the research behind the [product brief](product.html): what similar
tools measure, what holds up, and a proposed starting set. The proposed set
is input for the design brief, not a decision.

## What similar tools measure

| Source | What it counts | What we can take from it |
|---|---|---|
| Claude Code telemetry (OpenTelemetry) | Sessions, tokens, cost, lines added or removed, commits, PRs, edit accept/reject decisions per tool and language | Counts of activity. Telemetry has to be switched on, and it goes to the person's own collector |
| Claude Code analytics (Team/Enterprise) | Suggestion accept rate, lines accepted, merged PRs containing at least one Claude line | Kept conservative on purpose: a line or PR counts only when the tool is sure it was involved. Deletions afterwards aren't tracked |
| GitHub Copilot usage metrics API | Suggestion acceptance rate, active users, coding-agent PRs merged, median minutes to merge | **Merged agent PRs and time to merge** are the outcome numbers. Created vs merged gives a merge rate |
| Cursor AI code tracking | Share of committed lines that came from Tab or Agent, matched by line signature | Formatters break the matching, and users report wrong numbers. A share of AI-written lines is easy to get and hard to trust |
| aider release notes | "Aider wrote N% of the code in this release", by git blame on new lines | One honest number, published every release, with the method stated. Varies widely between releases (21% to 88%) |
| DX AI Measurement Framework | Three dimensions: utilization (active users, share of AI-assisted PRs), impact (hours saved, quality, developer experience), cost (spend, net time gained) | Pairs telemetry with short developer surveys; neither one alone |
| Anthropic, measuring agent autonomy | Human interventions per Claude Code session (fell from 5.4 to 3.3 over four months), turn length | **Interventions per session** is a direct measure of how much the person had to step in |
| Anthropic, evals for agents | pass@k (at least one of k runs passes), pass^k (all k pass), read transcripts to check the graders | Our 3-of-3 rule is pass^3. Tracking it per release is what turns evals into a trend |
| METR randomized trial (2025) | 16 experienced developers, 246 real tasks: measured 19% slower with AI, while they believed they were 20% faster | **Perception and measurement can point opposite ways.** Collect both and report both |
| GitClear code quality reports | Churn: lines reverted or rewritten within two weeks. Copy-pasted vs moved code | Churn is a quality signal that can be read from git alone. Vendor research, correlational |
| Studies of agent PRs (AIDev dataset) | Agent PRs merge less often than human PRs; scoped tasks (CI, docs) merge most; more review comments *lower* merge odds for agent PRs | Merge rate and review rounds per PR are the usual research outcomes |
| Study of instruction files and agent PRs (MSR '26) | Across 148 projects, adding instruction files raised the merge rate by 20% or more in 27.7% of them and lowered it by 20% or more in 26.35%. Projects that improved had longer, more structured files | Close to what the factory ships. **Its effect isn't reliably positive, so we have to measure it in each repository.** The length finding also sits awkwardly with our "lean rules", and only our own numbers can settle that |
| Superpowers, spec-kit, BMAD | No published outcome measurement found; reviews say their effect is hard to separate from the model's | Room for the factory to stand out: our evals already run with and without the factory (factory vs bare arms) |

Patterns across them:

- **Activity counts are easy and weak.** Lines written, sessions and accept
  rates go up with use whether or not the work got better. Each vendor
  hedges its AI-line attribution.
- **Outcomes come from git and the PR host.** Merged or not, time to merge,
  review rounds, reverted within two weeks. These need no telemetry.
- **Friction is a measure in its own right.** Interventions per session,
  permission prompts and turns to finish are what the person feels as "it
  keeps stopping".
- **Perception is collected on purpose, briefly, and next to the numbers.**
  DX uses surveys, and METR shows why a survey alone misleads.
- **The harness is a variable.** Studies of coding-agent harnesses find
  large differences in tokens per solved task between harnesses, with small
  differences in pass rate. Cost per pass belongs next to the pass rate.

## Proposed starting set

Three sets of numbers. Each one is computed locally from data that is
already there: eval results, git, the PR host, and the harness's own session
logs. No telemetry leaves anyone's machine, which fits the factory being
public and copied into other people's repositories.

### 1. The factory's evals, per release (this repository)

| Metric | From | Why |
|---|---|---|
| pass^3 per scenario, factory vs bare arm | `evals/run.py` results | Already measured; we need it kept per release, not only per pass |
| Lift: factory pass rate minus bare | same | Says what the factory adds over the model on its own |
| Cost and turns per passing run | `cost_usd`, `num_turns` the runner already reads | Catches a change that passes but costs twice as much |
| Void and crashed runs | same | A rise means the harness, not the factory, is the problem |
| Judge agreement with calibration samples | `--calibrate` | A judge that drifts makes every other number meaningless |

Gap today: results land in the scratch folder, and only a hand-picked copy
reaches `docs/projects/`. A small step: append each pass's summary to one
history file, so a release can be compared with the one before.

### 2. Outcomes in a repository that adopted the factory

| Metric | From | Why |
|---|---|---|
| Agent PR merge rate | PR host | The plainest outcome; what the studies and Copilot use |
| Review rounds before merge | PR host | Fewer rounds means the first version was closer to what was wanted |
| Time to merge | PR host | Copilot reports the median |
| Reverted or rewritten within 14 days | git | Quality, not volume |
| Corrections per task, and how many the retro turned into a test, rule or skill | the retro skill's Lessons tables | Our own signal: corrections should fall, and each one should leave a fix |

These are compared before and after applying the factory, and between
factory updates, in the same repository. Comparing across repositories says
little, because the work differs.

### 3. Session friction (the harness)

| Metric | From | Why |
|---|---|---|
| Interventions per session: interruptions, corrections, repeated instructions | the harness's session logs | Anthropic tracks this one; it's what "it keeps needing me" means |
| Permission prompts per session, by command | the harness's session logs | Measures whether the [settings guide](../../../guides/harness-settings.md) worked |
| Turns and minutes to a finished PR | the harness's session logs and the PR host | Shows how long it takes to finish, as well as whether it finished |

### 4. Perception, kept next to the numbers

A two-question pulse at the end of a task, optional and stored only in the
repository's own report: "How much did you have to step in? (none / some /
a lot)" and "Would you take this PR as is? (yes / with edits / no)". We show
it beside the measured numbers for the same tasks. When they disagree, as
in METR's trial, that disagreement is the finding.

## What not to measure

- **Share of code written by AI, or lines written.** Every vendor hedges
  its own attribution, and the number goes up with use, not with quality.
- **Raw accept rate of edits.** Permission settings and habits move it more
  than quality does.
- **One score across repositories.** We compare each repository with its
  own earlier numbers.

Any of these becomes a target the moment it's reported, so each one is
reported with the one that guards it: merge rate with reverts, pass rate
with cost, fewer interventions with corrections still caught.

## Open

- Which of the four sets to build first? Proposed: set 1's history file. It
  needs no new data, and it's how we'd measure everything after it.
- Sets 2 and 3 run inside adopting repositories, so they'd ship as a skill
  or a tool there (standard library, reads git and the PR host's CLI). Is a
  `metrics` skill in scope for v1, or after it?
- Reading the harness's session logs is specific to each harness (Claude
  Code and Codex keep different formats). Start with one?
- The perception pulse adds a question at the end of every task. Worth it,
  or only during a trial period after applying the factory?

## Sources

- [Claude Code: monitoring usage](https://docs.anthropic.com/en/docs/claude-code/monitoring-usage)
- [Claude Code: analytics](https://code.claude.com/docs/en/analytics)
- [GitHub: Copilot usage metrics](https://docs.github.com/en/copilot/concepts/billing-and-usage/copilot-usage-metrics/copilot-metrics)
- [GitHub changelog: PR throughput and time to merge in the usage metrics API](https://github.blog/changelog/2026-02-19-pull-request-throughput-and-time-to-merge-available-in-copilot-usage-metrics-api/)
- [Cursor: Cursor Blame](https://cursor.com/docs/integrations/cursor-blame)
- [aider: release history](https://aider.chat/HISTORY.html)
- [DX: AI Measurement Framework](https://getdx.com/ai-measurement-framework/)
- [Anthropic: measuring agent autonomy](https://www.anthropic.com/research/measuring-agent-autonomy)
- [Anthropic: demystifying evals for AI agents](https://anthropic.com/engineering/demystifying-evals-for-ai-agents)
- [DX newsletter on METR's study](https://newsletter.getdx.com/p/metr-study-on-how-ai-affects-developer-productivity)
- [GitClear: Coding on Copilot](https://www.gitclear.com/coding_on_copilot_data_shows_ais_downward_pressure_on_code_quality)
- [Developer and agentic pull requests (arXiv 2601.18749)](https://arxiv.org/abs/2601.18749)
- [How AI coding agents contribute: agentic PRs (arXiv 2607.21832)](https://www.alphaxiv.org/abs/2607.21832)
- [Toward instructions-as-code: instruction files and agentic PRs (arXiv 2606.13449)](https://arxiv.org/abs/2606.13449)
- [The scaffold effect in coding agents (ICML 2026)](https://icml.cc/virtual/2026/82739)
