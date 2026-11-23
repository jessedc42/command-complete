import unittest
import shlex

from command_complete import Catalog
from command_search_index import SearchIndex
from command_search_session import SearchSession
from search_metadata import build_metadata


def session(query='network'):
    commands = {
        'ping': {'description': 'Test network reachability.', 'flags': {'-c': 'value', '-i': 'value', '-q': 'switch'},
                 'flag_hints': {'-c': 'Count', '-i': 'Seconds'}, 'short_options': True},
        'nc': {'description': 'Test network connections.', 'flags': {'-l': 'switch', '-z': 'switch', '-p': 'value'},
               'flag_hints': {'-p': 'Port'}, 'flag_conflicts': [[['-l'], ['-z']]], 'short_options': True},
        'docker': {'command_group': True, 'flags': {'--context': 'value', '--help': 'switch'}},
        'docker stop': {'description': 'Stop network containers.', 'flags': {'--time': 'value'}}}
    metadata = build_metadata(commands, {'recipes': [{'id': 'ping-paced', 'command': 'ping',
        'description': 'Test network with paced probes.', 'effect': 'get', 'terms': ['paced'],
        'options': [{'flag': '-c', 'arguments': ['Count']}, {'flag': '-i', 'arguments': ['Seconds']}]}]})
    catalog = Catalog({'commands': commands})
    return SearchSession(SearchIndex(catalog, metadata), catalog, query)


def entry(s, text):
    return next(e for e in s.index.entries_for_command(text.split()[0]) if e.text == text)


class SessionTests(unittest.TestCase):
    def test_manual_matching_waits_for_complete_command_then_focuses_frozen_hits(self):
        s = session()
        original = tuple(r.entry.id for r in s.live.results)
        self.assertTrue(s.freeze())
        self.assertEqual(s.stage, 'choose')
        s.set_draft('docker ')
        self.assertEqual(s.stage, 'choose')
        s.set_draft('docker stop')
        self.assertEqual(s.stage, 'choose')
        s.set_draft('docker --context test stop ')
        self.assertEqual(s.stage, 'draft')
        self.assertEqual(s.command, 'docker stop')
        self.assertTrue(all(e.command == 'docker stop' for e in s.reference))
        self.assertEqual(tuple(r.entry.id for r in s.frozen), original)

    def test_direct_selection_inserts_flag_and_keeps_placeholders_out_of_draft(self):
        s = session()
        s.freeze(entry(s, 'ping -c <Count>'))
        self.assertEqual(s.stage, 'draft')
        self.assertEqual(s.draft, 'ping -c ')
        self.assertEqual(s.pending_hint, 'Count')
        self.assertFalse(s.confirm_value())
        s.set_draft('ping -c 4')
        self.assertTrue(s.confirm_value())
        self.assertEqual(s.draft, 'ping -c 4 ')
        self.assertIsNone(s.pending_hint)

    def test_guided_combination_accepts_each_value_explicitly(self):
        s = session()
        recipe = next(e for e in s.index.entries_for_command('ping') if e.id.startswith('recipe:'))
        s.freeze(recipe)
        s.set_draft(s.draft + '4')
        self.assertTrue(s.confirm_value())
        self.assertEqual(s.draft, 'ping -c 4 -i ')
        self.assertEqual(s.pending_hint, 'Seconds')
        s.set_draft(s.draft + '0.5')
        s.confirm_value()
        self.assertEqual(s.draft, 'ping -c 4 -i 0.5 ')
        self.assertIsNone(s.pending_hint)

    def test_unfinished_quotes_do_not_advance_and_shell_text_stays_inert(self):
        s = session()
        s.freeze(entry(s, 'nc -p <Port>'))
        s.set_draft(s.draft + "'unfinished")
        self.assertFalse(s.confirm_value())
        self.assertEqual(s.pending_hint, 'Port')
        s.set_draft("nc -p '$(touch /tmp/cs-never-execute)' ")
        self.assertTrue(s.confirm_value())
        self.assertIn('$(touch /tmp/cs-never-execute)', s.draft)

    def test_conflicting_reference_entry_is_unavailable_and_draft_is_unchanged(self):
        s = session()
        s.freeze(entry(s, 'nc -l'))
        conflicting = entry(s, 'nc -z')
        self.assertIn('conflicts', s.unavailable_reason(conflicting))
        before = s.draft
        self.assertFalse(s.insert_entry(conflicting))
        self.assertEqual(s.draft, before)
        self.assertIn(conflicting, s.reference)

    def test_backtracking_restores_query_and_resumes_same_command(self):
        s = session()
        s.freeze(entry(s, 'ping -q'))
        s.set_draft('ping -q example.org ')
        s.back()
        self.assertEqual(s.stage, 'choose')
        s.back()
        self.assertEqual(s.stage, 'search')
        self.assertEqual(s.query, 'network')
        s.freeze()
        s.set_draft('ping ')
        self.assertEqual(s.draft, 'ping -q example.org ')
        s.back()
        s.set_draft('nc ')
        self.assertEqual(s.draft, 'nc ')

    def test_existing_values_are_preserved_and_switches_are_not_duplicated(self):
        s = session()
        s.freeze(entry(s, 'ping -q'))
        s.insert_entry(entry(s, 'ping -q'))
        self.assertEqual(s.draft, 'ping -q ')
        s.set_draft('ping -c 7 ')
        s.insert_entry(entry(s, 'ping -c <Count>'))
        self.assertEqual(s.draft, 'ping -c 7 ')

    def test_editing_earlier_command_cancels_pending_recipe_steps(self):
        s = session()
        recipe = next(e for e in s.index.entries_for_command('ping') if e.id.startswith('recipe:'))
        s.freeze(recipe)
        s.set_draft('nc -p 80 ')
        self.assertIsNone(s.pending_hint)
        self.assertEqual(s.command, 'nc')
        self.assertFalse(s.confirm_value())
        self.assertEqual(s.draft, 'nc -p 80 ')

    def test_unmatched_paths_and_empty_results_do_not_activate(self):
        s = session('nonexistent')
        self.assertFalse(s.freeze())
        s.set_query('network')
        s.freeze()
        s.set_draft('other-command ')
        self.assertEqual(s.stage, 'choose')

    def test_selecting_help_for_a_command_group_can_return_a_help_draft(self):
        s = session('docker')
        s.freeze(entry(s, 'docker --help'))
        self.assertEqual(s.stage, 'draft')
        self.assertEqual(s.draft, 'docker --help ')

    def test_documented_inherited_repeatable_option_can_be_added_again(self):
        commands = {'kubectl': {'flags': {'--as-group': 'value'}, 'command_group': True,
                               'flag_hints': {'--as-group': 'Group'}, 'repeatable_flags': ['--as-group']},
                    'kubectl get': {'description': 'Read network resource information.', 'flags': {}}}
        catalog = Catalog({'commands': commands})
        s = SearchSession(SearchIndex(catalog, build_metadata(commands, {})), catalog, 'network')
        s.freeze()
        s.set_draft('kubectl --as-group dev get ')
        self.assertEqual(s.command, 'kubectl get')
        target = next(e for e in s.index.entries_for_command('kubectl get') if e.options and e.options[0].flag == '--as-group')
        s.insert_entry(target)
        self.assertEqual(s.draft, 'kubectl --as-group dev get --as-group ')
        self.assertEqual(s.pending_hint, 'Group')

    def test_resuming_visible_draft_restores_the_guided_queue(self):
        s = session('paced')
        s.freeze(next(e for e in s.index.entries_for_command('ping') if e.id.startswith('recipe:')))
        s.set_draft(s.draft + '4')
        s.back()
        s.set_draft(s.draft)
        self.assertEqual(s.pending_hint, 'Count')
        self.assertTrue(s.confirm_value())
        self.assertEqual(s.draft, 'ping -c 4 -i ')

    def test_editing_a_backtracked_value_resumes_its_remaining_steps(self):
        s = session('paced')
        s.freeze(next(e for e in s.index.entries_for_command('ping') if e.id.startswith('recipe:')))
        s.set_draft(s.draft + '4')
        s.back()
        s.set_draft(s.draft + '0')
        self.assertEqual(s.pending_hint, 'Count')
        self.assertTrue(s.confirm_value())
        self.assertEqual(s.draft, 'ping -c 40 -i ')

    def test_guidance_lists_remaining_operands_of_the_current_option(self):
        commands = {'tool': {'description': 'Show paired values.', 'flags': {'--pair': 'value'},
                             'flag_arguments': {'--pair': ['First', 'Second']}}}
        catalog = Catalog({'commands': commands})
        s = SearchSession(SearchIndex(catalog, build_metadata(commands, {})), catalog, 'paired')
        s.freeze(next(r.entry for r in s.live.results if r.entry.options))
        self.assertIn('<Second>', s.next_steps)

    def test_escaped_trailing_space_survives_confirmation_and_insertion(self):
        for suffix in ('foo\\ ', 'foo\\  '):
            s = session('paced')
            s.freeze(next(e for e in s.index.entries_for_command('ping') if e.id.startswith('recipe:')))
            s.set_draft(s.draft + suffix)
            self.assertTrue(s.confirm_value(), repr(suffix))
            self.assertEqual(shlex.split(s.draft), ['ping', '-c', 'foo ', '-i'])
        s = session()
        s.freeze(entry(s, 'ping'))
        s.set_draft('ping -c foo\\ ')
        self.assertTrue(s.insert_entry(entry(s, 'ping -q')))
        self.assertEqual(shlex.split(s.draft), ['ping', '-c', 'foo ', '-q'])

    def test_reference_options_are_blocked_after_the_option_terminator(self):
        s = session()
        s.freeze(entry(s, 'ping'))
        s.set_draft('ping -- ')
        self.assertFalse(s.insert_entry(entry(s, 'ping -q')))
        self.assertEqual(s.draft, 'ping -- ')
        self.assertIn('--', s.message)
        # A required option value of '--' is not an option terminator.
        s.set_draft('ping -c -- ')
        self.assertTrue(s.insert_entry(entry(s, 'ping -q')))

    def test_shell_operators_preserve_the_primary_scope_and_literal_draft(self):
        s = session()
        s.freeze(entry(s, 'ping'))
        for draft in ('ping host >results', 'ping host | cat', 'ping host; echo ok'):
            s.set_draft(draft)
            self.assertEqual(s.stage, 'draft', draft)
            self.assertEqual(s.command, 'ping')
            self.assertFalse(s.insert_entry(entry(s, 'ping -q')))
            self.assertEqual(s.draft, draft)
        s.set_draft('unmatched-command | cat')
        self.assertEqual(s.stage, 'choose')

    def test_fixed_recipe_operands_are_inserted_from_reference_and_not_duplicated(self):
        commands = {'kubectl': {'command_group': True, 'flags': {'-n': 'value'}},
                    'kubectl get': {'description': 'Display resources.', 'flags': {'-o': 'value'}}}
        catalog = Catalog({'commands': commands})
        meta = build_metadata(commands, {'recipes': [{'id': 'pods', 'command': 'kubectl get',
            'description': 'Display pods.', 'effect': 'get', 'positionals': ['pods'],
            'options': [{'flag': '-o', 'values': ['wide']}]}]})
        s = SearchSession(SearchIndex(catalog, meta), catalog, 'display')
        s.freeze()
        s.set_draft('kubectl -n test get ')
        recipe = next(e for e in s.reference if e.id == 'recipe:pods')
        self.assertTrue(s.insert_entry(recipe))
        self.assertEqual(s.draft, 'kubectl -n test get pods -o wide ')
        self.assertTrue(s.insert_entry(recipe))
        self.assertEqual(s.draft, 'kubectl -n test get pods -o wide ')
        s.set_draft('kubectl get services ')
        self.assertFalse(s.insert_entry(recipe))
        self.assertEqual(s.draft, 'kubectl get services ')
        self.assertIn('pods', s.message)

    def test_version_value_is_guided_instead_of_treated_as_a_display_switch(self):
        commands = {'pkgbuild': {'description': 'Create a package.', 'flags': {'--version': 'value'},
                                 'flag_hints': {'--version': 'Package version'},
                                 'flag_descriptions': {'--version': 'Specify the version of the package.'}}}
        catalog = Catalog({'commands': commands})
        s = SearchSession(SearchIndex(catalog, build_metadata(commands, {})), catalog, 'package')
        target = next(e for e in s.live.results if e.entry.options).entry
        s.freeze(target)
        self.assertEqual(s.draft, 'pkgbuild --version ')
        self.assertEqual(s.pending_hint, 'Package version')


if __name__ == '__main__':
    unittest.main()
