# Apply the software factory

**For the agent reading this:** follow these steps to install the factory in
the repository you are working in, or to update it if it is already there.
The person who sent you here does two things: answers one question on the
first install, and reviews the result.

**Outcome:** the repository has the factory's skills and rules, fitted to
its own conventions and recorded in a manifest, and a pull request (or a
report) that says what changed. Nothing the repository already had is lost
or rewritten.

**Permissions you need:** read the repository; clone the factory into a
temporary folder outside it; run `python3`; edit files in the repository;
create a branch, commit, and open a pull request.

## Steps

1. **Get the factory.** If you were given a local path to it, use that.
   Otherwise clone `https://github.com/rexk/soft-factorio` (its default
   branch, with full history) into a temporary folder outside the
   repository. The factory has no release tags: its version is the commit
   you cloned. Never copy the factory's own repository files into the
   target. *Done when* you have a checkout.

2. **Look at the repository.** Find its rules files (`AGENTS.md`,
   `CLAUDE.md`, `.cursor/rules/`, `.github/copilot-instructions.md`), its
   skills (`.agents/skills/`, `.claude/skills/`, `.cursor/skills/`), where
   it keeps docs and plans, and whether `.agents/factory/manifest.json`
   exists. *Done when* you can say: first install or update, which rules
   file its agents read, and which of its skills share a name with the
   factory's.

3. **First install only: ask the upstream question.** Ask the person, in
   your own words:

   > Should this repository send lessons back to the factory? If yes, it
   > gets a skill that drafts a lesson as an issue, without this
   > repository's private details, and asks you before each one is sent.
   > If no, nothing is ever sent.

   Wait for the answer, unless their request already gave it. On an update
   the answer is already in the settings table: don't ask again.
   *Done when* you have a yes or a no from the person.

4. **Plan.** Run, from the repository root:

   ```bash
   python3 <factory>/tools/factory.py plan . --upstream <yes|no>
   ```

   (On an update, `--upstream` can be left out.) It lists what would be
   added, updated, kept and skipped, and changes nothing.
   - **Conflicts** (a file edited here and changed in the factory): for
     each, show the person the local edit and the factory's change, and ask
     which to keep. Never pick for them.
   - **The repository's own skill with a factory skill's name:** the
     repository's wins and the factory's is skipped. Nothing to ask; say so
     in the report.

   *Done when* every conflict has the person's answer.

5. **Apply.**

   ```bash
   python3 <factory>/tools/factory.py apply . --upstream <yes|no> \
     [--resolve PATH=ours|theirs ...]
   ```

   It copies the skills, appends one marked block to `AGENTS.md` (creating
   it if needed) with a settings table after it, and records everything in
   `.agents/factory/manifest.json`. *Done when* it exits 0.

6. **Fit it to the repository.** This is your judgment; the helper can't do
   it.
   - **Every agent tool reaches the rules.** Codex and Cursor read
     `AGENTS.md`; Claude Code reads `CLAUDE.md`. If the repository has a
     `CLAUDE.md` that doesn't import `AGENTS.md`, add a line `@AGENTS.md` to
     it and change nothing else there. If it has none, create one holding
     only that line.
   - **Settings.** If the repository already keeps plans or design docs in
     a folder, set `projects` in the settings table to it.
   - **Contradictions.** If a factory rule contradicts one of the
     repository's rules, the repository's rule wins (the block says so).
     Don't edit either; name the contradiction in the report.
   - **Leave the rest alone.** Don't reorder or reword existing content,
     and don't edit inside the marked block: edits there count as local
     edits on the next update.

   *Done when* you'd be comfortable with an agent in each tool starting work
   here tomorrow.

7. **Report for review.** Create a branch (e.g. `factory/<version>`), commit
   the change with a message naming the factory version, and open one pull
   request (the `create-pr` skill you just installed knows how). Its
   description says:
   - the factory version (commit), from what to what, and the factory
     changes the helper listed since the installed version;
   - every changelog entry the helper marked **Action needed**, as a
     checklist of what the person does by hand;
   - what was added, updated and removed;
   - local edits kept, and how each conflict was resolved;
   - the repository's own skills that won over the factory's;
   - the upstream answer, and any contradiction from step 6;
   - one line pointing the person to
     `.agents/factory/guides/harness-settings.md`, which lists the settings
     that let commits, pushes and pull requests run without a prompt. Don't
     change those settings yourself.

   If there is no remote or you can't open a pull request, leave the commit
   on its branch and give the same report in chat.
   *Done when* the person has the link or the report.

## Never

- Push to the default branch, or merge your own pull request.
- Delete or rewrite the repository's files, other than what the helper
  installed.
- Send anything to the factory, open issues on it, or ask the upstream
  question again on an update.
