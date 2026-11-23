# Command-search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Ship offline, purpose-based command search across the complete cc catalog, followed by split-screen command drafting and editable shell handoff.

**Architecture:** Reuse cc's Catalog and inert parser. Add separate standard-library modules for documentation enrichment, search indexing, session transitions, and terminal presentation; keep curated search overrides independent of regenerated snapshots. Both entry points share platform data and a release version.

**Tech Stack:** Python 3.10+, curses, json/gzip, html.parser, sqlite3, unittest, Bash 5+, zsh.

**Spec:** `docs/superpowers/specs/2026-11-22-command-search-design.md`

## Global Constraints

- Use only Python's standard library at runtime and in Python build tools.
- Search entirely offline against bundled data.
- Index every existing macOS and Ubuntu 24.04 command and scoped flag, including inherited options and portable AWS/kubectl/Docker commands.
- Available documentation must be imported before final release; report genuinely unavailable metadata explicitly.
- Inclusive case-insensitive word-prefix matches rank by distinct matched query keywords, then alphabetical command-form text.
- get/set are strict filters; depends/unknown remain distinct.
- Never execute a draft. Preserve existing standalone cc behavior and supported shells.
- Use one repository and release version; retain unrelated Ubuntu packaging work untouched.

## Review Focus

- Shell punctuation, quotes, Unicode and argument placeholders stay inert and survive editable-buffer handoff (Tasks 3, 4, 5).
- Imported AWS HTML, shared shapes, custom commands and missing documentation produce truthful descriptions and coverage reports (Tasks 1, 6).
- Aliased commands, inherited flags, partial command paths, namespace-only nodes and global options before subcommands select the right reference scope (Tasks 2, 3).
- Resize and small terminals preserve selected entries and safe cancellation across both panes (Task 4).
- Guided values, conflicting recipes, repeated flags and backtracking never overwrite entered values or insert stale queued flags (Task 3).

## File structure and interfaces

- `search_metadata.py`: documentation cleanup/import, terms, effect provenance, search metadata assembly and report.
- `search_overrides.json`: reviewed task terms/effects and useful multi-option recipes.
- `build_search_catalog.py`: explicit build command, local source discovery, platform snapshot enrichment and audit.
- `command_search_index.py`: `SearchEntry`, `SearchResult`, `SearchIndex(catalog, metadata)`, `search(query)` and `entries_for_command(path)`; shared structured insertion components.
- `command_search_session.py`: `SearchSession(index, catalog, query='')`, frozen snapshots, drafting, guided sequences, selection and backtracking.
- `command_search.py`: curses UI and CLI entry point, result-fd output compatible with cc.
- `command_complete.py`: expose reusable edit-key handling/drawing as needed and read the shared release version; keep import compatibility.
- `version.py`: single shared `__version__` value (0.3.0 for this feature).
- Platform completion gzip files retain their paths and receive descriptions. Platform `search-*.db.gz` snapshots store the complete SQLite search index; `search-coverage-*.json.gz` store audits. Curated recipes remain in `search_overrides.json`.
- `shell-integration.sh`: both widgets and configurable cs key binding, preserving cc Ctrl+G.
- New `test_search_metadata.py`, `test_command_search.py`, `test_search_session.py`, `test_search_terminal.py`; extend existing terminal/platform tests where appropriate.

### Task 1: Import descriptive source metadata

Consumes existing completion catalogs and available installed manuals/CLI reference data. Produces `clean_description(text)`, `import_aws_models(commands, model_directory)`, manual/help summary import, `build_metadata(commands, overrides)`, and auditable source/description/effect coverage.

- [x] Write fixture tests for HTML-to-plain descriptions, AWS operation/input-shape mapping to CLI flags, shared-shape descriptions, unknown custom operations, curated overrides, and documented gaps in the report.
- [x] Run `python3 -B -m unittest test_search_metadata -v`; observe missing-importer failures.
- [x] Implement source import with stdlib JSON/HTML parsing, source-backed effects and conservative unknown/depends handling. No external Python package or runtime network requirement.
- [x] Run fixture tests and the existing suite. Commit the importer and tests.

### Task 2: Complete-catalog search and ranking

Consumes Task 1 semantic metadata and cc `Catalog`. Produces immutable entries and ranked results with structured option/value components. `SearchIndex.search(query)` returns results plus a query error when filters conflict.

- [x] Write tests with literal expected order for OR/prefix matching, duplicated query tokens, score ties, strict filters, filter-only/empty queries, unknown metadata, aliases and inherited flags.
- [x] Run `python3 -B -m unittest test_command_search -v`; observe missing-search failures.
- [x] Implement complete entry enumeration and an efficient token-posting prefix index; keep all results accessible and use stable IDs.
- [x] Verify representative documented purpose queries and mechanical coverage of every command/scoped flag. Run the suite and commit.

### Task 3: Stateful drafting and guided insertion

Consumes Task 2 entries and shared cc parsing/completion. Produces `SearchSession` with query/frozen/draft stages, `freeze(entry=None)`, `set_draft(line,cursor)`, `insert_entry(entry)`, `confirm_value()`, `back()`, and per-command session drafts.

- [x] Write tests for manual/direct selection transitions, exact runnable-path matching with global options, frozen order, changing commands, preserving work through backtracking, and cancellation semantics.
- [x] Add guided-recipe tests for two required values, quoting, fixed values, no literal placeholders, existing values, conflicts before mutation and stale queue cancellation.
- [x] Run `python3 -B -m unittest test_search_session -v`; observe missing-session failures.
- [x] Implement transitions and inert structured insertion; confirm values explicitly and reuse cc hints/conflict knowledge.
- [x] Run all session tests and full suite, then commit.

### Task 4: Terminal UI and offline CLI

Consumes `SearchIndex`/`SearchSession` and cc drawing/edit primitives. Produces `command-search [query...]`, `--matches`, `--version`, hidden `--result-fd` integration and live top/bottom drafting.

- [x] Write PTY tests for live filtering, freezing, direct/manual selection, F6 reference focus, adding a flag, Ctrl+R, cancellation, final unexecuted output, queued arguments and small-terminal resize.
- [x] Run `python3 -B -m unittest test_search_terminal -v`; observe missing-entry-point failures.
- [x] Implement curses presentation with full-screen search/chooser, equal-height split, responsive two-entry reference rows, descriptions in normal text and flags in cyan, active-pane indication, paging and contextual help.
- [x] Share edit-key handling where needed without changing standalone cc contracts. Run new PTY tests and existing tests, then commit.

### Task 5: Shared installation, version and shell handoff

Consumes Task 4 result-fd protocol. Produces both shell widgets, configurable default cs Ctrl+X Ctrl+G, shared version 0.3.0 and explicit short-entry-point installation.

- [x] Add real-shell PTY tests for query seed, completed cs draft remaining editable until another shell Enter, literal punctuation and cancellation restoring original text.
- [x] Run the tests to observe missing-shell-widget failures.
- [x] Implement shared integration while preserving cc Ctrl+G and supporting Bash 5+/zsh. Provide a non-overwriting installer/setup command for command-search/cs.
- [x] Verify shells where available, whole suite and version consistency. Commit.

### Task 6: Build and audit the full platform datasets

Consumes Task 1 importers, Task 2 entry enumeration, local documentation and versioned authoritative source data where needed. Produces enriched completion data, full search snapshots, source provenance and coverage reports for both supported platforms.

- [x] Add catalog acceptance tests for available AWS operation/flag prose, representative purpose searches and curated recipes in all five families, and truthful unavailable-doc reporting.
- [x] Run the acceptance tests before generating snapshots; observe absent-data failures.
- [x] Discover source availability, import all available documentation, generate both platform snapshots, and audit complete command/scoped-flag enumeration. Resolve available-documentation importer misses; do not declare them undocumented.
- [x] Measure full-data startup/search performance and record actual counts and unavailable-source reasons in the report. Run full suite and commit generated artifacts.

### Task 7: Document, review and verify the delivered feature

- [x] Update README, 0.3.0 release notes, build/coverage instructions, keyboard map, offline behavior, installation and effect-label limitations.
- [x] Run `python3 -B -m unittest -q`, CLI smoke checks, `git diff --check`, and Ubuntu container tests when Docker access permits. Report any blocked environment checks truthfully.
- [x] Obtain one fresh-context whole-branch review against the spec, fix important findings through regression tests, and verify the whole suite.
- [x] Commit the feature checkpoint on the isolated branch. Present working launch instructions and exact validation results; integrate/publish according to the user's authorized Git workflow.

## Execution notes

The user authorized proceeding with the agreed design. Execute natively in the
isolated `codex/command-search` branch, continuously through these tasks, with
one final independent review. Routine implementation choices stay with the
implementer; record material deviations in the execution ledger.
