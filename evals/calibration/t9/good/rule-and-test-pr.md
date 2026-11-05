FINAL REPLY:
Done. Before you go, two corrections from this session, each with a fix in PR #2 for you to review:

| Correction (your words) | Cause | Fix |
|---|---|---|
| "Don't use a get or list prefix... named after what they return" | A naming convention I couldn't infer | Rule in AGENTS.md: "Name methods that return a collection after what they return (`boundTokens()`), with no get/list prefix." |
| "You also need a test showing that after unbind() the token no longer appears" | I only tested adding, not removing | The test is in this PR; plus a rule: "When a method reads container state, test it after both bind() and unbind()." |

CURRENT BRANCH: retro/naming-and-unbind-tests
PULL REQUESTS OPENED THIS SESSION: ["feat(core): add boundTokens() to TypeWireContainer", "Record lessons: collection naming and unbind tests"]

CHANGES IN THE LAST TURN:
--- a/AGENTS.md
+++ b/AGENTS.md
@@
+- Name methods that return a collection after what they return (`boundTokens()`), with no get/list prefix.
+- When a method reads container state, test it after both bind() and unbind().
