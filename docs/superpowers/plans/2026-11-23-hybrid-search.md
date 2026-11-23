# Hybrid Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Implement the approved 250 ms idle/Space-immediate search while keeping input responsive.
**Architecture:** A latest-query scheduler runs cancellable searches off the curses thread. Independent SQLite readers transfer completed lazy snapshots to the UI; session and editor accept only current results.
**Tech Stack:** Python 3.10+ standard library, threading, sqlite3, curses, unittest.
**Spec:** docs/superpowers/specs/2026-11-23-hybrid-search-design.md

## Global Constraints

- Preserve complete catalogs, inclusive word-prefix ranking, strict filters, frozen results, and literal editable shell handoff.
- Python standard library only. No runtime network or changed data/schema requirement.
- Use 250 ms idle delay, immediate Space, responsive input, and discard outdated results.
- Keep --matches synchronous. No release/version change. Jesse runs Git add/commit/push.

## Review Focus

- A slow old query must not replace current text/results or block typing/cancellation.
- Navigation/Enter arriving before results must never choose stale entries.
- Frozen SQLite snapshots stay usable after later background queries and backtracking.
- Keyboard timeouts must not busy-redraw the terminal or alter cc draft behavior.
- Shutdown and repeated canceled searches must close resources without cross-thread SQLite errors.

### Task 1: Schedule and own background search snapshots

Files: create search_scheduler.py and test_search_scheduler.py; modify command_search_index.py.
Interfaces: HybridSearch(search, delay=.25), request(query, immediate=False), poll(), expedite(), pending, close(). Backend search_background(query, cancelled) returns SearchResults with owned lazy reader.

- [x] Add failing tests for coalesced idle deadlines, immediate dispatch, blocked worker responsiveness, outdated-result rejection, errors/cancellation, and real SQLite snapshot handoff/lifetime.
- [x] Run python3 -B -m unittest test_search_scheduler -q; observe failure.
- [x] Implement scheduler and independent cancellable readers; preserve direct search API.
- [x] Run targeted tests and full suite; record evidence. Leave changes uncommitted.

### Task 2: Integrate hybrid terminal behavior and verify

Files: modify command_search_session.py, command_search.py, test_search_terminal.py, README.md.
Interfaces: optional scheduler in SearchSession, poll_search(), search_pending and expedited query handling; existing synchronous sessions remain compatible.

- [x] Add failing real-terminal tests for idle/Space updates, typing during blocked search, stale freeze protection, and deferred Enter/navigation preserving queued draft input.
- [x] Integrate scheduler polling with timeout input, current-query results/status, and queued selection intent. Close worker before index cleanup.
- [x] Run full suite with ResourceWarning errors, CLI checks and git diff --check; compare input/search timing on the full catalog.
- [x] Obtain one fresh-context independent review; regression-test Important findings, then rerun full suite.
- [x] Update README and record verification. Supply exact relevant Git commands; no automatic commit, merge or push.
