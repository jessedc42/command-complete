"""Scheduling and real SQLite snapshot lifetime across the worker/UI boundary."""

from contextlib import closing
import gc
from pathlib import Path
import tempfile
import threading
import time
import unittest

from command_search_index import DatabaseSearchIndex, write_database
from search_scheduler import HybridSearch
from test_command_search import fixture_index
from command_search_session import SearchSession


def wait_result(search):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        result = search.poll()
        if result is not None:
            return result
        time.sleep(.001)
    raise AssertionError('background search did not finish')


class SchedulerTests(unittest.TestCase):
    def test_pending_query_cannot_freeze_old_results(self):
        index = fixture_index()
        with HybridSearch(lambda query, cancelled: index.search(query)) as search:
            session = SearchSession(index, index.catalog, 'net', scheduler=search)
            deadline = time.monotonic() + 3
            while not session.poll_search() and time.monotonic() < deadline:
                time.sleep(.001)
            self.assertTrue(session.live.results)
            session.set_query('reach')
            self.assertFalse(session.freeze())
            self.assertEqual(session.stage, 'search')
            self.assertFalse(session.live.results)
            while not session.poll_search() and time.monotonic() < deadline:
                time.sleep(.001)
            self.assertTrue(session.freeze())
            self.assertEqual(session.paths, {'ping': ['ping']})

    def test_typing_resets_the_idle_deadline_and_only_searches_the_latest_text(self):
        clock = [0.0]
        queries = []
        index = fixture_index()
        def backend(query, cancelled):
            queries.append(query)
            return index.search(query)
        with HybridSearch(backend, clock=lambda: clock[0]) as search:
            search.request('n')
            self.assertIsNone(search.poll())
            clock[0] = .1
            search.request('ne')
            clock[0] = .2
            search.request('network')
            clock[0] = .449
            self.assertIsNone(search.poll())
            self.assertEqual(queries, [])
            clock[0] = .451
            result = wait_result(search)
            self.assertEqual(queries, ['network'])
            self.assertIn('ping', [r.entry.command for r in result.results])
            self.assertFalse(search.pending)

    def test_space_or_explicit_choice_dispatches_without_waiting_for_idle(self):
        index = fixture_index()
        with HybridSearch(lambda query, cancelled: index.search(query), clock=lambda: 0.0) as search:
            search.request('net ', immediate=True)
            self.assertTrue(wait_result(search).results)
            search.request('reach')
            search.expedite()
            result = wait_result(search)
            self.assertEqual({r.entry.command for r in result.results}, {'ping'})

    def test_an_old_query_cannot_publish_after_new_input(self):
        started, release = threading.Event(), threading.Event()
        index = fixture_index()
        def backend(query, cancelled):
            if query == 'old':
                started.set()
                if not release.wait(2):
                    raise AssertionError('test did not release old query')
                return index.search('net')
            return index.search(query)
        with HybridSearch(backend) as search:
            search.request('old', immediate=True)
            search.poll()
            self.assertTrue(started.wait(1))
            search.request('reach', immediate=True)
            self.assertIsNone(search.poll())
            self.assertTrue(search.pending)
            release.set()
            result = wait_result(search)
            self.assertEqual({r.entry.command for r in result.results}, {'ping'})

    def test_search_error_is_reported_and_a_later_query_can_succeed(self):
        index = fixture_index()
        def backend(query, cancelled):
            if query == 'broken':
                raise ValueError('unreadable index')
            return index.search(query)
        with HybridSearch(backend) as search:
            search.request('broken', immediate=True)
            self.assertIn('unreadable index', wait_result(search).error)
            search.request('reach', immediate=True)
            self.assertTrue(wait_result(search).results)

    def test_shutdown_cancels_a_running_search_and_discards_queued_work(self):
        started, stopped = threading.Event(), threading.Event()
        def backend(query, cancelled):
            started.set()
            deadline = time.monotonic() + 2
            while not cancelled() and time.monotonic() < deadline:
                stopped.wait(.001)
            stopped.set()
            return fixture_index().search(query)
        search = HybridSearch(backend)
        search.request('net', immediate=True)
        search.poll()
        self.assertTrue(started.wait(1))
        search.request('reach', immediate=True)
        search.close()
        self.assertTrue(stopped.is_set())
        self.assertFalse(search.pending)

    def test_completed_sqlite_snapshot_can_be_read_on_ui_and_outlive_later_queries(self):
        source = fixture_index()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'search.db'
            write_database(path, source.catalog, source.metadata)
            with closing(DatabaseSearchIndex(path, source.catalog)) as index:
                with HybridSearch(index.search_background) as search:
                    search.request('net', immediate=True)
                    original = wait_result(search)
                    self.assertEqual(original.results.command_paths(), {'ping', 'ipconfig', 'networksetup'})
                    search.request('reach', immediate=True)
                    latest = wait_result(search)
                    self.assertEqual([r.entry.text for r in latest.results], ['ping', 'ping -c <Count>'])
                    self.assertEqual([e.text for e in original.results.for_command('ipconfig')], ['ipconfig'])
                self.assertEqual(len(original.results), 4)
                del original, latest
                gc.collect()


class GuardSessionTests(unittest.TestCase):
    def make_session(self, enabled=True):
        index = fixture_index()
        self.queries = []
        original = index.search
        def search(query):
            self.queries.append(query)
            return original(query)
        index.search = search
        return SearchSession(index, index.catalog, short_query_guard=enabled)

    def test_guard_is_off_by_default(self):
        index = fixture_index()
        session = SearchSession(index, index.catalog)
        session.set_query('n')
        self.assertTrue(session.live.results)
        self.assertFalse(session.guard_waiting)

    def test_short_unfinished_keyword_is_held_after_typing_or_backspacing(self):
        session = self.make_session()
        for query, held in [('n', True), ('ne', True), ('net', False), ('network ', False), ('n', True)]:
            session.set_query(query)
            self.assertEqual(session.guard_waiting, held, query)
            if held:
                self.assertFalse(session.live.results)
                self.assertIn('3', session.guard_hint)
        self.assertNotIn('n', self.queries)
        self.assertNotIn('ne', self.queries)

    def test_completed_keywords_stay_active_without_requerying_for_short_suffixes(self):
        session = self.make_session()
        session.set_query('network ')
        count = len(self.queries)
        session.set_query('network i')
        session.set_query('network ip')
        self.assertEqual(len(self.queries), count)
        self.assertEqual({r.entry.command for r in session.live.results}, {'ping', 'ipconfig', 'networksetup'})
        self.assertTrue(session.guard_waiting)
        self.assertIn('completed', session.guard_hint.lower())

    def test_explicit_submission_includes_the_short_keyword_before_freezing(self):
        session = self.make_session()
        session.set_query('network i')
        self.assertFalse(session.freeze())
        self.assertFalse(session.guard_waiting)
        self.assertEqual(self.queries[-1], 'network i')
        self.assertTrue(session.freeze())
        session.back()
        session.set_query('ip ', immediate=True)
        self.assertFalse(session.guard_waiting)
        self.assertEqual(self.queries[-1], 'ip ')

    def test_effect_filters_and_unicode_follow_the_same_guard_rules(self):
        session = self.make_session()
        session.set_query('get network i')
        self.assertTrue(session.guard_waiting)
        self.assertTrue(all(r.entry.effect == 'get' for r in session.live.results))
        for query, held in [('ré', True), ('réa', False), ('n--', True), ('get', False)]:
            session.set_query(query)
            self.assertEqual(session.guard_waiting, held, query)

    def test_searchable_characters_count_across_punctuation_and_repeated_segments(self):
        session = self.make_session()
        for query, held in [('ci/cd', False), ('s3.cp', False), ('a-a-a', False), ('n--', True)]:
            session.set_query(query)
            self.assertEqual(session.guard_waiting, held, query)

    def test_guard_handles_a_long_completed_keyword_without_blocking_input(self):
        from command_search_session import automatic_query
        prefix = 'x' * 30000 + ' '
        started = time.perf_counter()
        effective, held = automatic_query(prefix + 'i')
        elapsed = time.perf_counter() - started
        self.assertEqual((effective, held), (prefix, True))
        self.assertLess(elapsed, .5)

    def test_backspacing_cancels_an_old_query_without_searching_the_short_suffix(self):
        index = fixture_index()
        started, cancelled_seen = threading.Event(), threading.Event()
        queries = []
        def backend(query, cancelled):
            queries.append(query)
            if query == 'network':
                started.set()
                deadline = time.monotonic() + 2
                while not cancelled() and time.monotonic() < deadline:
                    cancelled_seen.wait(.001)
                cancelled_seen.set()
            return index.search(query)
        with HybridSearch(backend) as search:
            session = SearchSession(index, index.catalog, 'network', scheduler=search, short_query_guard=True)
            session.poll_search()
            self.assertTrue(started.wait(1))
            session.set_query('n')
            self.assertTrue(cancelled_seen.wait(1))
            session.poll_search()
            self.assertTrue(session.guard_waiting)
            self.assertFalse(session.live.results)
            self.assertEqual(queries, ['network'])


if __name__ == '__main__':
    unittest.main()
