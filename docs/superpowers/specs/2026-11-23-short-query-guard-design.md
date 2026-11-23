# Optional short-query guard

The user approved an optional three-character automatic-search guard, default
off, after choosing the hybrid search. Prepare minor version 0.4.0 from 0.3.0
under the repository's 0.x feature policy, with release notes and user-run Git
and release commands. Do not commit, merge, tag or publish automatically.

When enabled, an automatic interactive edit holds the final unfinished keyword
if it has fewer than three searchable characters. Earlier whitespace-completed
keywords remain searchable, with an explicit hint that the short suffix has
not yet been included. With no earlier keywords, do not query the database.
Deleting back to a short unfinished keyword follows the same rule.

Space and Enter submit the full query. Preserve existing navigation-as-explicit-
submission behavior as well; selection/freezing must use full current-query
results, not an old partial result list. Preserve explicit initial launch
queries and --matches behavior. Guard off preserves the current hybrid rules.

Expose --short-query-guard / --no-short-query-guard. An exported
COMMAND_SEARCH_SHORT_QUERY_GUARD boolean enables the guard for shell hotkeys;
CLI flags override the environment. Accept 1/0, true/false, yes/no, on/off;
reject invalid values with a clear error when no CLI override is supplied.

Keep Python standard-library-only operation, complete catalogs, OR/ranking,
strict effect filters, frozen snapshots, and literal unexecuted shell handoff.
Update both bundled own-command schemas/search indexes for the public flags.
Carry the previously uncommitted Bash vi-prefix fix into the release.
