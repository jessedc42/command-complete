import json
from pathlib import Path
import tempfile
import unittest

import search_metadata as metadata


class MetadataImportTests(unittest.TestCase):
    def test_html_cleanup_preserves_words_without_tags_or_control_codes(self):
        self.assertEqual(metadata.clean_description('<p>Lists <b>network</b> interfaces &amp; addresses.</p><p>Details.</p>'),
                         'Lists network interfaces & addresses.')
        self.assertEqual(metadata.clean_description('<p>Do\x1b[31m not use\ncontrols.</p>'), 'Do not use controls.')

    def test_aws_model_imports_operations_members_shared_shapes_and_negative_boolean(self):
        commands = {'aws ec2': {}, 'aws ec2 describe-instances': {'flags': {
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


if __name__ == '__main__':
    unittest.main()
