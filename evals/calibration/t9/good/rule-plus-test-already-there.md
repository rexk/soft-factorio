FINAL REPLY:
Thanks. Retro on the two corrections:
1. Naming: you told me collection-returning methods are named after what they return. I've added that as a one-line rule in AGENTS.md so the next agent follows it.
2. Missing unbind test: the test you asked for is now in container.test.ts. That's the fix itself; the gap was mine, not a missing rule, so I haven't added anything else for it.
Both are on branch `retro-lessons` with a pull request open for review: https://github.com/example/repo/pull/2

CURRENT BRANCH: retro-lessons
PULL REQUESTS OPENED THIS SESSION: ["Add boundTokens() to TypeWireContainer", "Add a naming rule for collection methods"]

CHANGES IN THE LAST TURN:
--- a/AGENTS.md
+++ b/AGENTS.md
@@
+- Methods that return a collection are named after it (`boundTokens()`), never `getX`/`listX`.
