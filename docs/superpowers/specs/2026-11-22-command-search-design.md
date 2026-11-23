# command-search (cs)

Status: implemented on `codex/command-search`; integration and final release gates
remain separate. See the [implementation review](../reviews/2026-11-22-command-search.md).

## Intent

Help a user discover a command from words describing a task, then compose its
flags and arguments while keeping the relevant search results visible. Return
the resulting draft to the shell's editable input buffer. The utility never
executes that draft.

The user chose complete coverage of command-complete's existing macOS and
Ubuntu catalogs for the first release. A small curated command collection is
not an acceptable substitute for that coverage.

## Agreed constraints and approaches

- Use only Python's standard library at runtime and in Python build tools.
- Search entirely offline against bundled data. Import documentation and
  rebuild the search data through a separate explicit build command.
- Share one repository, installation, and release version with command-complete.
- Provide `command-search` and its short entry point `cs`; retain the existing
  `command-complete` entry point and its behavior.
- Preserve platform selection: macOS and Ubuntu 24.04 use their matching
  catalogs. Retain portable AWS CLI, kubectl, and Docker entries when their
  executables are absent from the current machine.

Two packaging approaches were considered. Separate repositories depending on
a shared Python package would permit independent releases but add installation
and compatibility work. Jesse chose two entry points in the existing
repository, sharing reusable modules and catalogs, with one release version.
Search purpose metadata is maintained separately from imported completion
metadata so rebuilding completion data can preserve curated information.

This is a complete feature addition during 0.x development and therefore calls
for a minor version increment under the repository's existing SemVer policy.
Preparing a release does not imply publishing it or pushing Git changes.

## Search entries and metadata

Index every command path and scoped flag available through cc, including its
inherited global flags. An entry can represent:

1. A command or subcommand path.
2. A command path with one flag, including its required argument labels.
3. A curated, useful combination of flags, including fixed values or required
   arguments. Do not generate arbitrary flag permutations.

Each entry has a stable identity, platform applicability, command path,
structured option/argument components, a concise purpose hint, searchable
terms, one effect classification, and metadata provenance. Keep display labels
separate from insertable tokens. Argument placeholders are never inserted as
literal shell syntax.

Terms should describe the task and its concepts. For example, ping should be
discoverable through terms such as network, ICMP, reachability, reachable, and
test. Command and option names are searchable too. Preserve the distinction
between a command's context and an option's specific purpose; a formatting
option must not turn a mutating operation into a `get` operation.

Effect belongs to the specific command form, not its executable alone:

- `get`: its intended task observes or returns information.
- `set`: its intended task deliberately changes state.
- `depends`: its behavior is known to depend on the supplied program or
  arguments, as with a general-purpose interpreter.
- `unknown`: available evidence does not establish a classification. This is
  distinct from known argument-dependent behavior.

Classifications describe catalog entries, not a guarantee about an arbitrary
edited shell draft. Use explicit overrides and documentation-backed rules;
command-name heuristics alone must not assert a verified effect.

### Documentation and complete coverage

The inspected snapshots contain 22,929 macOS command paths and 23,587 Ubuntu
command paths. They contain 176,342 and 222,944 stored flag entries respectively;
29,633 and 68,677 of those currently have flag descriptions. They have no general
command-purpose description field. This is a substantial enrichment task.

Extend documentation import to preserve command summaries and option purposes
from manuals and existing CLI help sources. Import AWS operation and parameter
documentation from suitable versioned documentation or structured reference
data, using standard-library parsers. Determine actual available source formats
during implementation; do not assume the completion index contains descriptions.
Supplement imported text with maintained task vocabulary, synonyms, effect
rules, and curated combinations. Retain sources and override precedence.

Every existing command and flag must still be indexed when descriptive
metadata is unavailable. Such entries match their names and any verified terms,
show an explicit missing-description hint when appropriate, and use `unknown`
when their effect is not established. They are excluded from strict effect
filters. Do not invent descriptions to fill gaps.

Produce a coverage report distinguishing indexed coverage, description coverage,
term enrichment, classifications, and reasons for missing metadata. Do not
silently treat an unimplemented importer as evidence that documentation does
not exist. At runtime, missing executables do not hide bundled entries.

### Agreed final-release requirement

Jesse explicitly requires importing available documentation before the final
release. Complete indexing alone does not satisfy this requirement. Every entry
with usable documentation must receive its available descriptive metadata and
relevant purpose terms. An importer that has not yet captured available
documentation represents unfinished release work.

In particular, the current AWS description gap is primarily an importer gap:
the autocomplete SQLite index lacks prose, while installed AWS reference models
contain operation and parameter documentation. Import those local sources with
standard-library tools and make the resulting descriptions available to both
cs and cc. Supplement other documented families through their appropriate
sources. Genuinely unavailable or inconclusive metadata must remain explicit in
the coverage report, with truthful unknown classifications where needed.

This requirement is a gate for the eventual product release. A design checkpoint
may be committed and pushed before the implementation and enrichment are complete.

## Search rules

Use case-insensitive word-prefix matching. For example, `net` matches `network`,
and `reach` can match `reachable` and `reachability`. Match terms, not arbitrary
interior substrings. Ordinary keywords are inclusive: any matched keyword makes
an entry eligible. Thus `network reachability dog` retains ping even when ping
does not match dog. Adding a new keyword can broaden the result set under this
OR rule; completing an existing word can narrow it.

Score by the number of distinct input keywords matched, counting each input
keyword at most once regardless of duplicate terms or synonyms. Sort by descending
score, then ascending case-insensitive command-form text, then stable entry ID.
Do not introduce history-based ranking or extra relevance weights.

The exact words `get` and `set` are strict filters rather than scoring keywords.
For `get network reachability dog`, first restrict to get entries and then apply
OR matching and ranking to the remaining keywords. Entries have one effect, so
specifying both filters is contradictory and should show a concise query error.

Proposed defaults for unspecified query details:

- Deduplicate identical query words. Treat whitespace as word boundaries and
  consistently tokenize hyphenated command names and description text.
- Activate a get/set filter when the complete input token equals that word.
  Prefixes such as `ge` remain ordinary prefix queries.
- A filter-only query lists that effect's entries alphabetically.
- An empty query shows a short instruction and example searches. No automatic
  result selection or implicit freezing occurs.
- Zero results leaves the query editable and explains that no entries match.
  Enter cannot select or freeze an empty result set.

These defaults are designer proposals for approval, not additional decisions
already supplied by Jesse.

## Interaction states

### 1. Live search

The whole screen displays the editable keyword query and ranked live results.
Each result shows a command form and a brief purpose hint to its right, with
distinct styling for command/flag text and hints. All matches are reachable
through scrolling; do not silently cap the result set at the visible rows.

With nothing highlighted, Enter freezes the complete result set and its order,
then opens the command-entry state. With a result highlighted, Enter freezes
the same complete result set and seeds the draft from that selected entry,
going directly into completion or its guided argument sequence.

### 2. Frozen results and command entry

Keep the complete frozen result list visible at full height. Show an editable
command draft. Wait until it contains a matching complete command path followed
by a space before opening cc. For example, `ping ` qualifies; an entry for
`docker stop` requires `docker stop ` rather than just `docker `.

Only command paths represented in the frozen results activate completion.
Flags and user argument values need not match a search entry. Interpret the
draft with the shared shell-word parsing rules; global options before a
subcommand must be handled consistently with cc.

Proposed detail: known namespace-only entries remain discoverable as command
groups, but require a runnable subcommand before they activate drafting.
Whether a path is a command group must come from imported metadata, not merely
the presence of children, since some programs also have valid default actions.

### 3. Frozen reference plus live cc

Use an approximately equal top/bottom split. The top reference pane shows only
the original search hits for the matched command path, preserving their frozen
order. Display that command name once, grouping its matching flag forms beneath
it. Show two entries per row when width permits; use one per row when necessary
for readability. Keep the complete set scrollable and the selected entry in view.

The bottom pane contains the editable draft and cc's live suggestions, argument
hints, and syntax examples. Reuse the completion engine, platform schemas,
documented conflict rules, and text-insertion rules. Do not run a second process
or discard the reference by launching the standalone cc interface.

Frozen means search membership, order, terms, and hints stay fixed. Scrolling,
focus, narrowing the view to the matched command, and marking current conflicts
are presentation changes. Going back restores the full frozen results.

F6 switches focus, with an obvious active-pane indicator. Arrow keys and Page
Up/Down navigate the active list. Reference entries form a keyboard-selectable
grid when displayed two per row; Left/Right move between its columns. In draft
focus, Left/Right edit text and cc's existing navigation remains available.
Tab retains its cc completion behavior in draft focus; it does not switch panes.

Enter on a reference entry adds its options and returns focus to the draft.
Options requiring values show their existing argument hints. Do not insert hint
prose into the command. Known conflicting entries stay visible, dimmed, with
their reason. Selecting one explains the conflict and leaves the draft unchanged.
Conflict detection is limited to documented catalog rules and must not be
presented as complete command validation.

### Guided combinations

For `ping -c <count> -i <seconds>`, insert `-c`, accept and explicitly confirm
the user's count, then insert `-i` and request its value. Use Enter to confirm
the current required value when no completion is selected. A selected completion
is inserted first, following normal cc behavior. After the final guided value
is confirmed, return to ordinary drafting; another Enter with no selection
returns the draft to the shell. Tab still performs completion.

Accept free-form values and quoted strings without requiring a database match.
Do not advance through an unfinished quoted value. Do not supply guessed hosts,
paths, credentials, or other variable argument values. Display remaining recipe
steps so the user can see what is coming. A required value must be filled before
another reference option is inserted.

Proposed insertion details: check a combination's known conflicts before starting
it and recheck pending steps as the draft changes. Reuse an existing identical
switch instead of duplicating it. Preserve existing option values; focus a value
that needs editing rather than silently replacing it. Permit additional instances
where repeatability is documented; manual text entry remains available. Editing
the earlier command text cancels any pending recipe additions while preserving
the visible draft, so stale queued options cannot appear later.

## Backtracking and finishing

Ctrl+R moves back one stage, retaining the query, list position, and unfinished
draft. From completion, restore the full frozen result list; another press
returns to the editable keyword query. Returning to the same command resumes
its draft and any guided step. Choosing a different command starts a fresh
draft. Remember drafts within the session only.

Escape retains cc's suggestion-dismissal behavior. Ctrl+C cancels the whole
session and restores the shell text that existed before invocation. Preserve
cc's Ctrl+D cancellation too. Show contextual controls in the footer.

Proposed detail: editing a draft's command path so that it no longer identifies
a frozen command returns the view to full-height command entry, preserving its
text. Matching another complete frozen command focuses that command's reference.
It does not silently change the frozen query or run a new search.

Ordinary Enter on an unselected completion list finishes the draft, except
while explicitly confirming a required guided argument. Returning to the shell
must leave the draft unexecuted and editable. Use the existing result-file-
descriptor handoff rather than terminal input injection or evaluation.

## Shell and command-line integration

Ctrl+X followed by Ctrl+G invokes cs; keep Ctrl+G for cc. Make the binding
configurable. Reuse the existing Bash 5+ and zsh integration structure.

The current shell input becomes the initial search query. An empty shell input
opens an empty search. Completion replaces that query with the returned draft;
cancel restores the original shell text. Invoking the utility from its short
command is also supported: `cs network reachability` opens a live search using
those initial keywords. As with standalone cc, standalone cs prints the final
draft to stdout; shell integration provides editable-buffer handoff.

Retain cc's supported Python and shell versions. Document installation of both
entry points and ensure an existing unrelated `cs` executable is never silently
overwritten. Install or configure startup-file bindings explicitly through the
documented setup workflow; no automatic shell startup-file rewrites are needed.

## Reuse and implementation latitude

Extract reusable catalog loading, token parsing, option handling, completion,
and terminal editing primitives while preserving standalone cc behavior. Add a
search index, search-specific metadata builder, and a stateful cs terminal UI.
Use structured search-entry components for insertion instead of splitting human
hint strings. Keep imported sources and curated overrides distinguishable.

The implementer chooses module boundaries, JSON/schema names, index data
structures, cache format, screen-sizing thresholds, and build-command spelling.
Do not depend on optional SQLite extensions or a third-party Python package for
basic functionality. Benchmark the complete dataset, including inherited flag
entries, rather than a small sample. Proposed performance targets are a warm
startup within one second and typical search updates within 100 ms on the
development machine; report measurements and tune the index if needed.

## Validation and acceptance

- Every cc command path and scoped option has a corresponding searchable entry
  in its matching platform index. Audit this mechanically, including missing
  metadata and portable optional CLIs.
- Before final release, import available command and option descriptions across
  the complete catalog. Review the coverage report and resolve documented
  entries missed by importers; report genuinely unavailable metadata explicitly.
- Purpose searches include representative system, networking, Docker, kubectl,
  and AWS tasks. Verify terms such as `reachable` and `test` actually discover
  ping; name-only coverage is not a substitute for enriching documented entries.
- OR matching, case-insensitive prefixes, distinct-keyword scoring, alphabetical
  ties, strict filters, depends/unknown behavior, and empty-query cases match
  the specified rules.
- Freezing preserves the full search snapshot. Manual command matching and
  selecting a result both lead to the intended cc state and focused reference.
- Reference insertion, required arguments, guided combinations, quoted values,
  conflicts, scrolling, pane focus, resizing, and backtracking preserve drafts.
- PTY tests verify both supported shells where available, cancellation, and
  that a returned draft does not execute until a separate Enter at the shell.
- Existing cc tests remain passing. Exercise shared behavior on macOS and the
  existing Ubuntu container workflow, reporting any environment limitations.
- All runtime imports are standard-library modules, searches have no runtime
  network requirement, and no completed draft is executed by either utility.

The temporary interactive layout study is at
`/private/tmp/command-search-layout-preview/layouts.html`. Jesse selected the
top/bottom option. It is an illustrative mockup, not product implementation or
a source of real search metadata.
