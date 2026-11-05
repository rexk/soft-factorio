We're about to publish a release, and users read packages/react/README.md to learn the API, so anything exported but undocumented (or documented but gone) will confuse them.

Find every mismatch between what packages/react exports and what its README documents. Return a list with one line per mismatch: the name, and whether it's "exported but not documented" or "documented but not exported". If there are none, say so. Read only; don't edit files.
