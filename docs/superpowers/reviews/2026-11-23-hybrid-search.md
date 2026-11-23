# Hybrid search verification

Developed on `codex/hybrid-search` from `74f0bbf`. Changes remain uncommitted for
Jesse to stage, commit, integrate, and push himself. No release/version update.

## Behavior

- Wait 250 ms after the latest edit; a trailing Space dispatches immediately.
- Initial keywords, navigation, and Enter expedite the current search.
- Keep keyboard input and cancellation responsive during a running query.
- Cancel superseded work and reject obsolete results. Never freeze old matches.
- Retain queued selection/draft input in order; frozen lazy SQLite snapshots
  own independent readers and stay usable across later searches.
- Keep idle screens blocked on input rather than redrawing continuously.
- Leave ranking SQL, bundled data, direct `--matches`, and cc drafting semantics intact.

## Independent review

A fresh-context `gpt-6.2-astra` reviewer examined tracked and new working files.
No Critical or Minor findings. Three Important findings were reproduced with
real PTYs, fixed in one regression pass, and verified by the full suite:

1. Ctrl+R/Escape after a pending Enter could run before buffered draft text.
   Replay them in input order; only cancellation and resize bypass that queue.
   Query coalescing also consumes older buffered text before newer terminal bytes.
2. A Space inside a pasted burst incorrectly made the final partial word search
   immediate. Dispatch policy now follows the last edit; trailing Space remains
   immediate. A fixed-clock terminal regression verifies both cases.
3. A disconnected PTY could cause a busy polling loop. Distinguish timeout from
   disconnect and exit, tested both with a pending lookup and after results
   settle, without relying on SIGHUP.

After this review, Jesse reported a Bash vi-mode shortcut failure. A pause
between Ctrl+X and Ctrl+G inserted a control character and routed Ctrl+G to cc.
The integration now clears the old vi-mode Ctrl+X sequence/prefix before
rebinding it, including on repeated sourcing, without changing the global
Readline timeout. A real Bash test first reproduced the failure, then passed
with an 800 ms pause, double sourcing, Unicode draft handoff, and no execution.

No review findings were deferred. Exhaustive catalog content was outside this
review's scope: data and ranking SQL are unchanged and the existing full-catalog
acceptance checks still pass.

## Verification

- `python3 -B -W error::ResourceWarning -m unittest -q`: **141 tests passed**.
- `git diff --check`: passed.
- Real full-catalog PTY: input during a broad `n` search echoed in 0.14 ms in
  one observation; replacement network results took 412 ms including idle wait,
  cancellation/cleanup, and query time. Fresh network input echoed in 0.10 ms;
  results arrived after 327 ms. These measurements are examples, not latency guarantees.
- Runtime/build code continues to use only Python's standard library.
- Native Ubuntu execution remains unverified here because the session cannot
  access Docker. Both platform datasets are covered on macOS; use the existing
  `bash test-ubuntu.sh` workflow for native Linux validation.

## Decisions

The displayed hybrid approach was explicitly approved. The short design records
it without reopening the same approval question; implementation runs natively
with one final independent review. This gives independent feedback at the end.

Honor Jesse's Git workflow by retaining uncommitted changes in the isolated
worktree and supplying commands. The installed `main` copy stays unchanged
until local integration. Existing catalog uncertainty remains documented in
the separate coverage reports; this change does not claim to resolve it or
publish a final release.
