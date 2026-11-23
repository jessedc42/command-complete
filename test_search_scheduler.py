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


if __name__ == '__main__':
    unittest.main()
