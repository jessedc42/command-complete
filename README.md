# command-complete

Draft UNIX commands in a standalone terminal editor. The editor looks up candidates in its bundled database. It prints the draft when you finish.

## Versioning

The current version is 0.2.0. Run `command-complete --version` to check the installed version. The version lives in `command_complete.py` and releases use annotated Git tags such as `v0.2.0`. See the [v0.2.0 release notes](releases/v0.2.0.md).

During 0.x development, feature additions and breaking changes increase the minor version. Backward-compatible bug fixes increase the patch version. Version 1.0.0 will establish a stable command-line interface.

## Use it

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

The [coverage audit](coverage.md) lists commands with partial or missing flag descriptions in the latest audited snapshot.

- The snapshot includes executable names from your macOS Bash login PATH. Standard UNIX flags come from installed manual pages where available, including documented Git, GitHub CLI, and Docker subcommands. Terraform help supplies flags for its main workflows.
- AWS CLI v2 coverage comes from the AWS installation’s autocomplete index. It includes service operations, waiters, custom subcommands bundled with the CLI, and global flags. [AWS CLI source](https://github.com/aws/aws-cli/tree/v2)
- kubectl coverage comes from the installed client’s help, including nested subcommands, aliases and global flags. It includes a static list of common resource types. [kubectl reference](https://kubernetes.io/docs/reference/kubectl/)
- Docker coverage comes from the installed CLI's help tree, including built-in command groups and the installed Compose and Buildx plugins. Commands such as `docker stop` and `docker container stop` include flags, descriptions, and argument hints. Importing this help uses the client and does not require a running daemon.
- Completion works on one command at a time. Live resource names, AWS profile names, custom aliases, plugins, filenames, and shell pipelines are outside the snapshot. Some PATH executables only have name completion because they lack a usable local manual. Man-page extraction is best effort.

## Refresh and verify

Python 3.10 or newer with curses is sufficient for the editor, with no packages to install. Rebuild after changing PATH or upgrading AWS CLI or kubectl. The builder reads local manuals and installed CLI help and does not probe arbitrary binaries on PATH.

```bash
cd ~/projects/command-complete
python3 -B build_catalog.py
python3 -B -m unittest -v
```

Use `--aws-index /path/to/ac.index` if your AWS install stores its index outside the packaged location. Manual flag extraction uses `mandoc` and `manpath`.

### Test in Ubuntu with Docker

```bash
bash test-ubuntu.sh
```

This runs the tests in an Ubuntu 24.04 amd64 container. The repository is mounted read-only, and Python is installed inside the container. The tests exercise the terminal UI through a pseudoterminal, including the Bash Ctrl+G handoff and a check that the draft stays editable until a separate Enter. macOS-specific tests are skipped on Ubuntu. Docker removes the container when the run finishes.
