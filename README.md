# command-complete and command-search

Find a UNIX command by what you want to do, then draft it with live autocomplete. Both utilities use bundled, platform-specific data and Python's standard library. They never execute the draft.

- `command-search` / `cs`: search by task keywords, keep the results visible, and compose a command with cc.
- `command-complete`: start directly with a command draft and complete its subcommands, flags, and arguments.

## Versioning

The current version is 0.3.0. Both entry points read `version.py`. Run `command-complete --version` or `cs --version` to check. Releases use annotated Git tags such as `v0.3.0`. See the [v0.3.0 release notes](releases/v0.3.0.md).

During 0.x development, feature additions and breaking changes increase the minor version. Backward-compatible bug fixes increase the patch version. Version 1.0.0 will establish a stable command-line interface.

## Install

Python 3.10 or newer with curses and SQLite is sufficient. No third-party Python packages are needed. Keep this repository in place: the installer creates symlinks to its scripts and data.

```bash
cd ~/projects/command-complete
python3 -B install_commands.py
export PATH="$HOME/.local/bin:$PATH"
source ~/projects/command-complete/shell-integration.sh
```

The installer adds `command-complete`, `command-search`, and `cs` in `~/.local/bin`. It refuses to replace an unrelated existing executable or symlink. Use `--bin-dir /another/directory` if a name is already taken. It does not edit shell startup files; add the PATH and source lines to your supported shell's startup file if desired.

Shell shortcuts require **Bash 5+ or zsh**. From the shell prompt, **Ctrl+G** opens cc; **Ctrl+X, then Ctrl+G** opens cs. The existing shell input seeds the editor or keyword query. A finished draft replaces that input and stays editable until you press Enter again at the shell prompt. Cancellation restores the original input. Standalone invocations print their final draft to stdout.

To customize the search shortcut, set `COMMAND_SEARCH_KEY_BINDING` before sourcing the integration. Use the shell's native key notation: for example, `export COMMAND_SEARCH_KEY_BINDING='\C-x\C-s'` in Bash or `export COMMAND_SEARCH_KEY_BINDING='^X^S'` in zsh. `COMMAND_COMPLETE_EXECUTABLE` and `COMMAND_SEARCH_EXECUTABLE` can override the scripts used by the widgets.

In Bash vi editing mode, a configured Ctrl+X search sequence reserves that prefix so a pause between the keys does not insert a literal control character. The global Readline key timeout is unchanged. Source the integration before adding any other custom vi-mode Ctrl+X bindings.

## Search by purpose

```bash
cs network reachability dog
cs get disk space
cs set stop containers
cs get inspect instances
cs --matches get disk space
```

Results update after a **250 ms pause in typing**; **Space** requests an immediate search. Searching runs in the background so you can keep editing or cancel while a broad query is running. Waiting/searching status appears while current results are being prepared. Outdated results are discarded. Arrow navigation and Enter also request the current query immediately; a pending choice is applied when its results arrive. Initial keywords supplied at launch search immediately. `--matches` continues to run directly without an idle delay.

Each row shows a command form and a brief purpose hint. Matching is case-insensitive and uses word prefixes: `reach` matches `reachable` and `reachability`. Ordinary keywords use inclusive OR matching, so adding `dog` does not remove ping from a network reachability search. More distinct matched query words rank first; ties sort alphabetically by command form. Repeated query words do not add score.

The complete words `get` and `set` are strict effect filters. `get` means an intended observation; `set` means deliberate mutation. Argument-dependent forms have `depends`, and insufficient evidence gives `unknown`; neither appears under a strict filter. `get set` is a query error. A filter alone lists matching entries alphabetically. An empty query shows instructions.

Effects describe catalog forms, not arbitrary edited shell text. For example, a formatting flag on a mutating operation retains the operation's effect. These labels and the documented conflict checks are reference metadata, not a complete validator.

### Search, freeze, draft

1. Type keywords and navigate with Up/Down or Page Up/Page Down. **Enter with no highlight** freezes all results and waits for a complete command path followed by a space. For example, enter `docker stop ` to open that command's drafting pane. Known command groups require a runnable subcommand, unless a help/version option is selected.
2. **Enter on a highlighted result** freezes the same list and starts its command immediately. A flag requiring a value opens a guided prompt. Placeholders stay out of the draft.
3. Drafting divides the screen top/bottom: frozen hits for that command above, live cc below. The command name appears once in the reference; flags use two columns in a wide terminal and one in a narrow terminal. All results remain scrollable.

| Key | Action |
| --- | --- |
| F6 | Switch between frozen reference and live draft |
| Arrows / Page Up / Page Down | Navigate the active list; Left/Right selects reference columns |
| Enter in reference | Add the highlighted flag or combination, then return to drafting |
| Tab / Shift+Tab in draft | Use normal cc completion |
| Enter with a highlighted completion | Insert that completion and keep drafting |
| Enter at a guided value | Confirm the value and request the next required value |
| Enter with no selection or pending value | Return the unexecuted draft |
| Ctrl+R | Back one stage, preserving query, list position, and per-command drafts |
| Esc | Dismiss completion suggestions |
| Ctrl+C / Ctrl+D | Cancel the session |

Known conflicting reference flags remain visible and dimmed with a reason; selecting one leaves the draft unchanged. Existing nonrepeatable options and their values are preserved. Guided combinations such as a limited, paced ping request each argument in order. Free-form and quoted values do not need to match the database.

Manually typed redirections, pipelines, and other shell operators remain literal draft text and can be returned normally. Completion pauses for unsupported shell suffixes. Reference insertion explains why it cannot append options after an operator or an option-terminating `--`; edit those portions manually.

`cs --matches` emits tab-separated score, effect, command form, and description. `--catalog` and `--database` select an alternate matching snapshot pair.

## Complete a command

```bash
command-complete
command-complete 'aws eks update-kub'
command-complete 'kubectl get pods --all'
command-complete --matches 'aws ec2 describe-instances --instance'
```

Pass the initial draft as one quoted argument to preserve its spacing and quotes.

- Suggestions appear below the draft as you type and narrow with each edit.
- Flags appear in cyan with a short description beside them when local documentation provides one. Descriptions use the terminal's normal text color. Set `NO_COLOR` to use a monochrome list. Selecting a row inserts the flag text.
- **Down** highlights the first suggestion. **Up/Down** moves one match at a time. **Page Up/Page Down** jumps a screenful at a time.
- **Enter** inserts a highlighted suggestion and leaves the draft open for editing. With nothing highlighted, **Enter** exits and prints the draft as text.
- **Tab** inserts a unique match. For multiple matches, **Tab/Shift+Tab** moves through the list.
- **Esc** hides suggestions until you edit the draft or press **Tab**. **Ctrl+C** or **Ctrl+D** cancels.
- Arrow keys, Home, End, Backspace, Delete, Ctrl+A, Ctrl+E, Ctrl+U and Ctrl+K edit the draft.
- **`--matches`** prints one candidate per line for piping or scripting.

### Free-form arguments

Try `command-complete 'nc '`. Type a host and press **Space** to advance to the port. Enter any host or port as draft text. For multiword values, quote the value and press **Space** after the closing quote.

The editor shows argument labels when the snapshot knows what comes next. Try `nc -w ` for a timeout in seconds, `kubectl -n ` for a namespace, or `mkdir ` for a directory name. The builder imports straightforward argument forms from installed manuals, kubectl help, and the AWS CLI index. Curated labels cover common forms such as `aws s3 cp ` and its source and destination paths. If you want flag suggestions at an argument prompt, start with `-`.

The suggestion list filters documented conflicts covered by the snapshot. For example, after `nc -l -`, it omits `-p`, `-s`, and `-z`. The kubectl rules cover kustomize conflicts in `apply`, `create`, and `delete`. You can still type any flag by hand. Enter returns the draft as typed.

### Syntax examples

AWS `--query` shows a few JMESPath expressions with explanations. Generic examples use placeholder field names that you adapt to the response JSON. `aws ec2 describe-instances --query` has examples using instance fields. [AWS query documentation](https://docs.aws.amazon.com/cli/latest/userguide/cli-usage-filter.html)

`awk` program arguments and `sed` expressions, including `sed -e`, also show examples. The panel stays visible while you type inside quotes. Press Space after the closing quote to continue with the next argument. Examples serve as reference text while you write. [AWK manual](https://www.gnu.org/software/gawk/manual/gawk.html) and [sed manual](https://www.gnu.org/software/sed/manual/sed.html)

### Return a draft to the shell prompt

Use the shell integration to place the finished draft in the shell's editable command line. In an interactive zsh or Bash 5+ session, run:

```sh
source ~/projects/command-complete/shell-integration.sh
```

Press **Ctrl+G** from the shell prompt, either on an empty line or after typing the start of a command. Inside the editor, **Enter** inserts a highlighted suggestion. **Enter** with nothing highlighted returns the draft to the shell. You can edit it normally. Press **Enter at the shell prompt** when you want to run it. Cancelling the editor takes you back to the original draft.

The macOS `/bin/bash` shipped on this machine is Bash 3.2. Start Homebrew Bash with `/opt/homebrew/bin/bash`, or zsh with `/bin/zsh`, and run the `source` command above. You can add that source line to your supported shell's startup file to load the binding automatically. The standalone `command-complete` command continues to print drafts to the terminal.

## Coverage

The editor detects macOS or Ubuntu 24.04 at startup and loads that platform's offline catalog. The Ubuntu catalog includes 2,670 executable names from Ubuntu 24.04.5, metadata imported from 2,278 installed manuals, and portable AWS CLI, kubectl, and Docker schemas. Those optional CLIs remain available in the catalog when absent from the host.

Ubuntu entries use their own documentation. For example, GNU `ls --block-size` is available on Ubuntu, and the Ubuntu OpenBSD netcat rules allow `nc -l -p`. The macOS catalogs retain their own flags and conflict rules. Commands without usable manual entries have name completion.

To collect Ubuntu documentation from a Mac, replace `USER@UBUNTU_HOST` with your SSH destination:

```sh
ssh -T USER@UBUNTU_HOST 'bash -lc "python3 - --manuals"' \
  < collect_inventory.py > ubuntu-command-reference.json
python3 -B build_catalog.py --inventory ubuntu-command-reference.json
```

The collector reads installed manuals with `man`. The Ubuntu builder imports those manuals without requiring AWS CLI, kubectl, or mandoc on Ubuntu. Without collected manuals, the Ubuntu catalog provides executable names and the portable CLI schemas.

The raw inventory and reference JSON files are local build inputs ignored by Git. The bundled `catalog-ubuntu.json.gz` supplies the offline Ubuntu catalog.

The [search coverage audit](search-coverage.md) reports current command/flag descriptions, indexed forms, term enrichment, effects, timings, and remaining gaps for both platforms. Compressed `search-coverage-macos.json.gz` and `search-coverage-ubuntu.json.gz` contain individual missing records and source outcomes. Gap reasons distinguish missing or unread sources, extraction gaps requiring review, synopsis/example evidence, and legacy spellings absent from current sources. Every catalog command and scoped flag is indexed, including inherited flags and entries without descriptions. Such entries remain searchable by their names and verified terms and display `Description unavailable` when needed. The older [completion audit](coverage.md) records the pre-search snapshot.

- The snapshot includes executable names from your macOS Bash login PATH. Standard UNIX flags come from installed manual pages where available, including documented Git, GitHub CLI, and Docker subcommands. Terraform help supplies flags for its main workflows.
- AWS CLI v2 schemas come from the installation's autocomplete index. Operation and parameter descriptions come from its botocore reference models, global CLI data, and built-in help. This includes service operations, waiters, custom subcommands, and global flags. [AWS CLI source](https://github.com/aws/aws-cli/tree/v2)
- kubectl coverage comes from the installed client’s help, including nested subcommands, aliases and global flags. It includes a static list of common resource types. [kubectl reference](https://kubernetes.io/docs/reference/kubectl/)
- Docker coverage comes from the installed CLI's help tree, including built-in command groups and the installed Compose and Buildx plugins. Commands such as `docker stop` and `docker container stop` include flags, descriptions, and argument hints. Importing this help uses the client and does not require a running daemon.
- Completion works on one command at a time. Live resource names, AWS profile names, custom aliases, plugins, filenames, and shell pipelines are outside the snapshot. Some PATH executables only have name completion because they lack a usable local manual. Man-page extraction is best effort.

## Offline data and refresh

Search uses bundled compressed SQLite databases, without runtime network access or optional SQLite extensions. On first use, the selected database expands into `$XDG_CACHE_HOME/command-complete`, or `~/.cache/command-complete` by default. The cache is keyed by the compressed file's SHA-256; deleting that app cache safely forces regeneration. The compressed platform databases total approximately 130 MB, and expanded caches require additional disk space. Updated snapshots create new cache files; older cached copies can be removed when no longer needed.

The database fingerprints its matching completion catalog. Rebuild search data after changing a completion snapshot; cs rejects a mismatched pair instead of using stale metadata.

Python 3.10 or newer with curses is sufficient for the editor, with no packages to install. Rebuild after changing PATH or upgrading AWS CLI or kubectl. The builder reads local manuals and installed CLI help and does not probe arbitrary binaries on PATH.

```bash
cd ~/projects/command-complete
python3 -B build_catalog.py
python3 -B build_search_catalog.py --ubuntu-reference ubuntu-command-reference.json
python3 -B -m unittest -v
```

Use `--aws-index /path/to/ac.index` if your AWS install stores its index outside the packaged location. Manual flag extraction uses `mandoc` and `manpath`.

`build_search_catalog.py` imports available installed AWS models/help, Docker/kubectl/Terraform client help, rclone flag help, local macOS manuals, and collected Ubuntu manuals. It retains bundled documentation when optional source tools are absent and records that outcome. `--aws-models /path/to/awscli/botocore/data` selects an unusual AWS installation; `--platform macos` or `--platform ubuntu` rebuilds one snapshot. Build tools may call those documentation commands; interactive search does not.

Maintain purpose vocabulary, explicit effects, and useful combinations in `search_overrides.json`. Command overrides are keyed by full command paths; put flag overrides on canonical command paths so aliases inherit them. Recipes contain structured `options` with `flag`, required `arguments`, or fixed `values`, plus a description/effect/terms. They are curated combinations, not arbitrary flag permutations. Rebuilding preserves this separate override file.

Before publishing a final release, review the detailed coverage reports: available documentation must be imported; remaining genuinely unavailable records must stay explicit. Missing metadata is not filled with invented prose or an assumed effect.

### Test in Ubuntu with Docker

```bash
bash test-ubuntu.sh
```

This runs the tests in an Ubuntu 24.04 amd64 container. The repository is mounted read-only, and Python is installed inside the container. The tests exercise both terminal editors through pseudoterminals, both bundled platform datasets, and Bash editable-buffer handoff without execution. macOS-specific tests are skipped on Ubuntu. Docker removes the container when the run finishes.
