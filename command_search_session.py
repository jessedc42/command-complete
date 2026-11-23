"""Search/draft state transitions and inert, guided option insertion."""

from copy import copy
from dataclasses import dataclass
import shlex

from command_complete import following_options, read_options, split_at_cursor


@dataclass
class PendingValue:
    flag: str
    labels: tuple[str, ...]
    number: int
    start: int
    prefix: str


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
        if group and not any(flag in line.split() for flag in ('--help', '--version')):
            self.stage, self.command = 'choose', None
            return
        if command != self.command:
            self.command = command
            self.reference = self._reference_for(command)
            if line.strip() == command and command in self.drafts:
                self.draft, self.cursor, self.pending, self.queue = self.drafts[command]
                self.pending, self.queue = copy(self.pending), list(self.queue)
        self.stage = 'draft'
        self.message = ''

    def choose(self, entry):
        self.pending, self.queue = None, []
        self.set_draft(entry.command + ' ')
        if self.stage != 'draft':
            self.message = 'Choose a runnable subcommand for this command group.'
            return False
        if entry.positionals and not self.draft[len(entry.command):].strip():
            self.draft += ' '.join(shlex.quote(value) for value in entry.positionals) + ' '
            self.cursor = len(self.draft)
        return self.insert_entry(entry) if entry.options else True

    def _scope(self):
        canonical = self.index.resolve(self.command)
        raw = self.catalog.commands[canonical]
        flags = self.catalog.flags(canonical.split()[0], canonical)
        return raw, flags

    def _existing(self):
        """Return active option names and a flag whose required value is missing."""
        raw, flags = self._scope()
        active = set(following_options(self.draft, flags, raw.get('short_options')))
        try:
            words = shlex.split(self.draft)
        except ValueError:
            return active, 'the unfinished quoted argument'
        pending = None
        remaining = 0
        for word in words:
            if pending:
                if remaining:
                    remaining -= 1
                    if not remaining:
                        pending = None
                    continue
            if word == '--':
                break
            if word.startswith('-') and word != '-':
                names, attached = read_options(word, flags, raw.get('short_options'))
                flag = names[-1]
                if flags.get(flag) in ('value', 'many', 'attached') and not attached:
                    labels = raw.get('flag_arguments', {}).get(flag, ['Value'])
                    remaining = max(1, sum(not label.endswith(' (optional)') for label in labels))
                    pending = flag
        return active, pending

    def unavailable_reason(self, entry):
        if entry.command != self.command:
            return 'Select this command from the full frozen results.'
        raw, _ = self._scope()
        active, pending = self._existing()
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
            if self.draft and not self.draft.endswith(' '):
                self.draft += ' '
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
            values = shlex.split(self.draft[self.pending.start:].strip())
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
        self.draft = self.draft.rstrip() + ' '
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
