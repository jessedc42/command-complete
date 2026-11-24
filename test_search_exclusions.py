"""Command-name exclusions behave identically in both search backends."""

from contextlib import closing
from pathlib import Path
import tempfile
import unittest

from command_complete import Catalog
from command_search_index import DatabaseSearchIndex, SearchIndex, write_database
from command_search_session import SearchSession
from search_metadata import build_metadata


class NameExclusionTests(unittest.TestCase):
    def setUp(self):
        commands = {
            'aws': {'command_group': True, 'flags': {}},
            'aws network': {'description': 'Inspect network settings.', 'flags': {'--verbose': 'switch'}},
            'awstats': {'description': 'Inspect network statistics.'},
            'helper': {'description': 'Inspect AWS network settings.', 'flags': {'--aws': 'switch'},
                       'flag_descriptions': {'--aws': 'Inspect AWS network settings.'}},
            'tool get': {'description': 'Inspect network settings.'},
            'tool set': {'description': 'Change network settings.'},
            'tool-get': {'description': 'Inspect network settings.'},
        }
        self.catalog = Catalog({'commands': commands})
        self.metadata = build_metadata(commands, {'commands': {
            'tool get': {'effect': 'get'}, 'tool set': {'effect': 'set'}}})

    def check_queries(self, index):
        cases = [
            ('network !AWS', [('helper', 1), ('helper --aws', 1), ('tool get', 1), ('tool set', 1), ('tool-get', 1)]),
            ('network !aws !get', [('helper', 1), ('helper --aws', 1), ('tool set', 1), ('tool-get', 1)]),
            ('network !aws !tool', [('helper', 1), ('helper --aws', 1)]),
            ('network !aws !tool-get', [('helper', 1), ('helper --aws', 1), ('tool get', 1), ('tool set', 1)]),
            ('network !aws !et', [('helper', 1), ('helper --aws', 1), ('tool get', 1), ('tool set', 1), ('tool-get', 1)]),
            ('!aws', [('helper', 0), ('helper --aws', 0), ('tool get', 0), ('tool set', 0), ('tool-get', 0)]),
            ('get !get !aws', [('helper', 0), ('helper --aws', 0), ('tool-get', 0)]),
            ('set !aws', [('tool set', 0)]),
            ('network !network', [('awstats', 1), ('helper', 1), ('helper --aws', 1), ('tool get', 1), ('tool set', 1), ('tool-get', 1)]),
            ('network !aws !AWS !aws', [('helper', 1), ('helper --aws', 1), ('tool get', 1), ('tool set', 1), ('tool-get', 1)]),
            ('aws !aws', [('helper', 1), ('helper --aws', 1)]),
            ('!', []),
            ('!aws network !', [('helper', 1), ('helper --aws', 1), ('tool get', 1), ('tool set', 1), ('tool-get', 1)]),
            ('!no-such-command', [('aws', 0), ('aws network', 0), ('aws network --verbose', 0), ('awstats', 0),
                                  ('helper', 0), ('helper --aws', 0), ('tool get', 0), ('tool set', 0), ('tool-get', 0)]),
        ]
        for query, expected in cases:
            with self.subTest(query=query):
                result = index.search(query)
                self.assertIsNone(result.error)
                self.assertEqual([(r.entry.text, r.score) for r in result.results], expected)
        self.assertTrue(index.search('get set !aws').error)

    def test_memory_search_excludes_names_without_matching_descriptions_or_flags(self):
        self.check_queries(SearchIndex(self.catalog, self.metadata))

    def test_sqlite_search_excludes_names_and_keeps_frozen_results(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'search.db'
            write_database(path, self.catalog, self.metadata)
            with closing(DatabaseSearchIndex(path, self.catalog)) as index:
                frozen = index.search('network !aws').results
                self.check_queries(index)
                self.assertEqual([r.entry.text for r in frozen],
                                 ['helper', 'helper --aws', 'tool get', 'tool set', 'tool-get'])

    def test_short_query_guard_holds_an_incomplete_exclusion_until_submission(self):
        session = SearchSession(SearchIndex(self.catalog, self.metadata), self.catalog, short_query_guard=True)
        session.set_query('network !aw')
        self.assertTrue(session.guard_waiting)
        self.assertIn('aws network', {r.entry.command for r in session.live.results})
        session.set_query('network !aws')
        self.assertFalse(session.guard_waiting)
        self.assertEqual({r.entry.command for r in session.live.results}, {'helper', 'tool get', 'tool set', 'tool-get'})
        session.set_query('network !a', immediate=True)
        self.assertFalse(session.guard_waiting)
        self.assertEqual({r.entry.command for r in session.live.results}, {'helper', 'tool get', 'tool set', 'tool-get'})

    def test_alias_is_excluded_by_its_displayed_name_and_not_its_target(self):
        commands = {'aws': {'flags': {}, 'command_group': True},
                    'aws inspect': {'description': 'Inspect network settings.'},
                    'my-cloud': {'alias': 'aws inspect'}}
        catalog = Catalog({'commands': commands})
        metadata = build_metadata(commands, {})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'search.db'
            write_database(path, catalog, metadata)
            with closing(DatabaseSearchIndex(path, catalog)) as database:
                for index in (SearchIndex(catalog, metadata), database):
                    with self.subTest(backend=type(index).__name__):
                        self.assertEqual([r.entry.text for r in index.search('network !aws').results], ['my-cloud'])


if __name__ == '__main__':
    unittest.main()
