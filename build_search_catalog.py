#!/usr/bin/env python3
"""Import local documentation and build the complete offline search databases."""

import argparse
from collections import Counter
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import time

import build_catalog as completion_builder
from command_complete import Catalog
from command_search_index import DatabaseSearchIndex, write_database
from search_metadata import (aws_help_descriptions, aws_help_positionals, build_metadata, clean_description,
                             import_aws_models, manual_summary)


ROOT = Path(__file__).resolve().parent
COMMON_AWS = {'--cli-input-json', '--cli-input-yaml', '--generate-cli-skeleton',
              '--starting-token', '--max-items', '--page-size'}


def read_json(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8') as source:
        return json.load(source)


def write_json(path, data):
    temporary = path.with_suffix(path.suffix + '.building')
    with temporary.open('wb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as compressed:
        compressed.write(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode())
    temporary.replace(path)


def description_section(content):
    match = re.search(r'(?m)^DESCRIPTION\s*\n(.*?)(?=^[A-Z][A-Z /-]+\s*$|\Z)', content, re.S)
    if not match:
        return ''
    first = re.split(r'\n\s*\n', match[1].strip(), maxsplit=1)[0]
    return clean_description(first)


def merge_documentation(commands, documented):
    for name in commands.keys() & documented.keys():
        target, source = commands[name], documented[name]
        if source.get('description'):
            target['description'] = clean_description(source['description'])
        if source.get('documentation_source'):
            target['documentation_source'] = source['documentation_source']
        if source.get('command_group'):
            target['command_group'] = True
        positionals = source.get('positionals', source.get('documented_positionals', ()))
        if positionals:
            target['documented_positionals'] = list(positionals)
        for positional in positionals:
            flag = '--' + positional['name']
            target.get('flags', {}).pop(flag, None)
            for field in ('flag_hints', 'flag_arguments', 'flag_descriptions', 'flag_sources'):
                target.get(field, {}).pop(flag, None)
            arguments = target.setdefault('arguments', [])
            if not (positional['name'] in ('path', 'paths') and arguments) and positional['label'] not in arguments:
                arguments.append(positional['label'])
            if positional['name'] == 'outfile':
                target['documented_effect'] = 'set'
        for field in ('flag_conflicts', 'repeatable_flags'):
            if source.get(field):
                for value in source[field]:
                    if value not in target.setdefault(field, []):
                        target[field].append(value)
        for flag in target.get('flags', {}):
            if text := source.get('flag_descriptions', {}).get(flag):
                target.setdefault('flag_descriptions', {})[flag] = clean_description(text)
                target.setdefault('flag_sources', {})[flag] = source.get('documentation_source', 'installed documentation')
            for field in ('flag_hints', 'flag_arguments'):
                if flag in source.get(field, {}):
                    target.setdefault(field, {}).setdefault(flag, source[field][flag])


def import_ubuntu_manuals(commands, reference):
    manuals = reference.get('manuals', {})
    count = 0
    for name, entry in commands.items():
        content = manuals.get(name) or manuals.get(name.replace(' ', '-'))
        if not content:
            continue
        content = re.sub(r'.\x08', '', content)
        content = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', content)
        source = {'description': manual_summary(content), 'documentation_source': 'Ubuntu man:' + name,
                  'flag_descriptions': completion_builder.flag_descriptions(content, entry.get('flags', {}))}
        merge_documentation(commands, {name: source})
        count += 1
    return count


def import_cli_help(commands, aws, cache, errors):
    if not aws:
        return 0
    env = dict(os.environ, AWS_PAGER='', PAGER='cat', MANPAGER='cat', LC_ALL='C',
               AWS_EC2_METADATA_DISABLED='true', AWS_CONFIG_FILE=os.devnull,
               AWS_SHARED_CREDENTIALS_FILE=os.devnull, AWS_CLI_AUTO_PROMPT='off')
    cache.mkdir(parents=True, exist_ok=True)
    version = completion_builder.capture(aws, '--version').split()[0]

    def capture(name):
        key = hashlib.sha256(('format2:' + version + ':' + name).encode()).hexdigest()
        cached = cache / (key + '.json')
        if cached.exists():
            return name, read_json(cached), None
        try:
            raw = completion_builder.capture(aws, *name.split()[1:], 'help', env=env)
            raw = re.sub(r'.\x08', '', raw)
            flags = set(commands[name].get('flags', {})) | COMMON_AWS
            description = manual_summary(raw) or description_section(raw)
            descriptions = aws_help_descriptions(raw, flags)
            documented = {'description': description, 'documentation_source': version + ' local help',
                          'flag_descriptions': descriptions, 'positionals': aws_help_positionals(raw)}
            if 'AVAILABLE COMMANDS' in raw:
                documented['command_group'] = True
            cached.write_text(json.dumps(documented), encoding='utf-8')
            return name, documented, None
        except (OSError, subprocess.SubprocessError) as error:
            return name, {}, type(error).__name__

    common = {}
    if 'aws ec2 describe-instances' in commands:
        name, data, error = capture('aws ec2 describe-instances')
        if error:
            errors.append({'source': name, 'reason': error})
        else:
            merge_documentation(commands, {name: data})
            common = {flag: text for flag, text in data.get('flag_descriptions', {}).items() if flag in COMMON_AWS}
    for name, entry in commands.items():
        if name != 'aws' and not name.startswith('aws '):
            continue
        for flag in entry.get('flags', {}):
            if flag in common:
                entry.setdefault('flag_descriptions', {}).setdefault(flag, common[flag])
                entry.setdefault('flag_sources', {}).setdefault(flag, version + ' built-in argument help')
        if '--cli-input-json' in entry.get('flags', {}) and '--cli-input-yaml' in entry.get('flags', {}):
            pair = [['--cli-input-json'], ['--cli-input-yaml']]
            if pair not in entry.setdefault('flag_conflicts', []):
                entry['flag_conflicts'].append(pair)
    targets = [name for name, entry in commands.items() if name.startswith('aws ') and
               (not entry.get('description') or any(not entry.get('flag_descriptions', {}).get(flag)
                                                  for flag in entry.get('flags', {})))]
    print(f'Reading {len(targets)} AWS help topics for remaining documentation gaps...', flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for number, (name, data, error) in enumerate(pool.map(capture, targets), 1):
            if error:
                errors.append({'source': name, 'reason': error})
            else:
                merge_documentation(commands, {name: data})
            if number % 100 == 0:
                print(f'  {number}/{len(targets)} AWS topics processed', flush=True)
    return len(targets)


def import_rclone_flags(commands, errors):
    executable = shutil.which('rclone')
    if not executable or 'rclone' not in commands:
        return
    env = {key: value for key, value in os.environ.items() if key in ('PATH', 'HOME', 'TMPDIR', 'LANG')}
    env.update(LC_ALL='C', RCLONE_CONFIG=os.devnull)
    try:
        text = completion_builder.capture(executable, 'help', 'flags', env=env)
        descriptions = completion_builder.flag_descriptions(text, commands['rclone'].get('flags', {}))
        merge_documentation(commands, {'rclone': {'flag_descriptions': descriptions,
                                               'documentation_source': 'rclone local flag help'}})
    except (OSError, subprocess.SubprocessError) as error:
        errors.append({'source': 'rclone flag help', 'reason': type(error).__name__})


def add_builtin_descriptions(commands):
    for name, entry in commands.items():
        for flag in entry.get('flags', {}):
            if (flag == '--help' or (flag == '-h' and name.split()[0] in ('docker', 'kubectl'))
                    or (flag == '-help' and name.split()[0] == 'terraform')):
                entry.setdefault('flag_descriptions', {}).setdefault(flag, 'Show command help and exit.')
                entry.setdefault('flag_sources', {}).setdefault(flag, 'documented CLI help convention')
            elif flag == '--version':
                entry.setdefault('flag_descriptions', {}).setdefault(flag, 'Show the program version and exit.')
                entry.setdefault('flag_sources', {}).setdefault(flag, 'documented CLI version convention')
        for flag, text in entry.get('flag_descriptions', {}).items():
            entry['flag_descriptions'][flag] = text.replace(str(Path.home()), '~')


def register_own_commands(commands):
    common = {'--matches': 'switch', '--help': 'switch', '--version': 'switch'}
    commands['command-complete'] = dict(commands.get('command-complete', {}),
        description='Draft UNIX commands with live autocomplete and argument hints.',
        documentation_source='project command-complete CLI help', documented_effect='get', flags=dict(common),
        arguments=['Initial draft (optional)'],
        flag_descriptions={'--matches': 'Print completion candidates and exit.', '--help': 'Show command help and exit.',
                           '--version': 'Show the program version and exit.'})
    commands['command-search'] = {
        'description': 'Search UNIX commands by task keywords, then compose an unexecuted draft.',
        'documentation_source': 'project command-search CLI help', 'documented_effect': 'get',
        'flags': common | {'--catalog': 'value', '--database': 'value'},
        'arguments': ['Task keywords (optional)'], 'repeat_argument': 'Task keyword',
        'flag_hints': {'--catalog': 'Completion catalog file', '--database': 'Search database file'},
        'flag_descriptions': {'--matches': 'Print ranked search matches and exit.', '--help': 'Show command help and exit.',
                              '--version': 'Show the program version and exit.',
                              '--catalog': 'Use a specific platform completion catalog.',
                              '--database': 'Use a specific offline search database.'}}
    commands.setdefault('cs', {'alias': 'command-search'})


def build_platform(platform, data, overrides, output_dir, source_errors):
    commands = data['commands']
    register_own_commands(commands)
    add_builtin_descriptions(commands)
    metadata = build_metadata(commands, overrides)
    # Both utilities receive imported descriptions, including curated corrections.
    for name, meta in metadata['commands'].items():
        if meta['description']:
            commands[name]['description'] = meta['description']
        for flag, value in meta['flags'].items():
            if value['description']:
                commands[name].setdefault('flag_descriptions', {})[flag] = value['description']
    catalog_name = 'catalog.json.gz' if platform == 'macos' else 'catalog-ubuntu.json.gz'
    catalog_file = output_dir / catalog_name
    write_json(catalog_file, data)
    database = output_dir / f'search-{platform}.db'
    print(f'Building complete {platform} search database...', flush=True)
    started = time.perf_counter()
    count = write_database(database, Catalog(data), metadata)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute('INSERT INTO info VALUES (?,?)', ('catalog_sha256', hashlib.sha256(catalog_file.read_bytes()).hexdigest()))
        connection.execute('INSERT INTO info VALUES (?,?)', ('platform', platform))
        connection.commit()
    compressed = database.with_suffix('.db.gz')
    with database.open('rb') as source, compressed.open('wb') as raw:
        with gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0, compresslevel=6) as destination:
            shutil.copyfileobj(source, destination)
    report = metadata['report']
    report.update(platform=platform, indexed_entries=count, source_errors=source_errors,
                  source_versions=data.get('sources', {}), build_seconds=round(time.perf_counter() - started, 3))
    index = DatabaseSearchIndex(database, Catalog(data))
    measurements = {}
    for query in ('network reachability dog', 'get disk space', 'get inspect instances'):
        start = time.perf_counter()
        result = index.search(query)
        # Materialize only a visible page; every remaining result stays accessible.
        result.results[:20]
        measurements[query] = {'matches': len(result.results), 'milliseconds': round((time.perf_counter() - start) * 1000, 2)}
    index.close()
    report['query_measurements'] = measurements
    write_json(output_dir / f'search-coverage-{platform}.json.gz', report)
    database.unlink()
    print(f'{platform}: {count:,} forms; {report["commands_described"]:,}/{report["commands"]:,} command descriptions; '
          f'{report["flags_described"]:,}/{report["flags"]:,} stored flag descriptions.', flush=True)
    return report


def write_coverage(reports, output_dir):
    lines = ['# Command-search documentation coverage', '',
             'All catalog commands and scoped flags are indexed, including inherited options. '
             'Description counts below refer to stored command/flag records before inherited expansion.', '',
             '| Platform | Search forms | Command descriptions | Stored flag descriptions |',
             '| --- | ---: | ---: | ---: |']
    for report in reports:
        lines.append(f'| {report["platform"]} | {report["indexed_entries"]:,} | '
                     f'{report["commands_described"]:,} / {report["commands"]:,} | '
                     f'{report["flags_described"]:,} / {report["flags"]:,} |')
    for report in reports:
        lines += ['', '## ' + report['platform'], '',
                  'Effect classifications: ' + ', '.join(f'{key}: {value:,}' for key, value in sorted(report['effects'].items())) + '.', '',
                  f'Detailed gaps and source outcomes: `search-coverage-{report["platform"]}.json.gz`.', '',
                  'Measured query times (including the first visible page):', '']
        for query, measurement in report['query_measurements'].items():
            lines.append(f'- `{query}`: {measurement["milliseconds"]} ms; {measurement["matches"]:,} matches.')
        lines += ['', 'Largest remaining description gaps (review the detailed report for individual entries):', '']
        counts = Counter(item['command'] for item in report['missing_descriptions'])
        for command, count in counts.most_common(20):
            lines.append(f'- `{command}`: {count} missing descriptions.')
    (output_dir / 'search-coverage.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', choices=('macos', 'ubuntu', 'both'), default='both')
    parser.add_argument('--aws-models', type=Path)
    parser.add_argument('--ubuntu-reference', type=Path, default=ROOT / 'ubuntu-command-reference.json')
    parser.add_argument('--output-dir', type=Path, default=ROOT)
    parser.add_argument('--source-cache', type=Path, default=ROOT / '.superpowers/source-cache')
    args = parser.parse_args()
    try:
        overrides = read_json(ROOT / 'search_overrides.json')
        args.output_dir.mkdir(parents=True, exist_ok=True)
        platforms = ('macos', 'ubuntu') if args.platform == 'both' else (args.platform,)
        datasets = {platform: read_json(ROOT / ('catalog.json.gz' if platform == 'macos' else 'catalog-ubuntu.json.gz'))
                    for platform in platforms}
        aws = shutil.which('aws')
        models = args.aws_models or (Path(aws).resolve().parent / 'awscli/botocore/data' if aws else None)
        errors = []
        portable = next(iter(datasets.values()))['commands']
        if models and models.is_dir():
            print('Importing installed AWS service models...', flush=True)
            imported = import_aws_models(portable, models)
            print(f'Imported {imported:,} AWS operation/parameter description fields.', flush=True)
        else:
            errors.append({'source': 'AWS models', 'reason': 'optional local source unavailable; retaining bundled documentation'})
        import_cli_help(portable, aws, args.source_cache / 'aws', errors)
        import_rclone_flags(portable, errors)
        for cli, importer in (('docker', completion_builder.add_docker), ('kubectl', completion_builder.add_kubectl),
                              ('terraform', completion_builder.add_terraform)):
            executable = shutil.which(cli)
            if executable:
                print(f'Reading installed {cli} client help...', flush=True)
                documented = {}
                try:
                    importer(documented, executable)
                    merge_documentation(portable, documented)
                except (OSError, subprocess.SubprocessError) as error:
                    errors.append({'source': cli + ' help', 'reason': type(error).__name__})
            else:
                errors.append({'source': cli + ' help', 'reason': 'optional client unavailable; retaining bundled documentation'})
        reports = []
        for platform, data in datasets.items():
            commands = data['commands']
            if commands is not portable:
                merge_documentation(commands, {name: entry for name, entry in portable.items()
                    if name.split()[0] in ('aws', 'docker', 'kubectl', 'terraform', 'rclone')})
            if platform == 'macos' and os.uname().sysname == 'Darwin':
                print('Reading installed macOS manuals...', flush=True)
                documented = {name: {} for name in commands if ' ' not in name}
                completion_builder.add_manuals(documented)
                merge_documentation(commands, documented)
            elif platform == 'ubuntu' and args.ubuntu_reference.exists():
                print('Importing collected Ubuntu manuals...', flush=True)
                import_ubuntu_manuals(commands, read_json(args.ubuntu_reference))
            else:
                errors.append({'source': platform + ' manuals', 'reason': 'local reference unavailable; retaining bundled documentation'})
            reports.append(build_platform(platform, data, overrides, args.output_dir, list(errors)))
        write_coverage(reports, args.output_dir)
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f'build_search_catalog: {error}\n')


if __name__ == '__main__':
    main()
