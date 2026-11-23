"""Acceptance checks against both complete, prebuilt platform search datasets."""

import gzip
from itertools import groupby
import json
from pathlib import Path
import unittest

from command_complete import Catalog
from command_search import cached_database
from command_search_index import DatabaseSearchIndex


ROOT = Path(__file__).parent


class BundledSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.platforms = []
        for platform, filename in [('macos', 'catalog.json.gz'), ('ubuntu', 'catalog-ubuntu.json.gz')]:
            with gzip.open(ROOT / filename, 'rt') as f:
                data = json.load(f)
            catalog = Catalog(data)
            database = ROOT / f'search-{platform}.db.gz'
            if not database.exists():
                raise AssertionError(f'Missing complete {platform} search database')
            cls.platforms.append((platform, catalog, DatabaseSearchIndex(cached_database(database), catalog)))

    @classmethod
    def tearDownClass(cls):
        for _, _, index in cls.platforms:
            index.close()

    def test_every_command_and_inherited_option_is_indexed(self):
        for platform, catalog, index in self.platforms:
            actual = index.connection.execute('SELECT command,stable_id FROM entries ORDER BY command')
            seen = set()
            for name, rows in groupby(actual, lambda row: row[0]):
                seen.add(name)
                ids = {row[1] for row in rows if not row[1].startswith('recipe:')}
                canonical = index.resolve(name)
                expected = {name} | {name + '\t' + flag for flag in catalog.flags(canonical.split()[0], canonical)}
                self.assertEqual(ids, expected, f'{platform}: {name}')
            self.assertEqual(seen, set(catalog.commands))

    def test_available_cli_operation_and_option_descriptions_are_imported(self):
        for platform, catalog, _ in self.platforms:
            entry = catalog.commands['aws ec2 describe-instances']
            self.assertIn('instance', entry['description'].lower(), platform)
            for flag in ('--instance-ids', '--filters', '--cli-input-json', '--generate-cli-skeleton'):
                self.assertTrue(entry['flag_descriptions'].get(flag), f'{platform}: {flag}')
            self.assertTrue(catalog.commands['aws']['flag_descriptions'].get('--query'), platform)
            if 'terraform init' in catalog.commands:
                self.assertTrue(catalog.commands['terraform init'].get('flag_descriptions', {}).get('-upgrade'), platform)
            if '--config' in catalog.commands.get('rclone', {}).get('flags', {}):
                self.assertTrue(catalog.commands['rclone'].get('flag_descriptions', {}).get('--config'), platform)
            self.assertNotIn('--outfile', catalog.commands['aws apigateway get-export'].get('flags', {}))
            self.assertIn('Output file', catalog.commands['aws apigateway get-export'].get('arguments', []))

    def test_purpose_searches_find_documented_tasks_in_each_family(self):
        for platform, _, index in self.platforms:
            for query, command in [('get network reachability dog', 'ping'),
                                   ('get disk space', 'df'), ('set stop containers', 'docker stop'),
                                   ('get display resources', 'kubectl get'),
                                   ('get inspect instances', 'aws ec2 describe-instances')]:
                matches = index.search(query).results.for_command(command)
                self.assertTrue(matches, f'{platform}: {query} -> {command}')
                self.assertTrue(all(e.description != 'Description unavailable' for e in matches if not e.options))

    def test_curated_combinations_cover_each_command_family(self):
        for platform, _, index in self.platforms:
            recipes = {row[0] for row in index.connection.execute("SELECT stable_id FROM entries WHERE stable_id LIKE 'recipe:%'")}
            self.assertTrue({'recipe:ls-readable', 'recipe:ping-paced', 'recipe:docker-follow-tail',
                             'recipe:kubectl-pods-wide', 'recipe:aws-instance-fields'} <= recipes, platform)

    def test_coverage_reports_distinguish_unknown_metadata(self):
        for platform, _, _ in self.platforms:
            with gzip.open(ROOT / f'search-coverage-{platform}.json.gz', 'rt') as f:
                report = json.load(f)
            self.assertGreater(report['commands_described'], 20000)
            self.assertGreater(report['flags_described'], 130000)
            self.assertTrue(report['missing_descriptions'])
            self.assertTrue(all(item['reason'] for item in report['missing_descriptions']))
            self.assertGreater(report['effects'].get('depends', 0), 0)
            self.assertGreater(report['effects'].get('unknown', 0), 0)

    def test_both_utilities_and_short_search_name_are_discoverable(self):
        for platform, catalog, index in self.platforms:
            for command in ('command-complete', 'command-search', 'cs'):
                self.assertTrue(command in catalog.commands, f'{platform}: missing {command}')
                self.assertTrue(index.search('autocomplete command search').results.for_command(command), platform)


if __name__ == '__main__':
    unittest.main()
