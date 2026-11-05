# T1 judge calibration

The brief judge must accept every page in `good/` and reject every page in
`bad/` before its verdicts count:

```bash
python3 evals/run.py T1 --calibrate
```

`bad/` holds near misses on purpose: a brief that is right except for one
line naming a storage mechanism and a file, and a build plan that calls
itself a product brief. Changing these samples changes what T1 means, so it
goes through the maintainer's review like any scenario change.
