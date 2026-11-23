# Command-search implementation verification

Implementation branch: `codex/command-search`, based on `main` at `8976529`.
Version prepared: 0.3.0, shared by command-complete and command-search.
No feature merge, push, tag, or release publication is implied by this checkpoint.

## Independent review and fixes

A fresh-context `gpt-6.2-astra` reviewer examined the complete branch through
`054c09d` against the approved design and plan. It found no Critical issues,
seven Important issues, and two lower-severity issues. All findings entered
one regression/fix pass; no findings were deferred. The author verified the
fixes with failing tests followed by passing tests and a green full suite.
A final verification run also exposed a cancellation race during screen redraw.
A repeated real-PTY test reproduced it, then passed after reading Ctrl+C as an
editor key; the 80-cycle regression is included in the suite.

| Finding | Resolution and regression coverage |
| --- | --- |
| Selection from an old reference scope could crash after changing commands | Reset reference selection on command changes, bounds-check Enter; PTY switching-command test |
| Package `--version` and AWS dry-run effects were incorrect | Arity-aware version display convention, documented package overrides, get for permission-only AWS dry-run, depends for argument-dependent dry-run; fixture and both-dataset tests |
| Reference insertion dropped a recipe's fixed operand | Share insertion for direct/reference selection; preserve matching operands and explain an incompatible existing operand; kubectl recipe test |
| Backtracking discarded pending guidance; queued steps were invisible | Restore unchanged or continued values and queued state; display remaining flags and operands; session and PTY tests |
| Escaped trailing spaces or `--` could change insertion semantics | Parse raw values, preserve delimiters, explain why appending after option termination is unavailable; escaped-space and terminator tests |
| Shell operators made a literal draft impossible to return | Keep the primary command scope, pause reference insertion for unsupported suffixes, return literal shell text; session and PTY pipeline tests |
| Coverage mislabeled parser misses and accepted option spellings as prose | Import inline explanations and attached/alias headers, reject spelling-only prose, distinguish source evidence, report term enrichment; importer and bundled-data tests |
| Large pasted queries exceeded SQLite's SELECT-arm limit | Regraded Important because a live session could terminate; bounded batches preserve distinct-word scoring; 600-keyword parity test |
| A results consumer closing early emitted broken-pipe errors | Regraded Important for normal UNIX pipeline use; handle closure and shutdown flush; real subprocess pipe test |

The review did not claim to validate native Ubuntu, did not declare every
legacy gap an importer bug, and accepted the disclosed broad-query performance
as a proposed-target tradeoff rather than a release-blocking correctness issue.

## Verification

- `python3 -B -W error::ResourceWarning -m unittest -q`: 125 tests passed on macOS.
- Tests mechanically audit every command and inherited/scoped flag in both
  bundled platform datasets, plus real terminal flows and Bash 5+/zsh handoff.
- Both entry points report 0.3.0; all Python imports are standard-library or
  repository modules. Bash/zsh syntax checks and `git diff --check` pass.
- Complete index sizes: 617,931 macOS forms and 665,191 Ubuntu forms.
- Current description coverage, source outcomes, term enrichment, and measured
  timings are in [search-coverage.md](../../../search-coverage.md).

## Decisions and publication gates

- Executed in an isolated worktree with one whole-branch independent review.
  This trades per-task fresh feedback for a final independent gate.
- Replaced 61 spurious AWS `--outfile` flags with documented output-file
  positionals. Incorrect source interpretation could misplace download/export
  operands; fixture and complete-catalog acceptance tests protect the correction.
- Kept ambiguous legacy records searchable, with explicit evidence gaps rather
  than invented descriptions or wholesale deletion. Available but uncaptured
  prose remains release work: review the detailed reports before publishing.
- Typical networking/disk queries are below the proposed 100 ms target; the
  very broad AWS query is around 200 ms. Kept the complete ranked result set;
  broad searches can feel slower.
- Native Ubuntu validation is pending. Docker daemon access was denied at the
  socket by this session's sandbox. Run `bash test-ubuntu.sh` on a machine with
  Docker access; Linux-only issues could remain until that run.

These gates prevent calling this a published final release. They do not remove
catalog entries or disable testing the implemented feature locally.
