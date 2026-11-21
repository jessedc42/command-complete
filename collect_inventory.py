#!/usr/bin/env python3
"""Print OS details and the executables available on this process's PATH as JSON."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manuals", action="store_true", help="include installed command manuals")
    args = parser.parse_args()
    distro = {}
    release_file = Path("/etc/os-release")
    if release_file.exists():
        for line in release_file.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and not key.startswith("#"):
                parts = shlex.split(value)
                distro[key] = parts[0] if parts else ""

    commands = {}
    errors = []
    path = list(dict.fromkeys(os.get_exec_path()))
    for directory in path:
        try:
            with os.scandir(directory or ".") as entries:
                for entry in entries:
                    try:
                        if entry.is_file() and os.access(entry.path, os.X_OK):
                            location = os.path.abspath(entry.path)
                            commands.setdefault(entry.name, []).append({
                                "path": location,
                                "resolved_path": os.path.realpath(location),
                            })
                    except OSError as error:
                        errors.append({"path": entry.path, "error": str(error)})
        except OSError as error:
            errors.append({"path": directory, "error": str(error)})

    inventory = {
        "schema_version": 1,
        "system": platform.system(),
        "architecture": platform.machine(),
        "kernel_release": platform.release(),
        "distribution": distro,
        "path": path,
        "commands": dict(sorted(commands.items())),
        "errors": errors,
    }
    if args.manuals:
        man = shutil.which("man")
        if not man:
            parser.error("man is required for --manuals")
        env = dict(os.environ, LC_ALL="C", MANWIDTH="160", MANPAGER="cat",
                   PAGER="cat", MANOPT="", GROFF_NO_SGR="1")

        def read_manual(name):
            try:
                result = subprocess.run(
                    [man, "-P", "cat", "-s", "1:8:6", "--", name],
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, errors="replace", timeout=15, env=env,
                )
                return name, result.stdout if result.returncode == 0 else ""
            except subprocess.TimeoutExpired:
                return name, ""

        print("Collecting installed manuals...", file=sys.stderr)
        with ThreadPoolExecutor(max_workers=4) as pool:
            inventory["manuals"] = {name: text for name, text in pool.map(read_manual, sorted(commands))
                                    if text}
        print(f"Collected {len(inventory['manuals'])} manuals.", file=sys.stderr)
    json.dump(inventory, sys.stdout, indent=2, ensure_ascii=True)
    print()


if __name__ == "__main__":
    main()
