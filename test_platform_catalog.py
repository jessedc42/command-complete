import unittest
import gzip
import json

from build_catalog import build_ubuntu_catalog
from command_complete import Catalog, DATABASE, UBUNTU_DATABASE, catalog_path


class PlatformCatalogTests(unittest.TestCase):
    def test_os_selects_the_matching_catalog(self):
        self.assertEqual(catalog_path("Darwin"), DATABASE)
        self.assertEqual(catalog_path("Linux", {"ID": "ubuntu", "VERSION_ID": "24.04"}), UBUNTU_DATABASE)
        with self.assertRaises(ValueError):
            catalog_path("Linux", {"ID": "fedora", "VERSION_ID": "41"})
        with self.assertRaises(ValueError):
            catalog_path("Linux", {"ID": "ubuntu", "VERSION_ID": "22.04"})

    def test_ubuntu_uses_its_manuals_and_keeps_optional_portable_clis(self):
        inventory = {
            "system": "Linux",
            "distribution": {"ID": "ubuntu", "VERSION_ID": "24.04"},
            "commands": {"ls": [], "apt": []},
            "manuals": {"ls": """SYNOPSIS
       ls [OPTION]... [FILE]...
DESCRIPTION
       -a, --all
              Do not ignore entries starting with a dot.
"""},
        }
        portable = {"commands": {
            "aws": {"flags": {"--query": "value"}},
            "aws ec2": {}, "aws ec2 describe-instances": {},
            "kubectl": {"flags": {}}, "kubectl get": {},
            "networksetup": {"flags": {"-getinfo": "value"}},
            "ls": {"flags": {"-@": "switch"}},
        }}
        result = build_ubuntu_catalog(inventory, portable)
        catalog = Catalog(result)
        names = result["commands"]
        self.assertIn("apt", names)
        self.assertIn("aws", names)
        self.assertIn("kubectl", names)
        self.assertNotIn("networksetup", names)
        self.assertEqual([m.text for m in catalog.matches("ls --a")], ["--all"])
        self.assertEqual(catalog.matches("ls -@"), [])
        self.assertTrue(catalog.matches("ls --a")[0].description)
        self.assertTrue(catalog.complete("aws ec2 describe-instances --query ").examples)
        self.assertFalse(names["apt"].get("flag_descriptions"))

    def test_bundled_ubuntu_catalog_keeps_gnu_and_netcat_variants_separate(self):
        with gzip.open(UBUNTU_DATABASE, "rt", encoding="utf-8") as source:
            data = json.load(source)
        catalog = Catalog(data)
        self.assertGreater(data["sources"]["manual_count"], 0)
        self.assertNotIn("networksetup", data["commands"])
        self.assertNotIn("system_profiler", data["commands"])
        self.assertEqual(catalog.matches("ls -@"), [])
        self.assertEqual([m.text for m in catalog.matches("ls --block-si")], ["--block-size"])
        self.assertTrue(catalog.matches("sed --quiet")[0].description)
        self.assertTrue(catalog.complete("sed --expression 's/").examples)
        self.assertEqual(catalog.matches("nc -L"), [])
        self.assertIn("-p", [m.text for m in catalog.matches("nc -l -")])
        self.assertNotIn("-z", [m.text for m in catalog.matches("nc -l -")])
        self.assertIn("install", [m.text for m in catalog.matches("apt ")])
        self.assertIsNone(catalog.complete("ls --help ").hint)

