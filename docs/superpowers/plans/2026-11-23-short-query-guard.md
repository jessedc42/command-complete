# Optional Short-query Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add the approved default-off guard and prepare shared version 0.4.0.
**Architecture:** Session policy separates the typed query from its automatic effective query. Existing scheduler runs completed-keyword searches; explicit interaction resubmits the full query. CLI/env configuration and own-command metadata expose the switch.
**Tech Stack:** Python 3.10+ standard library, curses, sqlite3, unittest.
**Spec:** docs/superpowers/specs/2026-11-23-short-query-guard-design.md

## Global Constraints

- Guard optional, default off. Hold only unfinished suffixes shorter than three searchable characters; keep completed keywords useful.
- Space, Enter and existing result navigation explicitly submit full current text. Explicit initial queries and --matches remain direct.
- Preserve complete catalogs/ranking/filtering, frozen snapshots, standard-library-only operation and unexecuted shell handoff.
- Shared version 0.4.0, release notes; Jesse executes all Git writes and publication commands.

## Review Focus

- Backspacing across the threshold must cancel obsolete full queries and never show them as current results.
- A held suffix must not silently affect or masquerade as the completed-keyword search.
- Enter/navigation on partial results must resubmit current full text before selecting/freezing.
- CLI override must beat environment settings; invalid configuration must produce useful errors.
- New bundled flags and aliases must match runtime and database fingerprints on both platforms.

### Task 1: Guard policy and terminal configuration

Files: command_search_session.py, command_search.py, test_search_scheduler.py, test_search_terminal.py.
Interfaces: SearchSession(..., short_query_guard=False), guard_waiting, guard_hint, expedite_search(); existing set_query immediate flag marks explicit submission. CLI BooleanOptionalAction with env fallback.

- [x] Add failing tests for off/on, suffix threshold/deletion, completed keywords, cancellation, explicit Space/Enter/navigation and no stale freeze.
- [x] Add CLI/env and real PTY tests for guarded waiting, completed-word hints and short-query override.
- [x] Implement policy, current-query explicit submission and configuration; run targeted tests then full suite with ResourceWarning errors.

### Task 2: Version, data, notes and review

Files: version.py, README.md, releases/v0.4.0.md, build_search_catalog.py, both catalogs/indexes/coverage reports and bundled acceptance tests.

- [x] Add acceptance tests for own public guard flags and help descriptions; observe missing entries.
- [x] Register flags and regenerate both search snapshots from existing enriched catalogs without unrelated documentation refresh.
- [x] Prepare version 0.4.0 and release notes, including hybrid scheduling and vi-mode fix since latest local tag v0.2.0.
- [x] Run full suite, both version commands, configuration/CLI checks, diff checks and Ubuntu validation when available.
- [x] Obtain one fresh-context review; regression-test Important findings in one pass, then rerun full suite.
- [x] Record results and supply exact user-run Git/tag/GitHub draft-release commands. Preserve unrelated packaging documents.
