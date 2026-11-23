# Hybrid command-search updates

The user approved the proposed hybrid: wait briefly after typing, search
immediately on Space, keep input responsive while searching, and discard
outdated results. Use 250 ms as the default idle interval from the proposed
200–300 ms range.

Approaches considered: strict Space-only searching delays useful feedback until
a word boundary; a keyword-count threshold excludes useful single-word searches
and can increase work under OR matching. The approved hybrid retains live
feedback without searching every intermediate prefix.

Keep Python standard-library-only operation, current complete catalogs,
ranking/filter semantics, frozen snapshots, and unexecuted shell handoff.
No release or catalog rebuild is requested.

A scheduler coalesces edits and runs one cancellable background search at a time.
Each query owns a separate SQLite connection; completed results may be handed
to the UI without concurrent connection access. Frozen results retain their
reader until released. Poll the scheduler without redrawing idle screens.
Show waiting/searching status; clear obsolete live matches on an edit. Selection
and Enter must never use stale results. Enter/navigation may expedite a pending
query, preserving fast typing/selection sequences. Cancellation stops queued and
running work and closes owned resources.

The implementer chooses internal interfaces and worker details. Keep CLI
`--matches` synchronous. Leave Git add/commit/push for Jesse to run, as requested.
