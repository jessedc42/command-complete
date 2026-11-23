"""Complete-catalog keyword search with inert, structured insertion records."""

from array import array
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
import json
import hashlib
from pathlib import Path
import sqlite3

from search_metadata import information_option, purpose_terms, tokens


@dataclass(frozen=True, slots=True)
class Option:
    flag: str
    arguments: tuple[str, ...] = ()
    values: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SearchEntry:
    id: str
    command: str
    text: str
    description: str
    effect: str
    terms: frozenset[str]
    options: tuple[Option, ...] = ()
    positionals: tuple[str, ...] = ()
    group: bool = False
    source: str = 'unavailable'


@dataclass(frozen=True, slots=True)
class SearchResult:
    entry: SearchEntry
    score: int


@dataclass(frozen=True, slots=True)
class SearchResults:
    results: Sequence[SearchResult] = ()
    error: str | None = None


def option_for(entry, flag, kind, root_entry=None):
    arguments = entry.get('flag_arguments', {}).get(flag)
    if arguments is None and root_entry:
        arguments = root_entry.get('flag_arguments', {}).get(flag)
    if arguments is None and kind in ('value', 'many', 'attached'):
        label = entry.get('flag_hints', {}).get(flag)
        if not label and root_entry:
            label = root_entry.get('flag_hints', {}).get(flag)
        arguments = [label or 'Value']
    return Option(flag, tuple(arguments or ()))


def entry_text(command, options=(), positionals=()):
    words = [command, *positionals]
    for option in options:
        words.append(option.flag)
        words.extend(option.values or tuple(f'<{label}>' for label in option.arguments))
    return ' '.join(words)


def resolve_command(catalog, command):
    seen = set()
    while alias := catalog.commands[command].get('alias'):
        if command in seen or alias not in catalog.commands:
            raise ValueError(f'Invalid command alias: {command}')
        seen.add(command)
        command = alias
    return command


def iter_entries(catalog, metadata):
    meta_commands = metadata.get('commands', {})
    contexts = {}
    for command in catalog.commands:
        canonical = resolve_command(catalog, command)
        raw = catalog.commands[canonical]
        root = canonical.split()[0]
        root_raw = catalog.commands.get(root, {})
        canonical_meta = meta_commands.get(canonical, {})
        meta = canonical_meta
        if canonical != command:
            alias_meta = meta_commands.get(command, {})
            meta = dict(canonical_meta, **alias_meta)
            meta['flags'] = canonical_meta.get('flags', {}) | alias_meta.get('flags', {})
        description = meta.get('description') or raw.get('description', '')
        effect = meta.get('effect', 'unknown')
        terms = frozenset(tokens(command).union(canonical_meta.get('terms', ()), meta.get('terms', purpose_terms(description))))
        contexts[command] = terms
        source = meta.get('source', raw.get('documentation_source', 'unavailable'))
        yield (SearchEntry(command, command, command, description or 'Description unavailable',
                                   effect, terms, group=bool(meta.get('command_group', raw.get('command_group'))), source=source))
        for flag, kind in catalog.flags(root, canonical).items():
            flag_meta = meta.get('flags', {}).get(flag)
            if flag_meta is None and root in ('aws', 'kubectl', 'docker'):
                flag_meta = meta_commands.get(root, {}).get('flags', {}).get(flag)
            flag_meta = flag_meta or {}
            prose = flag_meta.get('description') or raw.get('flag_descriptions', {}).get(flag)
            if not prose and root in ('aws', 'kubectl', 'docker'):
                prose = root_raw.get('flag_descriptions', {}).get(flag)
            option = option_for(raw, flag, kind, root_raw)
            text = entry_text(command, (option,))
            flag_terms = frozenset(terms.union(tokens(flag), flag_meta.get('terms', purpose_terms(prose or ''))))
            # A global formatting flag does not change an operation's effect.
            flag_effect = flag_meta.get('effect', effect) if flag in raw.get('flags', {}) else effect
            if information_option(flag, kind, prose or '', root):
                flag_effect = 'get'
            yield (SearchEntry(command + '\t' + flag, command, text,
                prose or 'Description unavailable', flag_effect, flag_terms, (option,), source=flag_meta.get('source', source)))
    for recipe in metadata.get('recipes', []):
        command = recipe['command']
        if command not in catalog.commands:
            continue
        options = tuple(Option(o['flag'], tuple(o.get('arguments', ())), tuple(o.get('values', ())))
                        for o in recipe.get('options', ()))
        positionals = tuple(recipe.get('positionals', ()))
        text = entry_text(command, options, positionals)
        yield (SearchEntry('recipe:' + recipe['id'], command, text, recipe['description'],
                                   recipe.get('effect', 'unknown'),
                                       frozenset(contexts[command].union(tokens(text), purpose_terms(recipe['description']), recipe.get('terms', ()))),
                                   options, positionals, source='curated'))


class SearchIndex:
    def __init__(self, catalog, metadata):
        self.catalog = catalog
        self.metadata = metadata
        self.by_command = defaultdict(list)
        self.entries = tuple(sorted(iter_entries(catalog, metadata), key=lambda e: (e.text.casefold(), e.id)))
        self.postings = defaultdict(lambda: array('I'))
        self.effects = defaultdict(lambda: array('I'))
        for number, entry in enumerate(self.entries):
            self.by_command[entry.command].append(entry)
            self.effects[entry.effect].append(number)
            for term in entry.terms:
                for token in tokens(term):
                    self.postings[token].append(number)
        self.terms = sorted(self.postings)

    def resolve(self, command):
        seen = set()
        while alias := self.catalog.commands[command].get('alias'):
            if command in seen or alias not in self.catalog.commands:
                raise ValueError(f'Invalid command alias: {command}')
            seen.add(command)
            command = alias
        return command

    def entries_for_command(self, command):
        return tuple(self.by_command.get(command, ()))

    def search(self, query):
        words = set(query.casefold().split())
        filters = words.intersection(('get', 'set'))
        if len(filters) > 1:
            return SearchResults(error='Choose either get or set, not both.')
        keywords = sorted(tokens(' '.join(words - filters)))
        allowed = set(self.effects[next(iter(filters))]) if filters else None
        if not keywords:
            return SearchResults(tuple(SearchResult(self.entries[i], 0) for i in sorted(allowed or ())))
        scores = defaultdict(int)
        for keyword in keywords:
            matching = set()
            start = bisect_left(self.terms, keyword)
            end = bisect_left(self.terms, keyword + '\U0010ffff')
            for term in self.terms[start:end]:
                matching.update(self.postings[term])
            if allowed is not None:
                matching.intersection_update(allowed)
            for number in matching:
                scores[number] += 1
        order = sorted(scores, key=lambda number: (-scores[number], number))
        return SearchResults(tuple(SearchResult(self.entries[i], scores[i]) for i in order))


def _payload(entry):
    return json.dumps({'id': entry.id, 'command': entry.command, 'text': entry.text,
                       'description': entry.description, 'effect': entry.effect,
                       'options': [{'flag': o.flag, 'arguments': o.arguments, 'values': o.values} for o in entry.options],
                       'positionals': entry.positionals, 'group': entry.group, 'source': entry.source},
                      ensure_ascii=False, separators=(',', ':'))


def _entry(payload):
    data = json.loads(payload)
    data['options'] = tuple(Option(o['flag'], tuple(o['arguments']), tuple(o['values'])) for o in data['options'])
    data['positionals'] = tuple(data['positionals'])
    return SearchEntry(**data, terms=frozenset())


def write_database(path, catalog, metadata):
    """Build once, streaming entries; share term groups across inherited options."""
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.building')
    temporary.unlink(missing_ok=True)
    connection = sqlite3.connect(temporary)
    try:
        connection.executescript('''
            PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;
            CREATE TABLE entries (id INTEGER PRIMARY KEY, command TEXT, sort_key TEXT,
                                  stable_id TEXT, effect TEXT, payload TEXT);
            CREATE TABLE terms (term TEXT, group_id INTEGER, PRIMARY KEY(term,group_id)) WITHOUT ROWID;
            CREATE TABLE members (group_id INTEGER, entry_id INTEGER, PRIMARY KEY(group_id,entry_id)) WITHOUT ROWID;
            CREATE TABLE info (key TEXT PRIMARY KEY,value TEXT);
        ''')
        groups = {}
        command_terms = {}
        count = 0
        for number, entry in enumerate(iter_entries(catalog, metadata)):
            count += 1
            connection.execute('INSERT INTO entries VALUES (?,?,?,?,?,?)',
                               (number, entry.command, entry.text.casefold(), entry.id, entry.effect, _payload(entry)))
            if not entry.options and not entry.positionals:
                command_terms[entry.command] = entry.terms
            base = command_terms.get(entry.command, frozenset())
            for term_set in (base, entry.terms - base):
                normalized = frozenset(t for term in term_set for t in tokens(term))
                if not normalized:
                    continue
                group_id = groups.get(normalized)
                if group_id is None:
                    group_id = len(groups)
                    groups[normalized] = group_id
                    connection.executemany('INSERT INTO terms VALUES (?,?)', ((term, group_id) for term in sorted(normalized)))
                connection.execute('INSERT OR IGNORE INTO members VALUES (?,?)', (group_id, number))
        connection.executescript('''
            CREATE INDEX entry_command ON entries(command,sort_key,stable_id);
            CREATE INDEX entry_effect ON entries(effect,sort_key,stable_id);
        ''')
        connection.execute('INSERT INTO info VALUES (?,?)', ('format', '1'))
        connection.execute('INSERT INTO info VALUES (?,?)', ('entry_count', str(count)))
        connection.commit()
    finally:
        connection.close()
    temporary.replace(path)
    return count


class _DatabaseResults(Sequence):
    """An immutable query snapshot with small, lazy pages rather than 600k objects."""
    def __init__(self, index, table, count):
        self.index, self.table, self.count = index, table, count
        self.owns_index = False
        self.page = ()
        self.page_start = -1

    def __len__(self):
        return self.count

    def _range(self, start, stop):
        rows = self.index.connection.execute(
            f'SELECT e.payload,r.score FROM {self.table} r JOIN entries e ON e.id=r.entry_id '
            'WHERE r.position>? AND r.position<=? ORDER BY r.position', (start, stop))
        return tuple(SearchResult(_entry(payload), score) for payload, score in rows)

    def __getitem__(self, key):
        if isinstance(key, slice):
            start, stop, step = key.indices(self.count)
            if step != 1:
                return tuple(self[i] for i in range(start, stop, step))
            return self._range(start, stop)
        if key < 0:
            key += self.count
        if not 0 <= key < self.count:
            raise IndexError(key)
        start = (key // 64) * 64
        if self.page_start != start:
            self.page = self._range(start, start + 64)
            self.page_start = start
        return self.page[key - start]

    def __iter__(self):
        for start in range(0, self.count, 256):
            yield from self._range(start, min(start + 256, self.count))

    def command_paths(self):
        return {row[0] for row in self.index.connection.execute(
            f'SELECT DISTINCT e.command FROM {self.table} r JOIN entries e ON e.id=r.entry_id')}

    def for_command(self, command):
        self.index.connection.execute(f'CREATE INDEX IF NOT EXISTS {self.table}_entry ON {self.table}(entry_id)')
        return tuple(_entry(payload) for payload, in self.index.connection.execute(
            f'SELECT e.payload FROM entries e JOIN {self.table} r ON r.entry_id=e.id '
            'WHERE e.command=? ORDER BY r.position', (command,)))

    def __del__(self):
        try:
            if self.owns_index:
                self.index.close()
            else:
                self.index.connection.execute(f'DROP TABLE IF EXISTS {self.table}')
        except (sqlite3.Error, AttributeError):
            pass


class DatabaseSearchIndex:
    def __init__(self, path, catalog, catalog_file=None, *, handoff=False):
        self.catalog = catalog
        self.path = Path(path).resolve()
        self.connection = sqlite3.connect(self.path.as_uri() + '?mode=ro&immutable=1', uri=True,
                                          check_same_thread=not handoff)
        self.connection.execute('PRAGMA temp_store=MEMORY')
        try:
            if self.connection.execute("SELECT value FROM info WHERE key='format'").fetchone() != ('1',):
                raise ValueError('Unsupported search database format; rebuild the search catalog.')
            expected = self.connection.execute("SELECT value FROM info WHERE key='catalog_sha256'").fetchone()
            if expected and catalog_file is not None:
                actual = hashlib.sha256(Path(catalog_file).read_bytes()).hexdigest()
                if actual != expected[0]:
                    raise ValueError('Completion catalog changed; rebuild the search catalog before searching.')
        except (ValueError, OSError, sqlite3.Error):
            self.close()
            raise
        self.serial = 0

    def close(self):
        self.connection.close()

    def search_background(self, query, cancelled):
        """Transfer a finished lazy snapshot, never a concurrently used reader."""
        if cancelled():
            raise InterruptedError('search superseded')
        reader = DatabaseSearchIndex(self.path, self.catalog, handoff=True)
        try:
            reader.connection.set_progress_handler(lambda: int(cancelled()), 1000)
            result = reader.search(query)
            reader.connection.set_progress_handler(None, 0)
            if isinstance(result.results, _DatabaseResults):
                result.results.owns_index = True
            else:
                reader.close()
            return result
        except BaseException:
            reader.close()
            raise

    def resolve(self, command):
        return resolve_command(self.catalog, command)

    def entries_for_command(self, command):
        return tuple(_entry(payload) for payload, in self.connection.execute(
            'SELECT payload FROM entries WHERE command=? ORDER BY sort_key,stable_id', (command,)))

    def search(self, query):
        words = set(query.casefold().split())
        filters = words.intersection(('get', 'set'))
        if len(filters) > 1:
            return SearchResults(error='Choose either get or set, not both.')
        keywords = sorted(tokens(' '.join(words - filters)))
        if not keywords and not filters:
            return SearchResults()
        self.serial += 1
        table = f'results_{self.serial}'
        self.connection.execute(f'CREATE TEMP TABLE {table} (position INTEGER PRIMARY KEY,entry_id INTEGER,score INTEGER)')
        parameters = []
        if keywords:
            # Materialize keyword hits in bounded batches: SQLite limits the
            # number of SELECT arms, independently of its parameter limit.
            hits = f'hits_{self.serial}'
            self.connection.execute(f'CREATE TEMP TABLE {hits} (entry_id INTEGER, keyword INTEGER)')
            pieces = []
            for number, word in enumerate(keywords):
                pieces.append('SELECT DISTINCT m.entry_id,? AS keyword FROM terms t '
                              'JOIN members m ON m.group_id=t.group_id WHERE t.term>=? AND t.term<?')
                parameters.extend((number, word, word + '\U0010ffff'))
                if len(pieces) == 64 or number == len(keywords) - 1:
                    self.connection.execute(f'INSERT INTO {hits} ' + ' UNION ALL '.join(pieces), parameters)
                    pieces, parameters = [], []
            sql = (f'SELECT e.id,count(*) AS score FROM {hits} hits JOIN entries e ON e.id=hits.entry_id')
            if filters:
                sql += ' WHERE e.effect=?'
                parameters.append(next(iter(filters)))
            sql += ' GROUP BY e.id ORDER BY score DESC,e.sort_key,e.stable_id'
        else:
            sql = 'SELECT id,0 FROM entries WHERE effect=? ORDER BY sort_key,stable_id'
            parameters.append(next(iter(filters)))
        cursor = self.connection.execute(f'INSERT INTO {table}(entry_id,score) ' + sql, parameters)
        if keywords:
            self.connection.execute(f'DROP TABLE {hits}')
        return SearchResults(_DatabaseResults(self, table, cursor.rowcount))
