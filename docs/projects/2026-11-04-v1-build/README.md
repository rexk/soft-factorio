# v1 build

Building v1 of the factory: approach A2 (start file, copied skills, a
manifest, scenario evals). The product and design briefs are kept outside
this repository; the behaviour lines (B1–B14) and scenarios (T1–T12) they
define are mirrored in `evals/`.

## State

| Step | State |
|---|---|
| Prove the approach on T1 | Done: [t1-proof.html](t1-proof.html). Factory 3/3, bare 0/3 on the git diff, after one skill fix |
| Repository set up: license, checks, privacy scan, CI | Done |
| `START.md` (apply and update) | Not started |
| Manifest helper and its tests | Not started |
| Smoke scenarios T3, T10; T1 through `START.md` | Not started |
| Every behaviour line has a scenario passing at its rate | Not started |

## Open

- Does a product brief written in chat (not as a page) satisfy T1? The skill
  allows chat briefs for small asks; T1's code judge only accepts a page
  under `docs/`. A judge change, so the maintainer decides.

## Next

1. `START.md`, then rerun T1 with the `apply` arm.
2. Manifest helper, tested through its interface.
3. T3 and T10.
