#!/usr/bin/env python3
"""An offline command-line editor that returns a draft as text."""

import argparse
from collections import defaultdict
import curses
from dataclasses import dataclass
import gzip
import json
import os
from pathlib import Path
import platform
import re
import shlex
import sys
import unicodedata


__version__ = "0.2.0"
DATABASE = Path(__file__).resolve().with_name("catalog.json.gz")
UBUNTU_DATABASE = DATABASE.with_name("catalog-ubuntu.json.gz")
SHELL_WORD = re.compile(r"""(?:[^\s"'\\;&|<>()`]+|'[^']*'|"(?:[^"\\]|\\.)*"|\\.|'[^']*$|"(?:[^"\\]|\\.)*$)+""")
PLAIN_TOKEN = re.compile(r"(?:\[|[\w./=,%@:#?+-]*)", re.ASCII)


def catalog_path(system=None, distribution=None):
    system = platform.system() if system is None else system
    if system == "Darwin":
        return DATABASE
    if system == "Linux":
        if distribution is None:
            distribution = {}
            for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
                key, separator, value = line.partition("=")
                if separator:
                    distribution[key] = value.strip('"')
        if distribution.get("ID") == "ubuntu" and distribution.get("VERSION_ID") == "24.04":
            return UBUNTU_DATABASE
    raise ValueError(f"No command catalog is available for {system}. Supported platforms are macOS and Ubuntu 24.04.")


@dataclass(frozen=True)
class Match:
    text: str
    start: int
    end: int
    description: str = ""


@dataclass(frozen=True)
class Completion:
    matches: list[Match]
    hint: str | None = None
    examples: tuple[str, ...] = ()


def apply_match(line, match):
    space = " " if match.end == len(line) else ""
    insertion = match.text + space
    return line[:match.start] + insertion + line[match.end:], match.start + len(insertion)


def split_at_cursor(line, cursor):
    """Find the current token and decode each earlier shell word as data."""
    words = []
    end = 0
    for token in SHELL_WORD.finditer(line):
        if line[end:token.start()].strip() or token.group().startswith("#"):
            return None
        if token.start() > cursor:
            break
        if token.start() <= cursor <= token.end():
            return words, token.start(), token.end()
        words.extend(shlex.split(token.group()))
        end = token.end()
    if line[end:cursor].strip():
        return None
    return words, cursor, cursor


class Catalog:
    def __init__(self, data):
        self.commands = data["commands"]
        self.values = data.get("values", {})
        self.children = defaultdict(list)
        for command in sorted(self.commands):
            parent, _, word = command.rpartition(" ")
            self.children[parent].append(word)

    def matches(self, line, cursor=None):
        return self.complete(line, cursor).matches

    def complete(self, line, cursor=None):
        cursor = len(line) if cursor is None else cursor
        split = split_at_cursor(line, cursor)
        if split is None:
            return Completion([])
        words, start, end = split
        prefix = line[start:cursor]
        candidates, hint, command, examples = self.candidates(words, prefix, line[end:])
        descriptions = {}
        if command:
            root = words[0]
            if root in ("aws", "kubectl", "docker"):
                descriptions.update(self.commands[root].get("flag_descriptions", {}))
            descriptions.update(self.commands[command].get("flag_descriptions", {}))
        matches = []
        if PLAIN_TOKEN.fullmatch(line[start:end]):
            matches = [Match(word, start, end, descriptions.get(word, "")) for word in sorted(set(candidates))
                       if word.startswith(prefix) and PLAIN_TOKEN.fullmatch(word)]
        return Completion(matches, hint, examples)

    def candidates(self, words, prefix, following):
        if not words:
            return self.children[""], None, None, ()

        root = words[0]
        if root not in self.commands:
            return [], None, None, ()
        command = self.commands[root].get("alias", root)
        flags = self.flags(root, command)
        positional = 0
        script_supplied = False
        pending = None
        pending_index = 0
        options_enabled = True
        used_options = set()
        for word in words[1:]:
            if options_enabled and word == "--":
                options_enabled = False
                pending = None
                continue
            if pending:
                kind = flags[pending]
                arguments = self.commands[command].get("flag_arguments", {}).get(pending, [])
                optional = arguments and arguments[pending_index].endswith(" (optional)")
                if not word.startswith("-") or (kind == "value" and not optional):
                    pending_index += 1
                    if kind != "many" and pending_index >= max(1, len(arguments)):
                        pending = None
                    if not arguments:
                        pending_index = 0
                    continue
                pending = None
            if options_enabled and word.startswith("-") and word != "-":
                names, attached = read_options(word, flags, self.commands[command].get("short_options"))
                if root in ("awk", "sed") and any(name in ("-f", "--file") for name in names):
                    script_supplied = True
                if root == "sed" and any(name in ("-e", "--expression") for name in names):
                    script_supplied = True
                used_options.update(active_option_names(word, names, flags))
                name = names[-1]
                pending_index = 0
                if not attached and flags.get(name) in ("value", "optional", "many"):
                    pending = name
                elif attached and len(self.commands[command].get("flag_arguments", {}).get(name, [])) > 1:
                    pending, pending_index = name, 1
                continue

            child = f"{command} {word}"
            if options_enabled and positional == 0 and child in self.commands:
                command = self.commands[child].get("alias", child)
                flags = self.flags(root, command)
            else:
                positional += 1

        pending_arguments = self.commands[command].get("flag_arguments", {}).get(pending, [])
        optional = pending_arguments and pending_arguments[pending_index].endswith(" (optional)")
        if pending and (not prefix.startswith("-") or (flags[pending] == "value" and not optional)):
            return (self.flag_values(command, root, pending), self.flag_hint(command, root, pending, pending_index),
                    command, self.examples_for(root, command, "flag_examples", pending))

        entry = self.commands[command]
        excluded = set()
        if options_enabled and (not prefix or prefix.startswith("-")) and entry.get("flag_conflicts"):
            active = used_options
            if following.strip():
                active = used_options.union(following_options(following, flags, entry.get("short_options")))
            for left, right in entry["flag_conflicts"]:
                if not active.isdisjoint(left):
                    excluded.update(right)
                if not active.isdisjoint(right):
                    excluded.update(left)

        if options_enabled and prefix.startswith("-"):
            flag, equals, _ = prefix.partition("=")
            if equals:
                if flag in excluded:
                    return [], None, command, ()
                values = [flag + "=" + value for value in self.flag_values(command, root, flag)]
                hint = None
                if flags.get(flag) in ("value", "optional", "many", "attached"):
                    hint = self.flag_hint(command, root, flag)
                return values, hint, command, self.examples_for(root, command, "flag_examples", flag)
            return (flags.keys() - excluded, None, command,
                    self.examples_for(root, command, "flag_examples", prefix))

        arguments = next(
            (labels for option, labels in entry.get("argument_modes", []) if option in used_options),
            entry.get("arguments", []),
        )
        hint = arguments[positional] if positional < len(arguments) else entry.get("repeat_argument")
        suggestions = []
        if options_enabled:
            if positional == 0:
                suggestions = self.children[command] + entry.get("words", [])
            if not suggestions and not prefix and not arguments:
                suggestions = flags.keys() - excluded
        examples = ()
        if not script_supplied:
            examples = self.examples_for(root, command, "argument_examples", str(positional))
        return suggestions, hint, command, examples

    def examples_for(self, root, command, kind, key):
        local = self.commands[command].get(kind, {})
        inherited = self.commands[root].get(kind, {}) if root in ("aws", "kubectl") else {}
        return tuple(local.get(key, inherited.get(key, [])))

    def flags(self, root, command):
        options = self.commands[command].get("flags", {})
        if root in ("aws", "kubectl", "docker") and command != root:
            return self.commands[root]["flags"] | options
        return options

    def flag_values(self, command, root, flag):
        return self.values.get(command, {}).get(flag, self.values.get(root, {}).get(flag, []))

    def flag_hint(self, command, root, flag, index=0):
        if index:
            return self.commands[command]["flag_arguments"][flag][index]
        local = self.commands[command].get("flag_hints", {})
        global_hints = self.commands[root].get("flag_hints", {})
        return local.get(flag) or global_hints.get(flag) or f"Value for {flag}"


def following_options(text, flags, short_options):
    """Read options to the right of the cursor for conflict filtering."""
    text += " "
    split = split_at_cursor(text, len(text))
    if split is None:
        return
    words, _, _ = split
    pending = None
    for word in words:
        if word == "--":
            break
        if pending and (pending == "value" or not word.startswith("-")):
            if pending != "many":
                pending = None
            continue
        pending = None
        if word.startswith("-") and word != "-":
            names, attached = read_options(word, flags, short_options)
            yield from active_option_names(word, names, flags)
            if not attached and flags.get(names[-1]) in ("value", "optional", "many"):
                pending = flags[names[-1]]


def read_options(word, flags, short_options):
    name, equals, _ = word.partition("=")
    if short_options and name not in flags and len(name) > 2 and not name.startswith("--"):
        names = []
        for index, char in enumerate(name[1:], 1):
            option = "-" + char
            names.append(option)
            if flags.get(option) in ("value", "optional", "many"):
                return names, bool(equals) or index < len(name) - 1
        return names, bool(equals)
    return [name], bool(equals)


def active_option_names(word, names, flags):
    _, equals, value = word.partition("=")
    if equals and flags.get(names[-1]) == "switch" and value.lower() in ("false", "f", "0"):
        return names[:-1]
    return names


def visible(value):
    return "".join(char if char.isprintable() else f"\\x{ord(char):02x}" for char in value)


def cell_width(char):
    if unicodedata.combining(char):
        return 0
    return 2 if unicodedata.east_asian_width(char) in "WF" else 1


def draw(screen, line, cursor, completion, selected, first, message, flag_style=0):
    height, width = screen.getmaxyx()
    screen.erase()

    def write(row, text, style=0, column=0, max_columns=None):
        limit = width - column - 1
        if max_columns is not None:
            limit = min(limit, max_columns)
        if row >= height or limit <= 0:
            return
        used = 0
        for index, char in enumerate(text):
            used += cell_width(char)
            if used > limit:
                text = text[:index]
                break
        try:
            screen.addstr(row, column, text, style)
        except curses.error:
            # Terminals can resize between getmaxyx() and addstr().
            pass

    prompt = "> "
    before, after = visible(line[:cursor]), visible(line[cursor:])
    available = max(width - 4, 0)
    used = 0
    start = len(before)
    for char in reversed(before):
        used += cell_width(char)
        if used > available:
            break
        start -= 1
    before = before[start:]
    write(0, prompt + before + after)
    matches = completion.matches
    example_rows = min(len(completion.examples) + 1, max(0, height - 4)) if completion.examples else 0
    hint = f"Argument: {completion.hint}" if completion.hint else ""
    if matches:
        end = min(first + max(height - 3 - example_rows, 0), len(matches))
        heading = f"Matches ({len(matches)})"
        if end > first and (first or end < len(matches)):
            heading += f"  {first + 1}-{end}"
        if hint:
            heading += f"  |  {hint}"
        write(1, heading, curses.A_BOLD)
        description_column = min(6 + max(len(match.text) for match in matches), max(12, width // 2))
        for row, match in enumerate(matches[first:end], start=2):
            active = row - 2 + first == selected
            style = curses.A_REVERSE if active else 0
            name_style = flag_style if match.text.startswith("-") else 0
            write(row, ("  > " if active else "    ") + match.text,
                  style | name_style,
                  max_columns=description_column - 2 if match.description else None)
            if match.description:
                write(row, visible(match.description), style, column=description_column)
    elif hint:
        write(1, hint, curses.A_BOLD)
    if example_rows:
        top = height - 1 - example_rows if matches else 2
        write(top, "Examples", curses.A_BOLD)
        for row, example in enumerate(completion.examples[:example_rows - 1], top + 1):
            write(row, visible(example))
    if height > 1:
        write(height - 1, message)
    try:
        screen.move(0, min(width - 1, len(prompt) + sum(map(cell_width, before))))
        screen.refresh()
    except curses.error:
        pass


EDITOR_HELP = "Enter return text  |  Ctrl+C cancel"
SUGGESTION_HELP = "Up/Down select  |  PgUp/PgDn jump  |  Enter return text  |  Ctrl+C cancel"
SELECTION_HELP = "Enter insert  |  Up/Down move  |  PgUp/PgDn jump  |  Esc hide  |  Ctrl+C cancel"


def edit(screen, catalog, line, cursor):
    curses.set_escdelay(50)
    flag_style = curses.A_BOLD
    if curses.has_colors() and "NO_COLOR" not in os.environ:
        try:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_CYAN, -1)
            flag_style |= curses.color_pair(1)
        except curses.error:
            pass
    completion = catalog.complete(line, cursor) if line[:cursor].strip() else Completion([])
    selected = None
    first = 0
    while True:
        matches = completion.matches
        height = screen.getmaxyx()[0]
        example_rows = min(len(completion.examples) + 1, max(0, height - 4)) if completion.examples else 0
        rows = max(height - 3 - example_rows, 1)
        if selected is not None:
            first = max(selected - rows + 1, min(first, selected))
        message = EDITOR_HELP
        if selected is not None:
            message = SELECTION_HELP
        elif matches:
            message = SUGGESTION_HELP
        draw(screen, line, cursor, completion, selected, first, message, flag_style)
        key = screen.get_wch()
        if key in ("\x03", "\x04"):
            return None
        if key == curses.KEY_RESIZE:
            continue
        if key == "\x1b":
            completion = Completion([])
            selected, first = None, 0
            continue
        if key == "\t" and not matches:
            completion = catalog.complete(line, cursor)
            matches = completion.matches
        if matches and key in (curses.KEY_PPAGE, curses.KEY_NPAGE):
            step = rows if key == curses.KEY_NPAGE else -rows
            current = selected if selected is not None else 0
            selected = max(0, min(len(matches) - 1, current + step))
            first = max(0, min(len(matches) - rows, first + step))
            continue
        if (
            matches
            and key in (curses.KEY_UP, curses.KEY_DOWN, "\t", curses.KEY_BTAB)
            and (key != "\t" or len(matches) > 1)
        ):
            step = -1 if key in (curses.KEY_UP, curses.KEY_BTAB) else 1
            if selected is None:
                selected = 0 if step > 0 else len(matches) - 1
            else:
                selected = (selected + step) % len(matches)
            continue
        previous = line, cursor
        if key in ("\n", "\r", curses.KEY_ENTER):
            if selected is None:
                return line
            line, cursor = apply_match(line, matches[selected])
        elif key == "\t" and matches:
            line, cursor = apply_match(line, matches[0])
        elif key in (curses.KEY_LEFT, "\x02"):
            cursor = max(0, cursor - 1)
        elif key in (curses.KEY_RIGHT, "\x06"):
            cursor = min(len(line), cursor + 1)
        elif key in (curses.KEY_HOME, "\x01"):
            cursor = 0
        elif key in (curses.KEY_END, "\x05"):
            cursor = len(line)
        elif key in (curses.KEY_BACKSPACE, "\x7f", "\b") and cursor:
            line = line[:cursor - 1] + line[cursor:]
            cursor -= 1
        elif key == curses.KEY_DC:
            line = line[:cursor] + line[cursor + 1:]
        elif key == "\x15":
            line = line[cursor:]
            cursor = 0
        elif key == "\x0b":
            line = line[:cursor]
        elif isinstance(key, str) and key.isprintable():
            line = line[:cursor] + key + line[cursor:]
            cursor += len(key)
        if previous != (line, cursor):
            completion = catalog.complete(line, cursor) if line[:cursor].strip() else Completion([])
            selected, first = None, 0


def edit_draft(screen, catalog, line, cursor):
    try:
        return edit(screen, catalog, line, cursor)
    finally:
        # Clear bytes queued in the editor before handing the tty back to the shell.
        curses.flushinp()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=f"command-complete {__version__}")
    parser.add_argument("--matches", action="store_true",
                        help="print candidates for the draft's last word and exit")
    parser.add_argument("--cursor", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--result-fd", type=int, help=argparse.SUPPRESS)
    parser.add_argument("draft", nargs="*", help="initial draft, preferably as one quoted argument")
    args = parser.parse_args()
    line = " ".join(args.draft)
    cursor = len(line) if args.cursor is None else args.cursor
    if not 0 <= cursor <= len(line):
        parser.error("cursor is outside the draft")
    if not args.matches and not (sys.stdin.isatty() and sys.stdout.isatty()):
        parser.error("the editor needs a terminal; use --matches to list candidates")
    if not all(char.isprintable() for char in line):
        parser.error("the draft must be a single line of printable text")

    try:
        selected_catalog = catalog_path()
        with gzip.open(selected_catalog, "rt", encoding="utf-8") as snapshot:
            catalog = Catalog(json.load(snapshot))
        if args.matches:
            for match in catalog.matches(line):
                print(match.text)
            return 0
        result = curses.wrapper(edit_draft, catalog, line, cursor)
        if result is None:
            return 130
        if args.result_fd is not None:
            with os.fdopen(args.result_fd, "w", encoding=sys.stdout.encoding) as output:
                print(result, file=output)
        else:
            print(result)
    except KeyboardInterrupt:
        return 130
    except (OSError, curses.error, ValueError) as error:
        parser.exit(1, f"command-complete: {error}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
