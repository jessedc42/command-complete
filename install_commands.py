#!/usr/bin/env python3
"""Install command-complete, command-search and cs without replacing other tools."""

import argparse
from pathlib import Path
import shlex


def install(directory):
    directory = Path(directory).expanduser().absolute()
    root = Path(__file__).resolve().parent
    targets = {'command-complete': root / 'command_complete.py',
               'command-search': root / 'command_search.py', 'cs': root / 'command_search.py'}
    for name, target in targets.items():
        link = directory / name
        if link.is_symlink() and link.resolve() == target:
            continue
        if link.exists() or link.is_symlink():
            raise ValueError(f'{link} already exists; use another --bin-dir to preserve it.')
    directory.mkdir(parents=True, exist_ok=True)
    for name, target in targets.items():
        link = directory / name
        if not link.is_symlink():
            link.symlink_to(target)
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bin-dir', type=Path, default=Path.home() / '.local/bin')
    args = parser.parse_args()
    try:
        root = install(args.bin_dir)
    except (OSError, ValueError) as error:
        parser.exit(1, f'install_commands: {error}\n')
    print(f'Installed command-complete, command-search and cs in {args.bin_dir}.')
    print('Load the shell shortcuts with:')
    print('source ' + shlex.quote(str(root / 'shell-integration.sh')))


if __name__ == '__main__':
    main()
