from pathlib import Path
from contextlib import closing
import gzip
import hashlib
import json
import sqlite3
import tempfile
import unittest

from command_complete import Catalog
from command_search_index import SearchIndex
from search_metadata import build_metadata


def fixture_index():
    commands = {
        'ping': {'description': 'Test ICMP network reachability.', 'flags': {'-c': 'value'},
                 'flag_hints': {'-c': 'Count'}, 'flag_descriptions': {'-c': 'Limit probe count.'}},
        'ipconfig': {'description': 'Display network addresses.', 'flags': {}},
        'networksetup': {'description': 'Change network settings.', 'flags': {}},
        'python': {'description': 'Run a Python program.', 'flags': {}}, 'private': {},
        'aws': {'flags': {'--region': 'value'}, 'flag_hints': {'--region': 'Region'},
                'flag_descriptions': {'--region': 'AWS region.'}},
        'aws test': {}, 'aws test list-items': {'description': 'List items.', 'flags': {'--limit': 'value'}},
        'item-list': {'alias': 'aws test list-items'}}
    overrides = {'commands': {'ping': {'effect': 'get', 'terms': ['reachable']},
                              'python': {'effect': 'depends'}}}
    return SearchIndex(Catalog({'commands': commands}), build_metadata(commands, overrides))


class SearchTests(unittest.TestCase):
    def test_inclusive_prefix_matching_scores_distinct_input_words(self):
        results = fixture_index().search('NET reach dog net').results
        self.assertEqual([(r.entry.text, r.score) for r in results],
                         [('ping', 2), ('ping -c <Count>', 2), ('ipconfig', 1), ('networksetup', 1)])

    def test_effect_filters_do_not_become_or_keywords(self):
        index = fixture_index()
        self.assertEqual([r.entry.text for r in index.search('get net dog').results],
                         ['ipconfig', 'ping', 'ping -c <Count>'])
        self.assertEqual([r.entry.text for r in index.search('set net').results], ['networksetup'])
        self.assertTrue(index.search('get set network').error)
        self.assertFalse(index.search('get python').results)
        self.assertFalse(index.search('get private').results)

    def test_empty_filter_only_and_non_substring_queries(self):
        index = fixture_index()
        self.assertFalse(index.search('').results)
        self.assertTrue(index.search('get').results)
        self.assertFalse(index.search('etwork').results)
        self.assertEqual(index.search('reach reachable').results[0].score, 2)

    def test_inherited_options_and_aliases_keep_their_command_path(self):
        index = fixture_index()
        entries = {e.text: e for e in index.entries_for_command('aws test list-items')}
        self.assertIn('aws test list-items --region <Region>', entries)
        self.assertEqual(entries['aws test list-items --region <Region>'].description, 'AWS region.')
        alias = {e.text: e for e in index.entries_for_command('item-list')}
        self.assertIn('item-list --limit <Value>', alias)
        self.assertIn('item-list --region <Region>', alias)
        self.assertEqual([m.text for m in index.catalog.matches('item-list --reg')], ['--region'])

    def test_recipe_components_keep_placeholders_separate_from_insertable_tokens(self):
        catalog = Catalog({'commands': {'ping': {'flags': {'-c': 'value', '-i': 'value'}}}})
        metadata = {'commands': {}, 'recipes': [{'id': 'ping-limited', 'command': 'ping',
                    'description': 'Send a limited sequence of spaced probes.', 'effect': 'get',
                    'terms': ['test'], 'options': [{'flag': '-c', 'arguments': ['Count']},
                                                 {'flag': '-i', 'arguments': ['Seconds']}]}]}
        index = SearchIndex(catalog, metadata)
        entry = index.search('spaced').results[0].entry
        self.assertEqual(entry.text, 'ping -c <Count> -i <Seconds>')
        self.assertEqual(entry.options[0].flag, '-c')
        self.assertEqual(entry.options[0].arguments, ('Count',))

    def test_prebuilt_database_preserves_rank_scope_and_frozen_results(self):
        import command_search_index as search
        source = fixture_index()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'search.db'
            search.write_database(path, source.catalog, source.metadata)
            index = search.DatabaseSearchIndex(path, source.catalog)
            frozen = index.search('NET reach dog net').results
            index.search('get private')
            self.assertEqual([(r.entry.text, r.score) for r in frozen],
                             [('ping', 2), ('ping -c <Count>', 2), ('ipconfig', 1), ('networksetup', 1)])
            self.assertEqual(frozen[-1].entry.command, 'networksetup')
            self.assertIn('item-list --region <Region>',
                          [e.text for e in index.entries_for_command('item-list')])
            self.assertTrue(index.search('get set').error)
            index.close()

    def test_recipe_context_matches_identically_in_memory_and_prebuilt_index(self):
        import command_search_index as search
        catalog = Catalog({'commands': {'tool': {'description': 'Inspect network resources.', 'flags': {'-v': 'switch'}}}})
        meta = build_metadata(catalog.commands, {'recipes': [{'id': 'verbose', 'command': 'tool',
                              'description': 'Show extra details.', 'effect': 'get', 'options': [{'flag': '-v'}]}]})
        expected = ['tool', 'tool -v', 'tool -v']
        self.assertEqual([r.entry.text for r in SearchIndex(catalog, meta).search('network').results], expected)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'search.db'
            search.write_database(path, catalog, meta)
            index = search.DatabaseSearchIndex(path, catalog)
            self.assertEqual([r.entry.text for r in index.search('network').results], expected)
            index.close()

    def test_stale_prebuilt_index_rejects_a_changed_completion_snapshot(self):
        import command_search_index as search
        source = fixture_index()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'search.db'
            catalog_path = Path(tmp) / 'catalog.json.gz'
            with gzip.open(catalog_path, 'wt') as f:
                json.dump({'commands': source.catalog.commands}, f)
            search.write_database(path, source.catalog, source.metadata)
            digest = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
            with closing(sqlite3.connect(path)) as connection:
                connection.execute('INSERT INTO info VALUES (?,?)', ('catalog_sha256', digest))
                connection.commit()
            with gzip.open(catalog_path, 'wt') as f:
                json.dump({'commands': {'changed': {}}}, f)
            with self.assertRaisesRegex(ValueError, 'rebuild'):
                search.DatabaseSearchIndex(path, Catalog({'commands': {'changed': {}}}), catalog_path)

    def test_alias_keeps_its_custom_terms_and_canonical_flag_effects(self):
        catalog = Catalog({'commands': {'tool': {}, 'tool change': {'flags': {'--preview': 'switch'}},
                                       'tool edit': {'alias': 'tool change'}}})
        meta = build_metadata(catalog.commands, {'commands': {
            'tool change': {'effect': 'set', 'flags': {'--preview': {'effect': 'get'}}},
            'tool edit': {'terms': ['myshortcut']}}})
        index = SearchIndex(catalog, meta)
        self.assertEqual([r.entry.text for r in index.search('get myshortcut').results], ['tool edit --preview'])


if __name__ == '__main__':
    unittest.main()
