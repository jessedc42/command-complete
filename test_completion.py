import unittest

from command_complete import Catalog, apply_match


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog({
            "commands": {
                "aws": {"flags": {"--profile": "value", "--output": "value"}},
                "aws ec2": {},
                "aws ec2 describe-instances": {"flags": {"--instance-ids": "many"}},
                "aws ec2 describe-images": {"flags": {"--image-ids": "many"}},
                "kubectl": {"flags": {"-n": "value", "--namespace": "value"},
                            "flag_hints": {"-n": "Namespace", "--namespace": "Namespace"}},
                "kubectl get": {"flags": {"-o": "value", "--output": "value"},
                                "words": ["pods", "deployments"]},
                "kubectl config": {},
                "kubectl config get-contexts": {},
                "kubectl apply": {
                    "flags": {"-f": "value", "--filename": "value", "-k": "value",
                              "--kustomize": "value", "--server-side": "switch", "--recursive": "switch"},
                    "flag_conflicts": [[["-f", "--filename"], ["-k", "--kustomize"]],
                                       [["--recursive"], ["-k", "--kustomize"]]],
                },
                "mkdir": {"arguments": ["Directory name"], "repeat_argument": "Directory name"},
                "nc": {
                    "flags": {"-w": "value", "-U": "switch", "-l": "switch", "-v": "switch",
                              "-z": "switch", "-p": "value", "-s": "value"},
                    "flag_hints": {"-w": "Timeout in seconds"},
                    "flag_conflicts": [[["-l"], [other]] for other in ("-z", "-p", "-s")],
                    "arguments": ["Host", "Port"],
                    "argument_modes": [["-U", ["Socket path"]], ["-l", ["Listen port or bind address"]]],
                    "short_options": True,
                },
                "ls": {"flags": {"-l": "unknown"}},
            },
            "values": {"kubectl get": {"--output": ["json", "yaml"], "-o": ["json", "yaml"]}},
        })

    def matches(self, line):
        return [match.text for match in self.catalog.matches(line)]

    def test_commands_and_nested_subcommands(self):
        self.assertEqual(self.matches("ku"), ["kubectl"])
        self.assertEqual(self.matches("kubectl config get-c"), ["get-contexts"])
        self.assertEqual(self.matches("ls -"), ["-l"])

    def test_flags_are_scoped_and_root_flags_inherited(self):
        self.assertEqual(self.matches("aws ec2 describe-instances --i"), ["--instance-ids"])
        self.assertEqual(self.matches("aws ec2 describe-images --i"), ["--image-ids"])
        self.assertEqual(self.matches("aws ec2 describe-images --p"), ["--profile"])

    def test_global_option_with_quoted_argument_before_subcommand(self):
        self.assertEqual(self.matches('kubectl -n "my team" ge'), ["get"])

    def test_a_positional_does_not_change_subcommand(self):
        self.assertEqual(self.matches("kubectl get config --ou"), ["--output"])

    def test_resource_and_static_flag_values(self):
        self.assertEqual(self.matches("kubectl get po"), ["pods"])
        self.assertEqual(self.matches("kubectl get pods -o j"), ["json"])
        self.assertEqual(self.matches("kubectl get pods --output=ya"), ["--output=yaml"])

    def test_list_flag_ends_at_next_flag(self):
        self.assertEqual(
            self.matches("aws ec2 describe-instances --instance-ids i-one i-two --p"),
            ["--profile"],
        )
        self.assertEqual(
            self.catalog.complete("aws ec2 describe-instances --instance-ids i-one i-two ").hint,
            "Value for --instance-ids",
        )

    def test_punctuation_and_incomplete_quotes_are_inert(self):
        self.assertEqual(self.matches("ls; ku"), [])
        self.assertEqual(self.matches('kubectl get "po'), [])
        self.assertEqual(self.matches("kubectl get -- --ou"), [])

    def test_selection_replaces_word_under_cursor_and_preserves_suffix(self):
        line = "kubectl ge-old pods"
        match, = self.catalog.matches(line, len("kubectl ge"))
        self.assertEqual(apply_match(line, match), ("kubectl get pods", len("kubectl get")))

    def test_unlisted_host_and_port_advance_on_space(self):
        for line, hint in (
            ("nc ", "Host"),
            ("nc unlisted.invalid", "Host"),
            ("nc unlisted.invalid ", "Port"),
            ("nc unlisted.invalid 15432", "Port"),
            ("nc unlisted.invalid 15432 ", None),
        ):
            with self.subTest(line=line):
                result = self.catalog.complete(line)
                self.assertEqual(result.hint, hint)
                self.assertEqual(result.matches, [])

    def test_values_and_combined_options_do_not_advance_the_positional_argument(self):
        self.assertEqual(self.catalog.complete("nc -w ").hint, "Timeout in seconds")
        self.assertEqual(self.catalog.complete("nc -w 3 ").hint, "Host")
        self.assertEqual(self.catalog.complete("nc -vw3 ").hint, "Host")
        self.assertEqual(self.catalog.complete("nc -lU ").hint, "Socket path")
        self.assertEqual(self.catalog.complete('nc -U "/tmp/my socket" ').hint, None)
        self.assertEqual(self.catalog.complete("nc -- ").hint, "Host")

    def test_free_form_option_value_resumes_subcommand_completion(self):
        self.assertEqual(self.catalog.complete("aws --profile any-name").hint, "Value for --profile")
        self.assertEqual(self.catalog.complete("aws --profile=any-name").hint, "Value for --profile")
        self.assertEqual(self.matches("aws --profile any-name e"), ["ec2"])

    def test_named_hints_are_inherited_and_support_equals(self):
        self.assertEqual(self.catalog.complete("kubectl get -n ").hint, "Namespace")
        self.assertEqual(self.catalog.complete("kubectl get --namespace=demo").hint, "Namespace")

    def test_documented_conflicts_are_symmetric_and_other_flags_remain(self):
        self.assertEqual(self.matches("nc -vl -"), ["-U", "-l", "-v", "-w"])
        self.assertNotIn("-l", self.matches("nc -z -"))
        self.assertIn("-s", self.matches("nc -p 8888 -"))

    def test_conflicts_cover_option_aliases_and_a_flag_after_the_cursor(self):
        self.assertEqual(self.matches("kubectl apply --filename=a.yaml --"),
                         ["--filename", "--namespace", "--recursive", "--server-side"])
        self.assertEqual(self.matches("kubectl apply -k manifests -f"), [])
        line = "kubectl apply --k -f a.yaml"
        self.assertEqual(self.catalog.matches(line, len("kubectl apply --k")), [])

    def test_explicitly_disabled_switch_does_not_exclude_a_conflicting_flag(self):
        self.assertEqual(self.matches("kubectl apply --recursive=false --ku"), ["--kustomize"])

    def test_repeatable_positionals_keep_their_label(self):
        self.assertEqual(self.catalog.complete("mkdir one two ").hint, "Directory name")

    def test_descriptions_follow_command_scope_and_are_never_inserted(self):
        self.catalog.commands["kubectl"]["flag_descriptions"] = {"--namespace": "Choose a namespace"}
        self.catalog.commands["kubectl get"]["flag_descriptions"] = {"--output": "Choose the output format"}
        match, = self.catalog.matches("kubectl get --out")
        self.assertEqual(match.description, "Choose the output format")
        self.assertEqual(apply_match("kubectl get --out", match)[0], "kubectl get --output ")
        inherited, = self.catalog.matches("kubectl get --names")
        self.assertEqual(inherited.description, "Choose a namespace")
        self.assertEqual(self.catalog.matches("ls -l")[0].description, "")


class MetadataTests(unittest.TestCase):
    def test_named_macos_flags_are_not_expanded_into_letters(self):
        from build_catalog import manual_options

        page = """SYNOPSIS
     utility [-listDataTypes] [-json] [-help] [-ab]
DESCRIPTION
     -listDataTypes  List data types.
     -json          Write JSON.
     -a             First switch.
     -b             Second switch.
"""
        self.assertEqual(set(manual_options(page)), {"-listDataTypes", "-json", "-help", "-a", "-b"})

    def test_manual_operand_sequences_advance_through_quoted_values(self):
        from build_catalog import manual_argument_hints

        hints = manual_argument_hints(
            "DESCRIPTION\n     -setmanual networkservice ip subnet router\n"
            "     -setdhcp networkservice [clientid]\n")
        flags = {"-setmanual": "value", "-setdhcp": "value", "-getinfo": "value"}
        catalog = Catalog({"commands": {"networksetup": {
            "flags": flags, "flag_arguments": hints,
            "flag_hints": {flag: labels[0] for flag, labels in hints.items()},
        }}})
        self.assertEqual(catalog.complete('networksetup -setmanual "Wi-Fi" ').hint, "IP address")
        self.assertEqual(catalog.complete('networksetup -setmanual "Wi-Fi" 192.0.2.1 ').hint, "Subnet mask")
        self.assertEqual(catalog.complete('networksetup -setmanual "Wi-Fi" 192.0.2.1 255.255.255.0 ').hint,
                         "Router address")
        self.assertIn("-getinfo", [m.text for m in catalog.matches('networksetup -setdhcp "Wi-Fi" -get')])

    def syntax_catalog(self):
        from build_catalog import add_syntax_examples

        commands = {
            "aws": {"flags": {"--query": "value", "--profile": "value"}},
            "aws ec2": {},
            "aws ec2 describe-instances": {},
            "awk": {"flags": {}}, "sed": {"flags": {"-n": "switch"}},
        }
        add_syntax_examples(commands)
        return Catalog({"commands": commands})

    def test_query_examples_use_response_fields_and_survive_unfinished_quotes(self):
        catalog = self.syntax_catalog()
        for suffix in ("--query", "--query ", "--query '", "--query 'Reservations[].", '--query="Reservations[]'):
            with self.subTest(suffix=suffix):
                result = catalog.complete("aws ec2 describe-instances " + suffix)
                self.assertIn("InstanceId", " ".join(result.examples))
        self.assertEqual(catalog.complete("aws ec2 describe-instances --profile ").examples, ())
        self.assertEqual(catalog.complete("aws ec2 describe-instances --query 'Reservations[]' ").examples, ())

    def test_program_examples_yield_to_input_files_and_option_values(self):
        catalog = self.syntax_catalog()
        self.assertTrue(catalog.complete('awk -F : ').examples)
        self.assertTrue(catalog.complete('awk -F : "{ print ').examples)
        self.assertFalse(catalog.complete("awk -F ").examples)
        self.assertFalse(catalog.complete("awk -f script.awk ").examples)
        self.assertFalse(catalog.complete("awk '{print $1}' ").examples)
        self.assertTrue(catalog.complete("sed -n -e '").examples)
        self.assertFalse(catalog.complete("sed -e 's/old/new/' ").examples)
        self.assertFalse(catalog.complete("sed -f script.sed ").examples)

    def test_flag_descriptions_read_aliases_and_stop_at_the_next_entry(self):
        from build_catalog import flag_descriptions

        page = """OPTIONS
     -q, --quiet  Suppress output.
             Additional details.

     -o FILE
             Write output to FILE.
     --other
             Other option.
"""
        self.assertEqual(flag_descriptions(page, {"-q": "switch", "--quiet": "switch", "-o": "value"}), {
            "-q": "Suppress output.", "--quiet": "Suppress output.", "-o": "Write output to FILE.",
        })

    def test_option_entries_provide_labels_outside_the_synopsis(self):
        from build_catalog import manual_value_hints

        page = """SYNOPSIS
     nc [host] [port]
DESCRIPTION
     -L num_probes
             Number of probes sent before declaring the peer unreachable.
     -n      Do not look up hosts.
     -o, --output=FILE  Write to this file.
     --color[=WHEN]    Enable color.
EXAMPLES
     -x example
"""
        self.assertEqual(manual_value_hints(page), {
            "-L": "Number of probes", "-o": "File", "--output": "File",
            "--color": "When (optional)",
        })

    def test_documentation_imports_simple_options_and_repeating_arguments(self):
        from build_catalog import usage_metadata

        page = "SYNOPSIS\n     mkdir [-pv] [-m mode] directory_name ...\n\nDESCRIPTION\n"
        self.assertEqual(usage_metadata(page, "mkdir"), {
            "arguments": ["Directory name"],
            "repeat_argument": "Directory name",
            "flag_hints": {"-m": "Mode"},
        })

    def test_documentation_import_ignores_alternate_positional_forms(self):
        from build_catalog import usage_metadata

        page = "SYNOPSIS\n     tool file\n     tool source target\n\nDESCRIPTION\n"
        self.assertEqual(usage_metadata(page, "tool"), {})

    def test_help_import_understands_explicit_placeholders(self):
        from build_catalog import usage_metadata

        help_text = "Usage:\n  kubectl create namespace NAME [options]\n\n"
        self.assertEqual(usage_metadata(help_text, "kubectl create namespace", "Usage:"),
                         {"arguments": ["Name"]})

    def test_kubectl_help_filters_plugin_rows_and_reads_flag_types(self):
        from build_catalog import kube_help

        help_text = """Basic Commands (Beginner):
  create       Create a resource
Subcommands provided by plugins:
  unknown      Plugin
Options:
    -A, --all-namespaces=false:
        List all namespaces
    -o, --output='':
        Select a format
Aliases:
get, list
"""
        self.assertEqual(kube_help(help_text),
                         (["create"], ["list"],
                          {"-A": "switch", "--all-namespaces": "switch",
                           "-o": "value", "--output": "value"}))

    def test_manual_flags_expand_short_groups_and_ignore_examples(self):
        from build_catalog import manual_options

        page = """SYNOPSIS
     utility [-al] [--color=when] [arg ...]
DESCRIPTION
     -s, --silent     Keep quiet
EXAMPLES
     utility --invented
"""
        self.assertEqual(set(manual_options(page)), {"-a", "-l", "--color", "-s", "--silent"})
