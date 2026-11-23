# Optional short-query guard verification

Prepared shared version **0.4.0** from main `543d729` in the existing isolated
`codex/hybrid-search` worktree. No Git staging, commit, merge, tag, or release
publication was performed. Unrelated Ubuntu packaging documents remain untouched.

## Delivered behavior

- Guard off by default. `--short-query-guard` enables it; its negative spelling
  disables it. Exported `COMMAND_SEARCH_SHORT_QUERY_GUARD` covers the hotkey;
  CLI flags override the environment, and invalid/blank values report an error.
- Automatic edits, including backspacing, hold a trailing unfinished keyword
  under three alphanumeric characters. Punctuation separates search terms but
  does not prevent their characters counting toward the guard threshold.
- Completed keywords stay active and unchanged completed-keyword queries are
  reused. A visible hint identifies the ignored suffix.
- Space, Enter, and existing result navigation explicitly submit full current
  text before choosing/freezing. Initial launch queries and `--matches` retain
  their explicit behavior. Ranking/filter semantics remain unchanged.
- Both complete catalog/index pairs document the positive and negative flags.
  The previously unstaged Bash vi-prefix fix is included.

## Independent review

A fresh-context `gpt-6.2-astra` reviewer examined the working changes and
independently verified both database fingerprints and all four new forms per
platform. It found no Critical issues, three Important issues, and one evidence
classification issue initially labeled Minor. The latter was treated as Important
because the existing release gate relies on truthful, preserved source evidence.

All four findings were reproduced with failing tests and fixed in one pass:

1. Replace quadratic suffix-regex matching with a linear suffix split. The
   30,000-character completed-token regression failed at about 2.5 seconds and
   passes with the linear implementation.
2. Count all searchable characters across the suffix, including repeated
   punctuation-separated segments: `ci/cd`, `s3.cp`, and `a-a-a`.
3. Reject explicitly blank environment values, retain the unset default, and
   preserve explicit CLI override precedence.
4. Persist specific missing-description evidence before cleaning unusable prose.
   A two-build fixture verifies idempotency. Restored prior evidence for unchanged
   bundled records during this snapshot-only rebuild; a comparison confirmed all
   previous missing-entry classifications unchanged on both platforms.

No findings were deferred. Existing catalog prose beyond the changed entries is
outside this review; its established coverage/publication gate is preserved.
Native Ubuntu remains a separate validation gate. The full suite was run by the
implementer; the independent reviewer performed scoped read-only checks.

## Verification

- `python3 -B -W error::ResourceWarning -m unittest -q`: **155 tests passed**.
- Both executable version commands report **0.4.0**.
- Direct `--matches`, CLI/environment precedence, terminal interaction, shared
  installation, Bash/zsh handoff and the vi-prefix regression pass.
- `git diff --check` and Bash/zsh integration syntax checks pass.
- Complete indexes contain 617,935 macOS and 665,195 Ubuntu forms. Both catalog
  fingerprints match their indexes and all prior gap evidence is retained.
- Docker client was present, but access to its daemon socket was denied by the
  session sandbox. Run `bash test-ubuntu.sh` on a Docker-capable machine before
  final publication; Linux-specific failures remain unverified here.

## Rulings

- Used the approved default-off design with native implementation and one final
  independent review, rather than reopening the same design decision. Feedback
  therefore arrived at the end of implementation.
- Preserved initial launch/direct matches/navigation as explicit submission.
  A deliberately requested short query can still be broad and expensive.
- Carried the already-tested vi-prefix fix into this version. It reserves that
  prefix in vi mode; other custom vi Ctrl+X bindings should be sourced afterward.
- Preserved the existing coverage evidence and catalog-audit scope. Existing
  unresolved catalog descriptions remain release work rather than invented prose.
- Kept native Ubuntu validation open after the actual socket denial. The notes
  prepare a release and user-run draft commands, not a claim of final publication.
