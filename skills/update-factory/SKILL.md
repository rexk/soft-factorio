---
name: update-factory
description: Check for and apply updates to the software factory installed in this repository (its skills, the marked block in AGENTS.md and its guides), from the factory recorded in .agents/factory/manifest.json. Use when the person asks to update the factory, pull in its latest changes, check whether a factory update exists, or asks what changed upstream in the factory.
---

# update-factory: bring in the factory's latest, keeping local choices

**Outcome:** the person knows how far this repository is behind the factory
and what they would have to do by hand. If they asked for the update, it
arrives as one pull request made by following the factory's *current*
`START.md`, with this repository's local edits kept. If they only asked
whether there is one, nothing in the repository changed.

## Steps

1. **Find what's installed.** Read `.agents/factory/manifest.json`: `source`
   is where the factory came from, `version` is the commit installed. If
   there is no manifest, the factory isn't installed here: say so, and stop.
2. **Get the factory.** If `source` is a path to a factory checkout that
   exists, use it as it is. If it's a git URL, clone it (default branch,
   full history) into a temporary folder outside this repository. Otherwise
   ask the person where the factory is, suggesting
   `https://github.com/rexk/soft-factorio`.
3. **See what changed.** From this repository's root, run
   `python3 <factory>/tools/factory.py plan .`. It changes nothing. It
   prints the installed and latest versions, what each file would do, the
   factory's commits since the installed version, and the changelog entries
   added since then. If it says *Up to date*, tell the person and stop.
4. **Only checking?** If the person asked whether there is an update, or
   what changed, report it in a few lines and stop:
   - from which version to which, and the commits in between;
   - every "Action needed" changelog entry, as something the person does;
   - any conflicts (files edited here and changed in the factory).

   Then offer to apply it.
5. **Update.** Read `START.md` in the clone and follow it, from its step on
   looking at the repository. Follow the copy you cloned, not the steps you
   remember, as they change between versions. It's an update, so the
   upstream answer is already in the settings table: don't ask it again. In
   the pull request description, list every "Action needed" entry as a
   checklist for the person.

## Never

- Change the factory's files in this repository by hand: the helper
  installs them, and the manifest records what it installed.
- Push to the default branch, or merge the update yourself.
- Send anything to the factory.
