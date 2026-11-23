"""Search/draft state transitions and inert, guided option insertion."""

from copy import copy
from dataclasses import dataclass
import shlex

from command_complete import SHELL_WORD, following_options, read_options, split_at_cursor
from command_search_index import entry_text
from search_metadata import information_option


@dataclass
class PendingValue:
    flag: str
    labels: tuple[str, ...]
    number: int
    start: int
    prefix: str


@dataclass
class DraftState:
    active: set[str]
    pending: str | None
    positionals: list[str]
    options_enabled: bool


def primary_command(line):
    """Keep shell suffixes inert, and locate the first command's supported text."""
    end = 0
    for token in SHELL_WORD.finditer(line):
        if line[end:token.start()].strip() or token.group().startswith('#'):
            return line[:end] + ' ', True
        end = token.end()
    if line[end:].strip():
        return line[:end] + ' ', True
    return line, False


class SearchSession:
    def __init__(self, index, catalog, query=''):
        self.index, self.catalog = index, catalog
        self.query = query
        self.live = index.search(query)
        self.stage = 'search'
        self.frozen = ()
        self.reference = ()
        self.command = None
        self.draft = ''
        self.cursor = 0
        self.pending = None
        self.queue = []
        self.drafts = {}
        self.message = ''
        self.paths = {}

    @property
    def pending_hint(self):
        return self.pending.labels[self.pending.number] if self.pending else None

    @property
    def next_steps(self):
        labels = self.pending.labels[self.pending.number + 1:] if self.pending else ()
        return ' '.join([*(f'<{label}>' for label in labels), entry_text('', self.queue).strip()]).strip()

    def set_query(self, query):
        self.query = query
        self.live = self.index.search(query)
        self.message = self.live.error or ''

    def freeze(self, entry=None):
        if self.live.error or not self.live.results:
            self.message = self.live.error or 'No matching commands. Edit the search query.'
            return False
        self.frozen = self.live.results
        paths = (self.frozen.command_paths() if hasattr(self.frozen, 'command_paths') else
                 {r.entry.command for r in self.frozen})
        self.paths = {}
        for path in paths:
            self.paths.setdefault(self.index.resolve(path), []).append(path)
        self.stage = 'choose'
        self.command = None
        self.reference = ()
        self.draft, self.cursor = '', 0
        self.pending, self.queue = None, []
        self.message = 'Type a complete command path followed by Space, or select a result.'
        if entry is not None:
            self.choose(entry)
        return True

    def _command_for(self, line):
        line, _ = primary_command(line)
        split = split_at_cursor(line, len(line))
        if split is None:
            return None
        words, _, _ = split
        if not words:
            return None
        canonical = self.catalog.candidates(words, '', '')[2]
        matches = []
        for path in self.paths.get(canonical, ()):
            remaining = iter(words)
            if all(any(word == part for word in remaining) for part in path.split()):
                matches.append(path)
        return max(matches, key=lambda path: len(path.split())) if matches else None

    def _reference_for(self, command):
        if hasattr(self.frozen, 'for_command'):
            return self.frozen.for_command(command)
        return tuple(r.entry for r in self.frozen if r.entry.command == command)

    def _save(self):
        if self.command:
            self.drafts[self.command] = (self.draft, self.cursor, copy(self.pending), list(self.queue))

    def set_draft(self, line, cursor=None):
        if self.pending and not line.startswith(self.pending.prefix):
            self.pending, self.queue = None, []
        self.draft = line
        self.cursor = len(line) if cursor is None else cursor
        command = self._command_for(line)
        if command is None:
            self.command = None
            self.reference = ()
            self.stage = 'choose'
            return
        raw = self.catalog.commands[self.index.resolve(command)]
        base = next((e for e in self.index.entries_for_command(command) if e.id == command), None)
        group = raw.get('command_group') or (base and base.group)
        canonical = self.index.resolve(command)
        active = set(following_options(line, self.catalog.flags(canonical.split()[0], canonical), raw.get('short_options')))
        if group and not any(information_option(flag, self.catalog.flags(canonical.split()[0], canonical).get(flag),
                                               raw.get('flag_descriptions', {}).get(flag, ''), canonical.split()[0])
                             for flag in active):
            self.stage, self.command = 'choose', None
            return
        if command != self.command:
            self.command = command
            self.reference = self._reference_for(command)
            if command in self.drafts and (line.strip() == command or line == self.drafts[command][0]):
                self.draft, self.cursor, self.pending, self.queue = self.drafts[command]
                self.pending, self.queue = copy(self.pending), list(self.queue)
            elif command in self.drafts:
                saved_pending = self.drafts[command][2]
                if saved_pending and line.startswith(saved_pending.prefix):
                    self.pending = copy(saved_pending)
                    self.queue = list(self.drafts[command][3])
        self.stage = 'draft'
        self.message = ''

    def choose(self, entry):
        self.pending, self.queue = None, []
        helper = next((option.flag for option in entry.options
                       if option.flag in ('--help', '--version', '-help', '-h')
                       and not option.arguments and not option.values), None)
        self.set_draft(entry.command + (' ' + helper if helper else '') + ' ')
        if self.stage != 'draft':
            self.message = 'Choose a runnable subcommand for this command group.'
            return False
        return self.insert_entry(entry) if entry.options or entry.positionals else True

    def _scope(self):
        canonical = self.index.resolve(self.command)
        raw = self.catalog.commands[canonical]
        root = canonical.split()[0]
        flags = self.catalog.flags(root, canonical)
        if root in ('aws', 'docker', 'kubectl'):
            repeated = set(raw.get('repeatable_flags', ())) | set(self.catalog.commands[root].get('repeatable_flags', ()))
            if repeated:
                raw = dict(raw, repeatable_flags=repeated)
        return raw, flags

    def _draft_state(self):
        """Scan the primary command without confusing option values with operands."""
        raw, flags = self._scope()
        primary, _ = primary_command(self.draft)
        active = set(following_options(primary, flags, raw.get('short_options')))
        try:
            words = shlex.split(primary)
        except ValueError:
            return DraftState(active, 'the unfinished quoted argument', [], True)
        command_parts = self.command.split()
        positionals = []
        options_enabled = True
        pending = None
        remaining = 0
        consumed = 0
        for word in words:
            if pending:
                kind = flags[pending]
                if ((kind == 'many' and consumed or kind == 'optional') and word.startswith('-')):
                    pending = None
                else:
                    consumed += 1
                    remaining -= 1
                    if remaining <= 0 and kind != 'many':
                        pending = None
                    continue
            if options_enabled and word == '--':
                options_enabled = False
                continue
            if options_enabled and word.startswith('-') and word != '-':
                names, attached = read_options(word, flags, raw.get('short_options'))
                flag = names[-1]
                if flags.get(flag) in ('value', 'many', 'attached', 'optional') and not attached:
                    labels = raw.get('flag_arguments', {}).get(flag, ['Value'])
                    remaining = max(1, sum(not label.endswith(' (optional)') for label in labels))
                    pending = flag
                    consumed = 0
                continue
            if command_parts and word == command_parts[0]:
                command_parts.pop(0)
            else:
                positionals.append(word)
        if pending and (flags[pending] == 'many' and consumed or flags[pending] == 'optional'):
            pending = None
        return DraftState(active, pending, positionals, options_enabled)

    def _existing(self):
        state = self._draft_state()
        return state.active, state.pending

    def _separate(self):
        split = split_at_cursor(self.draft, len(self.draft))
        if self.draft and (split is None or split[1] != len(self.draft)):
            self.draft += ' '

    def unavailable_reason(self, entry):
        if entry.command != self.command:
            return 'Select this command from the full frozen results.'
        if primary_command(self.draft)[1]:
            return 'Edit shell operators manually; reference options apply to a single command.'
        raw, _ = self._scope()
        state = self._draft_state()
        active, pending = state.active, state.pending
        if not state.options_enabled and entry.options:
            return 'Options cannot be appended after --. Edit the draft to place them before --.'
        if (entry.positionals and state.positionals and
                tuple(state.positionals[:len(entry.positionals)]) != entry.positionals):
            return 'Requires positional arguments: ' + ' '.join(entry.positionals) + '; edit the existing arguments first.'
        proposed = {o.flag for o in entry.options}
        for left, right in raw.get('flag_conflicts', ()):
            if proposed.intersection(left) and (active | proposed).intersection(right):
                return 'conflicts with ' + ', '.join(sorted((active | proposed).intersection(right)))
            if proposed.intersection(right) and (active | proposed).intersection(left):
                return 'conflicts with ' + ', '.join(sorted((active | proposed).intersection(left)))
        if self.pending or pending:
            return 'Finish the value for ' + (self.pending.flag if self.pending else pending)
        return ''

    def insert_entry(self, entry):
        reason = self.unavailable_reason(entry)
        if reason:
            self.message = reason
            return False
        if entry.positionals and not self._draft_state().positionals:
            self._separate()
            self.draft += ' '.join(shlex.quote(value) for value in entry.positionals) + ' '
            self.cursor = len(self.draft)
        self.queue = list(entry.options)
        return self._advance()

    def _advance(self):
        raw, flags = self._scope()
        while self.queue:
            option = self.queue.pop(0)
            active, pending = self._existing()
            if pending:
                self.message = 'Finish the value for ' + pending
                self.queue = []
                return False
            if option.flag in active and option.flag not in raw.get('repeatable_flags', ()):
                self.message = option.flag + ' is already present; its value is preserved.'
                continue
            if option.flag not in flags:
                self.message = option.flag + ' is unavailable for this platform or command.'
                self.queue = []
                return False
            self._separate()
            self.draft += option.flag + ' '
            if option.values:
                self.draft += ' '.join(shlex.quote(value) for value in option.values) + ' '
            else:
                labels = tuple(label for label in option.arguments if not label.endswith(' (optional)'))
                if labels:
                    self.pending = PendingValue(option.flag, labels, 0, len(self.draft), self.draft)
                    self.message = 'Enter ' + labels[0] + '; Enter confirms this value.'
                    self.cursor = len(self.draft)
                    return True
            self.cursor = len(self.draft)
        return True

    def confirm_value(self):
        if self.pending is None:
            return False
        try:
            values = shlex.split(self.draft[self.pending.start:])
        except ValueError:
            self.message = 'Close the quoted value before confirming.'
            return False
        if not values:
            self.message = 'Enter a value for ' + self.pending_hint
            return False
        _, flags = self._scope()
        if len(values) > 1 and flags.get(self.pending.flag) != 'many':
            self.message = 'Quote a value containing spaces before confirming.'
            return False
        self._separate()
        self.cursor = len(self.draft)
        self.pending.number += 1
        if self.pending.number < len(self.pending.labels):
            self.pending.start = len(self.draft)
            self.pending.prefix = self.draft
            self.message = 'Enter ' + self.pending_hint + '; Enter confirms this value.'
            return True
        self.pending = None
        self.message = 'Value accepted. Continue drafting or Enter to return the draft.'
        self._advance()
        return True

    def back(self):
        if self.stage == 'draft':
            self._save()
            self.stage, self.command, self.reference = 'choose', None, ()
            self.pending, self.queue = None, []
            self.message = 'Frozen results restored. Select a command or edit the draft.'
        elif self.stage == 'choose':
            self.stage = 'search'
            self.message = 'Search restored. Your command drafts are retained.'
