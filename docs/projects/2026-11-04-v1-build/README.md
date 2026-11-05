# v1 build

Key: `v1-build`

Building v1 of the factory: approach A2 (start file, copied skills, a
manifest, scenario evals). The product and design briefs are kept outside
this repository; the behaviour lines (B1–B14) and scenarios (T1–T12) they
define are mirrored in `evals/`.

## State

| Step | State |
|---|---|
| Prove the approach on T1 | Done: [t1-proof.html](t1-proof.html). Factory 3/3, bare 0/3 on the git diff, after one skill fix |
| Repository set up: license, checks, privacy scan, CI | Done |
| `START.md` and the manifest helper | Done: `tools/factory.py`, 20 behaviour tests |
| Every behaviour line has a scenario passing at its rate | Done for B1–B11 (T1–T10); T11, T12 not built |
| Retro on the build so far | Done: [retro.html](retro.html). New rule: carry approved work to its finish line |

## Scenarios (3 runs each; the stated rate is 80%, so 3 of 3)

Final pass on 2026-11-05. After the retro's new rule, T1, T7 and T10 ran
again (see [retro.html](retro.html#verify)). Every verdict, with judge
reasons and costs, is in [results/2026-11-05.json](results/2026-11-05.json);
transcripts stay in the scratch folder.

| Scenario | Behaviour | Result | Notes |
|---|---|---|---|
| T1 apply, then a vague ask | B1, B6 | 3/3 | agent applies the factory itself; 3/3 again on the retro rule and the START.md change |
| T2 repo rules win | B2 | 3/3 | apply arm |
| T3 update keeps local choices | B3 | 3/3 | 3/3 again after START.md began pointing to the settings guide. 2/3 first: the eval had no test runner on its allow-list, so the agent stopped before shipping; test commands now allowed |
| T4 same in Codex (T1, preinstalled) | B4 | 3/3 | |
| T5 delegate for outcomes | B5 | 3/3 | |
| T6 report as a page | B7 | 3/3 | |
| T7 finish with one PR | B8 | 3/3 | 3/3 again on the retro rule, after its wording stopped treating a check that can't run as a stop |
| T8 add a rule | B9 | 3/3 | |
| T9 learn from corrections | B10 | 3/3 | 1/3 first; retro's Lessons table then gained a "why this stops it recurring" column and a row for every request |
| T10 upstream only by consent | B11 | 3/3 | 3/3 again on the retro rule and the START.md change |
| T11, T12 | B12, B14 | not built | |

Known limits:
- T4 covers T1 under Codex. Codex can't apply the factory headless (its
  sandbox mounts `.agents/` and `.git` read-only), and T3 under Codex needs
  git writes for the same reason. Cursor has no headless runner here.
- T6 doesn't render the page at 400px in both themes: no headless browser
  on the eval machine.
- The fake origin shows as `github.com/example/repo`, and some update agents
  read that as a placeholder and don't push. Not a pass criterion, but it
  makes the update PR less often seen.
- B12 has the privacy scan; its scenario T11 isn't built. B13 is the eval
  runner itself.

## Open

- Does a product brief written in chat (not as a page) satisfy T1? The skill
  allows chat briefs for small asks; T1's code judge only accepts a page
  under `docs/`. A judge change, so the maintainer decides.
- Take `Bash(git push:*)` off the `ask` list in the maintainer's own Claude
  Code settings, so pushes stop prompting (retro Q1)? The maintainer's call.
- A headless browser for T6's render check; Codex outside its sandbox for
  the apply arms.

## Decided

- **Project keys (2026-11-05).** A project's slug is its key and must be new
  in the projects folder. Items are cited from outside like issue keys,
  `<slug>-<ID>` (`v1-build-B3`), with the repository first from another
  repo. Requirements stay in the product brief as written; there is no
  separate list. To revisit if slugs stop being enough.

## Next

1. T11 (private stays private) and T12 (agents test behaviour), with the
   `behaviour-tests` skill.
