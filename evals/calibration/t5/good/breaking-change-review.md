Reviewers need to know whether this branch can break existing callers before they approve it.

Done means: a list of every public function or type whose behaviour or signature changed between main and this branch, each with one line on what a caller would notice. Say "none" if nothing public changed. The public API is whatever src/index.ts exports. Don't run the test suite; it's slow.
