# command-complete

Draft UNIX commands in a standalone terminal editor. The editor looks up candidates in its bundled database. It prints the draft when you finish.

## Use it

```bash
command-complete
command-complete 'aws eks update-kub'
command-complete 'kubectl get pods --all'
command-complete --matches 'aws ec2 describe-instances --instance'
```

Pass the initial draft as one quoted argument to preserve its spacing and quotes.

- Suggestions appear below the draft as you type and narrow with each edit.
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

### Return a draft to the shell prompt

Use the shell integration to place the finished draft in the shell's editable command line. In an interactive zsh or Bash 5+ session, run:

```sh
source ~/projects/command-complete/shell-integration.sh
```

Press **Ctrl+G** from the shell prompt, either on an empty line or after typing the start of a command. Inside the editor, **Enter** inserts a highlighted suggestion. **Enter** with nothing highlighted returns the draft to the shell. You can edit it normally. Press **Enter at the shell prompt** when you want to run it. Cancelling the editor takes you back to the original draft.

The macOS `/bin/bash` shipped on this machine is Bash 3.2. To use prompt handoff from there, start a zsh session with `/bin/zsh` and run the `source` command above. The binding applies to the current shell session. The standalone `command-complete` command continues to print drafts to the terminal.

## Coverage

- The snapshot includes executable names from your macOS Bash login PATH. Standard UNIX flags come from installed manual pages where available, including documented Git, GitHub CLI, and Docker subcommands. Terraform help supplies flags for its main workflows.
- AWS CLI v2 coverage comes from the AWS installation’s autocomplete index. It includes service operations, waiters, custom subcommands bundled with the CLI, and global flags. [AWS CLI source](https://github.com/aws/aws-cli/tree/v2)
- kubectl coverage comes from the installed client’s help, including nested subcommands, aliases and global flags. It includes a static list of common resource types. [kubectl reference](https://kubernetes.io/docs/reference/kubectl/)
- Completion works on one command at a time. Live resource names, AWS profile names, custom aliases, plugins, filenames, and shell pipelines are outside the snapshot. Some PATH executables only have name completion because they lack a usable local manual. Man-page extraction is best effort.

## Refresh and verify

Python 3.10 or newer with curses is sufficient for the editor, with no packages to install. Rebuild after changing PATH or upgrading AWS CLI or kubectl. The builder reads local manuals and installed CLI help and does not probe arbitrary binaries on PATH.

```bash
cd ~/projects/command-complete
python3 -B build_catalog.py
python3 -B -m unittest -v
```

Use `--aws-index /path/to/ac.index` if your AWS install stores its index outside the packaged location. Manual flag extraction uses `mandoc` and `manpath`.
