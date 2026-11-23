#!/usr/bin/env python3
"""Discover UNIX commands by purpose, then return an unexecuted command draft."""

import argparse
from collections import deque
import curses
import gzip
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import sqlite3
import sys
import tempfile

from command_complete import (Catalog, Completion, __version__, apply_match, catalog_path,
                              cell_width, draw as draw_completion, visible)
from command_search_index import DatabaseSearchIndex
from command_search_session import SearchSession
from search_scheduler import HybridSearch
from terminal_keys import character_cursor, configure_unicode_terminal, edit_text


ROOT = Path(__file__).resolve().parent


def cached_database(path):
    if path.suffix != '.gz':
        return path
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    cache = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'command-complete'
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / (digest.hexdigest() + '.db')
    if not target.exists():
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=cache, delete=False) as output:
                temporary = Path(output.name)
                with gzip.open(path, 'rb') as source:
                    shutil.copyfileobj(source, output)
            temporary.replace(target)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
    return target


class Canvas:
    def __init__(self, screen):
        self.screen = screen
        self.height, self.width = screen.getmaxyx()

    def write(self, row, text, style=0, column=0, limit=None):
        if not 0 <= row < self.height:
            return
        maximum = max(0, self.width - column - 1)
        if limit is not None:
            maximum = min(maximum, limit)
        text = visible(text)
        result, used = [], 0
        for char in text:
            used += cell_width(char)
            if used > maximum:
                break
            result.append(char)
        if not result:
            return
        try:
            self.screen.addstr(row, column, ''.join(result), style)
        except curses.error:
            pass

    def input(self, row, label, line, cursor):
        before = visible(line[:cursor])
        available = max(0, self.width - len(label) - 2)
        while sum(map(cell_width, before)) > available and before:
            before = before[1:]
        self.write(row, label + before + visible(line[cursor:]))
        return row, min(max(0, self.width - 1), len(label) + sum(map(cell_width, before)))


def _window_start(selected, first, count, capacity, columns=1):
    if selected is not None:
        if selected < first:
            first = (selected // columns) * columns
        elif selected >= first + capacity:
            first = max(0, ((selected // columns) - capacity // columns + 1) * columns)
    return max(0, min(first, max(0, count - capacity + columns - 1) // columns * columns))


def _move(selected, step, count):
    if not count:
        return None
    if selected is None:
        return 0 if step > 0 else count - 1
    return max(0, min(count - 1, selected + step))


def _colors():
    style = curses.A_BOLD
    if curses.has_colors() and 'NO_COLOR' not in os.environ:
        try:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_CYAN, -1)
            style |= curses.color_pair(1)
        except curses.error:
            pass
    return style


def terminal_disconnected():
    poller = select.poll()
    poller.register(sys.stdin.fileno(), select.POLLHUP | select.POLLERR | select.POLLNVAL)
    return bool(poller.poll(0))


def coalesce_query_input(screen, line, cursor, key, buffered):
    """Apply queued printable edits in order; leave controls for the event loop."""
    line, cursor = edit_text(line, cursor, key)
    immediate = key == ' '
    screen.nodelay(True)
    try:
        while True:
            if buffered:
                queued = buffered[0]
                if not isinstance(queued, str) or not queued.isprintable():
                    break
                buffered.popleft()
            else:
                try:
                    queued = screen.get_wch()
                except curses.error:
                    break
                if not isinstance(queued, str) or not queued.isprintable():
                    if isinstance(queued, int):
                        curses.ungetch(queued)
                    else:
                        curses.unget_wch(queued)
                    break
            line, cursor = edit_text(line, cursor, queued)
            immediate = queued == ' '
    finally:
        screen.nodelay(False)
    return line, cursor, immediate


def _edit(screen, session, query_cursor):
    # Read Ctrl+C as a key: terminal SIGINT handling can flush/cancel an
    # in-progress curses update before Python receives the cancellation.
    curses.raw()
    curses.set_escdelay(50)
    color = _colors()
    focus = 'draft'
    selected = reference_selected = completion_selected = None
    first = reference_first = completion_first = 0
    hidden = False
    previous_stage = None
    previous_command = None
    actions, buffered = deque(), deque()
    awaiting_choice, dirty = False, True
    previous_status = None
    while True:
        if session.stage == 'search' and session.poll_search():
            selected, first = None, 0
            dirty = True
        search_status = session.scheduler.status if session.scheduler and session.stage == 'search' else ''
        if search_status != previous_status:
            dirty, previous_status = True, search_status
        stage = session.stage
        if session.command != previous_command:
            reference_selected, reference_first = None, 0
            completion_selected, completion_first = None, 0
            previous_command = session.command
        if stage != previous_stage:
            screen.clearok(True)
            previous_stage = stage
        if dirty:
            screen.erase()
            canvas = Canvas(screen)
            height, width = canvas.height, canvas.width
            full_rows = max(1, height - 4)
            top = max(3, (height - 1) // 2)
            columns = 2 if width >= 90 else 1
            reference_capacity = max(1, top - 2) * columns
            completion = Completion([])
            completion_rows = max(1, height - top - 5)
            cursor_position = None
            if stage != 'draft':
                results = session.live.results if stage == 'search' else session.frozen
                first = _window_start(selected, first, len(results), full_rows)
                if stage == 'search':
                    cursor_position = canvas.input(0, 'Search> ', session.query, query_cursor)
                    heading = 'LIVE SEARCH'
                else:
                    cursor_position = canvas.input(0, 'Draft> ', session.draft, session.cursor)
                    heading = 'FROZEN RESULTS'
                canvas.write(1, f'{heading} - {len(results)} matches', curses.A_BOLD)
                text_column = min(max(10, width // 2), 60)
                for offset, result in enumerate(results[first:first + full_rows]):
                    number = first + offset
                    style = curses.A_REVERSE if number == selected else 0
                    canvas.write(2 + offset, (' > ' if number == selected else '   ') + result.entry.text,
                                 style | color, limit=text_column - 2)
                    canvas.write(2 + offset, result.entry.description, style, column=text_column)
                if not results:
                    canvas.write(3, search_status or session.live.error or session.guard_hint or
                                 'Type task keywords, for example: get network reachable')
                detail = session.live.error or session.guard_hint or search_status or session.message
                if selected is not None and selected < len(results):
                    entry = results[selected].entry
                    detail = f'[{entry.effect}] {entry.text}'
                canvas.write(height - 2, detail)
                canvas.write(height - 1, 'Arrows select | PgUp/PgDn jump | Enter choose/freeze | Ctrl+R back | Ctrl+C cancel')
                if cursor_position and width and height:
                    try:
                        screen.move(*cursor_position)
                    except curses.error:
                        pass
                screen.refresh()
            elif height < 9 or width < 32:
                canvas.write(0, 'Enlarge terminal for both panes.')
                canvas.input(1, '> ', session.draft, session.cursor)
                canvas.write(height - 1, 'Ctrl+R back | Ctrl+C cancel')
                screen.refresh()
            else:
                reference = session.reference
                reference_first = _window_start(reference_selected, reference_first, len(reference), reference_capacity, columns)
                canvas.write(0, f'FROZEN REFERENCE - {session.command}' + (' [active]' if focus == 'reference' else ''), curses.A_BOLD)
                cell = width // columns
                for offset, entry in enumerate(reference[reference_first:reference_first + reference_capacity]):
                    number = reference_first + offset
                    row, column = 1 + offset // columns, (offset % columns) * cell
                    style = curses.A_REVERSE if focus == 'reference' and number == reference_selected else 0
                    reason = session.unavailable_reason(entry)
                    if reason:
                        style |= curses.A_DIM
                    text = entry.text[len(entry.command):].strip() or '(command)'
                    name_width = min(max(12, cell // 2), 31)
                    canvas.write(row, ('> ' if number == reference_selected and focus == 'reference' else '  ') + text,
                                 style | color, column, name_width - 1)
                    canvas.write(row, reason or entry.description, style, column + name_width, cell - name_width - 2)
                status = session.message
                if session.next_steps:
                    status += (' | ' if status else '') + 'Next: ' + session.next_steps
                canvas.write(top - 1, status, curses.A_DIM)
                canvas.write(top, '─' * max(0, width - 1), curses.A_DIM)
                if not hidden:
                    completion = session.catalog.complete(session.draft, session.cursor)
                if session.pending_hint:
                    completion = Completion(completion.matches, session.pending_hint, completion.examples)
                example_rows = min(len(completion.examples) + 1, max(0, height - top - 5)) if completion.examples else 0
                completion_rows = max(1, height - top - 5 - example_rows)
                completion_first = _window_start(completion_selected, completion_first, len(completion.matches), completion_rows)
                canvas.write(top + 1, 'CC - LIVE COMPLETION' + (' [active]' if focus == 'draft' else ''), curses.A_BOLD)
                screen.noutrefresh()
                bottom = screen.derwin(height - top - 2, width, top + 2, 0)
                help_text = 'F6 pane | Ctrl+R back | Enter insert/return | Ctrl+C cancel'
                if session.pending_hint:
                    help_text = 'Enter confirms value | F6 pane | Ctrl+R back | Ctrl+C cancel'
                draw_completion(bottom, session.draft, session.cursor, completion,
                                completion_selected, completion_first, help_text, color)

        if actions and not session.search_pending:
            key = actions.popleft()
        elif buffered and not awaiting_choice:
            key = buffered.popleft()
        else:
            screen.timeout(25 if session.search_pending else -1)
            try:
                key = screen.get_wch()
            except curses.error:
                if not session.search_pending or terminal_disconnected():
                    return None
                dirty = False
                continue
        dirty = True
        if key in ('\x03', '\x04'):
            return None
        if key == curses.KEY_RESIZE:
            screen.clearok(True)
            continue
        if stage == 'search' and session.search_pending and awaiting_choice:
            # Once Enter submits a choice, later edit/back keys belong to that
            # choice's draft. Only cancellation and resize bypass this order.
            buffered.append(key)
            continue
        if key == '\x12':
            actions.clear()
            awaiting_choice = False
            session.back()
            focus, reference_selected, completion_selected = 'draft', None, None
            hidden = False
            continue
        if key == curses.KEY_F6 and stage == 'draft':
            focus = 'reference' if focus == 'draft' else 'draft'
            continue
        if key == '\x1b':
            actions.clear()
            awaiting_choice = False
            hidden, completion_selected = True, None
            if stage != 'draft':
                selected = None
            continue
        enter = key in ('\r', '\n', curses.KEY_ENTER)
        if stage == 'search' and (session.search_pending or session.guard_waiting):
            if enter or key in (curses.KEY_UP, curses.KEY_DOWN, curses.KEY_PPAGE, curses.KEY_NPAGE, '\t', curses.KEY_BTAB):
                session.expedite_search()
                if session.search_pending:
                    actions.append(key)
                    awaiting_choice = enter
                    continue
        if stage != 'draft':
            if results and key in (curses.KEY_UP, curses.KEY_DOWN, curses.KEY_PPAGE, curses.KEY_NPAGE, '\t', curses.KEY_BTAB):
                step = -1 if key in (curses.KEY_UP, curses.KEY_BTAB) else 1
                if key in (curses.KEY_PPAGE, curses.KEY_NPAGE):
                    step = -full_rows if key == curses.KEY_PPAGE else full_rows
                selected = _move(selected, step, len(results))
                continue
            if enter:
                awaiting_choice = False
                entry = results[selected].entry if selected is not None and selected < len(results) else None
                if stage == 'search':
                    session.freeze(entry)
                elif entry:
                    session.choose(entry)
                else:
                    session.set_draft(session.draft)
                focus, completion_selected = 'draft', None
                hidden = False
                continue
            if stage == 'search':
                line, cursor, immediate = coalesce_query_input(screen, session.query, query_cursor, key, buffered)
                if line != session.query:
                    actions.clear()
                    session.set_query(line, immediate=immediate)
                    selected, first = None, 0
                query_cursor = cursor
            else:
                line, cursor = edit_text(session.draft, session.cursor, key)
                session.set_draft(line, cursor)
                completion_selected = None
                hidden = False
            continue

        if focus == 'reference':
            if key in (curses.KEY_UP, curses.KEY_DOWN, curses.KEY_LEFT, curses.KEY_RIGHT,
                       curses.KEY_PPAGE, curses.KEY_NPAGE, '\t', curses.KEY_BTAB):
                step = {curses.KEY_UP: -columns, curses.KEY_DOWN: columns,
                        curses.KEY_LEFT: -1, curses.KEY_RIGHT: 1,
                        curses.KEY_PPAGE: -reference_capacity, curses.KEY_NPAGE: reference_capacity,
                        '\t': 1, curses.KEY_BTAB: -1}[key]
                reference_selected = _move(reference_selected, step, len(session.reference))
                continue
            if enter:
                if reference_selected is not None and reference_selected < len(session.reference):
                    session.insert_entry(session.reference[reference_selected])
                focus, completion_selected = 'draft', None
                hidden = False
                continue
            focus = 'draft'
        matches = completion.matches
        if key == '\t' and not matches:
            completion = session.catalog.complete(session.draft, session.cursor)
            matches, hidden = completion.matches, False
        if matches and key in (curses.KEY_UP, curses.KEY_DOWN, curses.KEY_PPAGE, curses.KEY_NPAGE, '\t', curses.KEY_BTAB):
            if key == '\t' and len(matches) == 1:
                line, cursor = apply_match(session.draft, matches[0])
                session.set_draft(line, cursor)
                completion_selected, hidden = None, False
                continue
            step = -1 if key in (curses.KEY_UP, curses.KEY_BTAB) else 1
            if key in (curses.KEY_PPAGE, curses.KEY_NPAGE):
                step = -completion_rows if key == curses.KEY_PPAGE else completion_rows
            completion_selected = _move(completion_selected, step, len(matches))
            continue
        if enter:
            if completion_selected is not None and completion_selected < len(matches):
                line, cursor = apply_match(session.draft, matches[completion_selected])
                session.set_draft(line, cursor)
                completion_selected = None
            elif session.pending_hint:
                session.confirm_value()
            else:
                return session.draft
            continue
        line, cursor = edit_text(session.draft, session.cursor, key)
        if (line, cursor) != (session.draft, session.cursor):
            session.set_draft(line, cursor)
            completion_selected, hidden, completion_first = None, False, 0


def edit(screen, session, query_cursor):
    try:
        return _edit(screen, session, query_cursor)
    finally:
        curses.flushinp()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version=f'command-search {__version__}')
    parser.add_argument('--matches', action='store_true', help='print ranked matches and exit')
    parser.add_argument('--catalog', type=Path, help='completion catalog for this platform')
    parser.add_argument('--database', type=Path, help='prebuilt search database (.db or .db.gz)')
    parser.add_argument('--short-query-guard', action=argparse.BooleanOptionalAction, default=None,
                        help='hold unfinished keywords under 3 characters during automatic search '
                             '(default: off; COMMAND_SEARCH_SHORT_QUERY_GUARD)')
    parser.add_argument('--result-fd', type=int, help=argparse.SUPPRESS)
    cursor_group = parser.add_mutually_exclusive_group()
    cursor_group.add_argument('--cursor', type=int, help=argparse.SUPPRESS)
    cursor_group.add_argument('--cursor-bytes', type=int, help=argparse.SUPPRESS)
    parser.add_argument('query', nargs='*', help='initial task keywords')
    args = parser.parse_args()
    if args.short_query_guard is None:
        configured = os.environ.get('COMMAND_SEARCH_SHORT_QUERY_GUARD', '0').strip().casefold()
        if configured not in ('0', 'false', 'no', 'off', '1', 'true', 'yes', 'on'):
            parser.error('COMMAND_SEARCH_SHORT_QUERY_GUARD must be a boolean: 1/0, true/false, yes/no, on/off')
        args.short_query_guard = configured in ('1', 'true', 'yes', 'on')
    query = ' '.join(args.query)
    cursor = len(query) if args.cursor is None else args.cursor
    if args.cursor_bytes is not None:
        try:
            cursor = character_cursor(query, args.cursor_bytes)
        except ValueError as error:
            parser.error(str(error))
    if not all(c.isprintable() for c in query) or not 0 <= cursor <= len(query):
        parser.error('the query must be one printable line with a valid cursor position')
    if not args.matches and not (sys.stdin.isatty() and sys.stdout.isatty()):
        parser.error('interactive search needs a terminal; use --matches to list results')
    index = None
    try:
        catalog_file = args.catalog or catalog_path()
        with gzip.open(catalog_file, 'rt', encoding='utf-8') as source:
            catalog = Catalog(json.load(source))
        database = args.database or ROOT / ('search-ubuntu.db.gz' if catalog_file.name == 'catalog-ubuntu.json.gz' else 'search-macos.db.gz')
        if not database.exists():
            raise ValueError('Search database missing. Run python3 build_search_catalog.py first.')
        index = DatabaseSearchIndex(cached_database(database), catalog, catalog_file)
        if args.matches:
            results = index.search(query)
            if results.error:
                parser.error(results.error)
            for result in results.results:
                print(f'{result.score}\t{result.entry.effect}\t{visible(result.entry.text)}\t{visible(result.entry.description)}')
            sys.stdout.flush()
            return 0
        configure_unicode_terminal()
        with HybridSearch(index.search_background) as scheduler:
            result = curses.wrapper(edit, SearchSession(index, catalog, query, scheduler=scheduler,
                                                       short_query_guard=args.short_query_guard), cursor)
        if result is None:
            return 130
        if args.result_fd is not None:
            with os.fdopen(args.result_fd, 'w', encoding=sys.stdout.encoding or 'utf-8') as output:
                print(result, file=output)
        else:
            print(result)
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        # A normal UNIX consumer (for example head) may stop reading early.
        # Redirect the descriptor so interpreter shutdown cannot retry the flush.
        with open(os.devnull, 'wb') as sink:
            os.dup2(sink.fileno(), sys.stdout.fileno())
        return 0
    except (OSError, ValueError, sqlite3.Error, curses.error) as error:
        parser.exit(1, f'command-search: {error}\n')
    finally:
        if index:
            index.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
