import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess
from contextlib import redirect_stdout
import io

import search_metadata as metadata
from build_catalog import flag_descriptions


class MetadataImportTests(unittest.TestCase):
    def test_snapshot_rebuild_preserves_specific_missing_description_evidence(self):
        from build_search_catalog import build_platform, read_json
        data = {'commands': {'compiler': {'description': 'Compile source files.',
                'flags': {'--color': 'unknown'}, 'documentation_source': 'man:compiler',
                'flag_descriptions': {'--color': '--color=always'}}}}
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
            root = Path(tmp)
            build_platform('macos', data, {}, root, [])
            snapshot = read_json(root / 'catalog.json.gz')
            report = build_platform('macos', snapshot, {}, root, [])
        reason = next(gap['reason'] for gap in report['missing_descriptions'] if gap['command'] == 'compiler')
        self.assertEqual(reason, 'source text is an option spelling, not purpose prose')

    def test_html_cleanup_preserves_words_without_tags_or_control_codes(self):
        self.assertEqual(metadata.clean_description('<p>Lists <b>network</b> interfaces &amp; addresses.</p><p>Details.</p>'),
                         'Lists network interfaces & addresses.')
        self.assertEqual(metadata.clean_description('<p>Do\x1b[31m not use\ncontrols.</p>'), 'Do not use controls.')

    def test_aws_model_imports_operations_members_shared_shapes_and_negative_boolean(self):
        commands = {'aws': {'flags': {}}, 'aws ec2': {}, 'aws ec2 describe-instances': {'flags': {
            '--instance-ids': 'many', '--filters': 'many', '--enabled': 'switch', '--no-enabled': 'switch'}},
            'aws ec2 undocumented-action': {'flags': {'--something': 'value'}}}
        model = {'metadata': {'serviceFullName': 'Amazon Elastic Compute Cloud'}, 'operations': {
            'DescribeInstances': {'documentation': '<p>Describes your EC2 instances.</p>', 'input': {'shape': 'Input'}}},
            'shapes': {'Input': {'members': {
                'InstanceIds': {'shape': 'IDs', 'documentation': '<p>The IDs of the instances.</p>'},
                'Filters': {'shape': 'Filters'}, 'Enabled': {'shape': 'Boolean', 'documentation': 'Enable detailed results.'}}},
                'IDs': {'type': 'list'}, 'Filters': {'type': 'list', 'documentation': 'Filters used to select instances.'},
                'Boolean': {'type': 'boolean'}}}
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'ec2' / '2020-01-01'
            p.mkdir(parents=True)
            (p / 'service-2.json').write_text(json.dumps(model))
            metadata.import_aws_models(commands, Path(tmp))
        entry = commands['aws ec2 describe-instances']
        self.assertEqual(entry['description'], 'Describes your EC2 instances.')
        self.assertEqual(entry['flag_descriptions']['--instance-ids'], 'The IDs of the instances.')
        self.assertEqual(entry['flag_descriptions']['--filters'], 'Filters used to select instances.')
        from command_complete import Catalog
        self.assertEqual(Catalog({'commands': commands}).complete('aws ec2 describe-instances --instance-ids ').hint,
                         'Instance IDs')
        self.assertIn('Disable', entry['flag_descriptions']['--no-enabled'])
        self.assertTrue(commands['aws ec2']['command_group'])
        self.assertNotIn('description', commands['aws ec2 undocumented-action'])

    def test_manual_summary_is_scoped_to_name_section(self):
        manual = 'PING(8)\n\nNAME\n     ping — send ICMP ECHO_REQUEST packets to network hosts\n\nSYNOPSIS\n     ping host\n\nDESCRIPTION\n     Further details.\n'
        self.assertEqual(metadata.manual_summary(manual), 'send ICMP ECHO_REQUEST packets to network hosts')
        self.assertEqual(metadata.manual_summary('SYNOPSIS\n ping host\n'), '')

    def test_help_summary_uses_command_purpose_before_usage(self):
        self.assertEqual(metadata.help_summary('Stop one or more running containers\n\nUsage: docker stop [OPTIONS] CONTAINER'),
                         'Stop one or more running containers')
        self.assertEqual(metadata.help_summary('Usage: docker stop [OPTIONS] CONTAINER\n\nStop one or more running containers\n\nOptions:\n  --help Help'),
                         'Stop one or more running containers')

    def test_overrides_supply_purpose_terms_effects_and_preserve_unknowns(self):
        commands = {'ping': {'description': 'Send ICMP packets.', 'flags': {'-c': 'value'},
                             'flag_descriptions': {'-c': 'Stop after the requested probe count.'}},
                    'private-tool': {'flags': {'-x': 'unknown'}}}
        overrides = {'commands': {'ping': {'effect': 'get', 'terms': ['reachable', 'test'],
                            'flags': {'-c': {'terms': ['limit'], 'effect': 'get'}}}}, 'recipes': []}
        data = metadata.build_metadata(commands, overrides)
        self.assertIn('reachable', data['commands']['ping']['terms'])
        self.assertEqual(data['commands']['ping']['effect'], 'get')
        self.assertEqual(data['commands']['private-tool']['effect'], 'unknown')
        gaps = data['report']['missing_descriptions']
        self.assertIn({'command': 'private-tool', 'reason': 'source description unavailable'}, gaps)
        self.assertIn({'command': 'private-tool', 'flag': '-x', 'reason': 'source description unavailable'}, gaps)

    def test_effect_inference_requires_descriptive_evidence(self):
        data = metadata.build_metadata({'aws test delete-whatever': {'flags': {}},
                'aws test create-thing': {'description': 'Creates a new thing.', 'flags': {}},
                'aws test list-things': {'description': 'Lists the available things.', 'flags': {}}}, {})
        self.assertEqual(data['commands']['aws test delete-whatever']['effect'], 'unknown')
        self.assertEqual(data['commands']['aws test create-thing']['effect'], 'set')
        self.assertEqual(data['commands']['aws test list-things']['effect'], 'get')

    def test_manual_alias_headers_share_the_following_description(self):
        content = ('OPTIONS\n       -I dir\n       -iquote dir\n       -isystem dir\n'
                   '           Add the directory to the header search path.\n\n'
                   '       -O0 Reduce compilation time and support debugging.\n\n'
                   '       -F\n       --fix\n       -FF\n       --fixfix\n'
                   '           Fix the archive directory.\n\n       -#\n       (-0, -1, -2)\n'
                   '           Select the compression speed.\n')
        descriptions = flag_descriptions(content, dict.fromkeys(['-I', '-iquote', '-isystem', '-O0', '-F', '--fix', '-FF', '--fixfix', '-#', '-0', '-1', '-2']))
        self.assertEqual(descriptions.get('-I'), 'Add the directory to the header search path.')
        self.assertEqual(descriptions.get('-iquote'), 'Add the directory to the header search path.')
        self.assertEqual(descriptions.get('-O0'), 'Reduce compilation time and support debugging.')
        self.assertEqual(descriptions.get('-F'), 'Fix the archive directory.')
        self.assertEqual(descriptions.get('--fix'), 'Fix the archive directory.')
        self.assertEqual(descriptions.get('-#'), 'Select the compression speed.')

    def test_aws_inline_shared_option_headers_have_descriptions(self):
        content = ('OPTIONS\n       --cli-input-json | --cli-input-yaml (string) Reads arguments from the\n'
                   '       supplied input document.\n\n'
                   '       --generate-cli-skeleton (string) Prints an input example without\n'
                   '       sending an API request.\n\n')
        descriptions = metadata.aws_help_descriptions(content, ['--cli-input-json', '--cli-input-yaml', '--generate-cli-skeleton'])
        self.assertEqual(descriptions['--cli-input-json'], 'Reads arguments from the supplied input document.')
        self.assertEqual(descriptions['--cli-input-yaml'], 'Reads arguments from the supplied input document.')
        self.assertIn('without sending an API request', descriptions['--generate-cli-skeleton'])

    def test_aliases_inherit_documented_purpose_in_coverage_report(self):
        data = metadata.build_metadata({'tool show': {'description': 'Display useful information.', 'flags': {}},
                                        'tool view': {'alias': 'tool show'}}, {})
        self.assertEqual(data['commands']['tool view']['description'], 'Display useful information.')
        self.assertEqual(data['commands']['tool view']['effect'], 'get')
        self.assertFalse(data['report']['missing_descriptions'])
        exported = metadata.build_metadata({'tool export': {'description': 'Retrieves information.',
                    'documented_effect': 'set', 'flags': {}}, 'tool download': {'alias': 'tool export'}}, {})
        self.assertEqual(exported['commands']['tool download']['effect'], 'set')

    def test_documented_aws_output_filename_is_a_positional_not_a_flag(self):
        from build_search_catalog import merge_documentation
        from command_complete import Catalog
        content = ('OPTIONS\n       --id (string)\n          Resource identifier.\n\n'
                   '       outfile (string) [required] Filename where the content will be saved\n\nGLOBAL OPTIONS\n')
        positionals = metadata.aws_help_positionals(content)
        commands = {'aws': {'flags': {}}, 'aws example': {'flags': {}},
                    'aws example get-data': {'description': 'Retrieves the data.', 'flags': {'--id': 'value', '--outfile': 'value'}}}
        merge_documentation(commands, {'aws example get-data': {'positionals': positionals}})
        self.assertNotIn('--outfile', commands['aws example get-data']['flags'])
        self.assertEqual(Catalog({'commands': commands}).complete('aws example get-data ').hint, 'Output file')
        compiled = metadata.build_metadata(commands, {})
        self.assertEqual(compiled['commands']['aws example get-data']['effect'], 'set')
        self.assertIn('output file', compiled['commands']['aws example get-data']['description'].lower())

    def test_output_file_description_is_stable_when_rebuilt_without_new_sources(self):
        commands = {'aws example get-data': {'description': 'Retrieves ' + 'instance information ' * 18,
                    'documented_effect': 'set', 'documented_positionals': [{'name': 'outfile'}], 'flags': {}}}
        first = metadata.build_metadata(commands, {})['commands']['aws example get-data']['description']
        commands['aws example get-data']['description'] = first
        second = metadata.build_metadata(commands, {})['commands']['aws example get-data']['description']
        self.assertEqual(first, second)

    def test_version_and_dry_run_effects_follow_the_documented_form(self):
        commands = {'pkgbuild': {'description': 'Create a package.', 'flags': {'--version': 'value'},
                                 'flag_descriptions': {'--version': 'Specify a version for the package.'}},
                    'aws ec2 terminate-instances': {'description': 'Terminates the instances.',
                        'flags': {'--dry-run': 'switch', '--no-dry-run': 'switch'},
                        'flag_descriptions': {'--dry-run': 'Checks permissions without actually making the request.'}},
                    'kubectl apply': {'description': 'Change resources.', 'flags': {'--dry-run': 'value'},
                        'flag_descriptions': {'--dry-run': 'Must be none, server, or client.'}}}
        data = metadata.build_metadata(commands, {})['commands']
        self.assertEqual(data['pkgbuild']['flags']['--version']['effect'], 'set')
        self.assertEqual(data['aws ec2 terminate-instances']['flags']['--dry-run']['effect'], 'get')
        self.assertEqual(data['aws ec2 terminate-instances']['flags']['--no-dry-run']['effect'], 'set')
        self.assertEqual(data['kubectl apply']['flags']['--dry-run']['effect'], 'depends')

    def test_manual_inline_prose_and_attached_headings_supply_real_descriptions(self):
        text = ('NAME\n tool - test compiler\n\nSYNOPSIS\n tool [-Bprefix] [--dry-run]\n\n'
                'DESCRIPTION\n       With --dry-run option, report what branches would be pruned, but do\n'
                '       not actually prune them.\n\nOPTIONS\n   -special\n       A shallow entry.\n\n'
                '       -Bprefix\n           Specify where to find compiler executables.\n\n'
                '       -fcolor[=WHEN]\n       -fno-color\n           Use color in diagnostics.\n\n'
                'EXAMPLES\n       tool --unused\n')
        result = flag_descriptions(text, dict.fromkeys(['--dry-run', '-B', '-special', '-fcolor', '-fno-color', '--unused']))
        self.assertIn('not actually prune', result.get('--dry-run', ''))
        self.assertEqual(result.get('-B'), 'Specify where to find compiler executables.')
        self.assertEqual(result.get('-fcolor'), 'Use color in diagnostics.')
        self.assertNotIn('--unused', result)

    def test_gap_report_distinguishes_an_unread_source_and_an_extraction_gap(self):
        data = metadata.build_metadata({'private': {}, 'tool': {'description': 'Show network information.',
            'documentation_source': 'man:tool', 'flags': {'--missing': 'unknown'}}}, {})
        gaps = data['report']['missing_descriptions']
        private = next(g for g in gaps if g['command'] == 'private')
        known = next(g for g in gaps if g['command'] == 'tool')
        self.assertNotEqual(private['reason'], known['reason'])
        self.assertIn('available', known['reason'])
        self.assertGreater(data['report']['term_enrichment']['commands'], 0)

    def test_an_unrequested_alias_header_does_not_hide_the_requested_prose(self):
        text = 'OPTIONS\n       -Bprefix\n       --prefix prefix\n           Find compiler executables and libraries.\n'
        self.assertEqual(flag_descriptions(text, {'-B': 'unknown'}).get('-B'),
                         'Find compiler executables and libraries.')

    def test_unread_manual_is_reported_as_unread(self):
        from build_catalog import add_manuals
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / 'man1'
            directory.mkdir()
            (directory / 'tool.1').write_text('.TH TOOL 1\n')
            def capture(executable, *args):
                if executable == 'manpath':
                    return tmp
                raise subprocess.CalledProcessError(1, [executable])
            commands = {'tool': {'flags': {'-x': 'unknown'}}}
            with patch('build_catalog.shutil.which', side_effect=lambda name: name), patch('build_catalog.capture', side_effect=capture):
                add_manuals(commands)
            data = metadata.build_metadata(commands, {})
            self.assertTrue(all('could not be read' in gap['reason'] for gap in data['report']['missing_descriptions']))

    def test_an_option_spelling_is_not_counted_as_a_purpose_description(self):
        data = metadata.build_metadata({'compiler': {'flags': {'-fcolor': 'unknown'},
             'documentation_source': 'man:compiler', 'flag_descriptions': {'-fcolor': '-fcolor=always'}}}, {})
        self.assertEqual(data['commands']['compiler']['flags']['-fcolor']['description'], '')
        self.assertEqual(data['report']['flags_described'], 0)
        self.assertTrue(any('spelling' in gap['reason'] for gap in data['report']['missing_descriptions']))


if __name__ == '__main__':
    unittest.main()
