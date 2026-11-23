"""Import documentation and assemble offline, source-attributed search metadata."""

from collections import Counter
import gzip
from html.parser import HTMLParser
import json
from pathlib import Path
import re


STOP_WORDS = set(('a an and are as at be been being by can could do does for from has have '
                  'if in into is it its may must of on or should specify specifies specified '
                  'that the their then there these this those to use used using was were '
                  'when which will with you your').split())
READ_VERBS = {'describe', 'describes', 'display', 'displays', 'list', 'lists', 'retrieve', 'retrieves',
              'show', 'shows', 'print', 'prints', 'read', 'reads', 'inspect', 'inspects',
              'fetch', 'fetches', 'report', 'reports'}
WRITE_VERBS = {'create', 'creates', 'delete', 'deletes', 'remove', 'removes', 'update', 'updates',
               'modify', 'modifies', 'change', 'changes', 'set', 'sets', 'stop', 'stops',
               'start', 'starts', 'enable', 'enables', 'disable', 'disables', 'add', 'adds',
               'attach', 'attaches', 'detach', 'detaches', 'associate', 'associates',
               'disassociate', 'disassociates', 'reboot', 'reboots', 'terminate', 'terminates'}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ('p', 'br', 'li', 'div'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('p', 'li', 'div'):
            self.parts.append('\n')

    def handle_data(self, data):
        self.parts.append(re.sub(r'\s+', ' ', data))


def plain_text(text):
    parser = _Text()
    parser.feed(re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text or ''))
    return ''.join(parser.parts)


def clean_description(text, limit=200):
    """Use the first prose paragraph; keep terminal controls and HTML out."""
    paragraphs = [re.sub(r'\s+', ' ', p).strip() for p in plain_text(text).split('\n')]
    result = next((p for p in paragraphs if p), '')
    result = ''.join(c for c in result if c.isprintable())
    if len(result) > limit:
        result = result[:limit - 3].rsplit(' ', 1)[0] + '...'
    return result


def tokens(text):
    return set(re.findall(r'[^\W_]+', text.casefold(), re.UNICODE))


def purpose_terms(text):
    words = {word for word in tokens(text) - STOP_WORDS if len(word) > 1}
    vocabulary = {
        'icmp': 'network ping probe reachability reachable test connectivity',
        'reachability': 'reachable connectivity network test',
        'network': 'networking connectivity', 'describes': 'describe inspect details information',
        'describe': 'inspect details information', 'display': 'show view inspect',
        'displays': 'display show view inspect', 'lists': 'list show view inspect',
        'retrieve': 'read fetch inspect', 'retrieves': 'read fetch inspect',
        'deletes': 'delete remove erase', 'removes': 'remove delete',
        'creates': 'create add', 'updates': 'update change modify',
        'filesystem': 'filesystems storage', 'directory': 'directories folder',
        'directories': 'directory folders', 'containers': 'container docker',
        'container': 'containers docker', 'instances': 'instance',
        'statistics': 'stats metrics', 'memory': 'ram', 'processes': 'process',
    }
    for word in tuple(words):
        words.update(vocabulary.get(word, '').split())
    return sorted(words)


def cli_name(name):
    name = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1-\2', name)
    return re.sub(r'([a-z0-9])([A-Z])', r'\1-\2', name).replace('_', '-').lower()


def field_label(name):
    label = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', name)
    label = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', label).replace('_', ' ')
    acronyms = {'id': 'ID', 'ids': 'IDs', 'arn': 'ARN', 'arns': 'ARNs', 'vpc': 'VPC', 'ip': 'IP',
                'ec2': 'EC2', 'dns': 'DNS', 'ttl': 'TTL', 'url': 'URL', 'uri': 'URI', 'cpu': 'CPU'}
    return ' '.join(acronyms.get(word.lower(), word) for word in label.split())


def manual_summary(content):
    match = re.search(r'(?m)^NAME\s*\n(.*?)(?=^[A-Z][A-Z /-]+\s*$|\Z)', content, re.S)
    if not match:
        return ''
    text = re.sub(r'\s+', ' ', match[1]).strip()
    parts = re.split(r'\s+[—–−-]\s+', text, maxsplit=1)
    return clean_description(parts[1]) if len(parts) == 2 else ''


def help_summary(content):
    sections = re.split(r'\n\s*\n', content.strip())
    for section in sections:
        value = section.strip()
        if value and not value.startswith(('Usage:', 'Options:', 'Flags:', 'Available Commands:',
                                             'Global Options:', 'Aliases:', 'Examples:')):
            if not re.match(r'^\s*(?:-|docker |kubectl )', value):
                return clean_description(value)
    return ''


def aws_help_descriptions(content, flags):
    """AWS man output allows inline prose and continuation at the same indent."""
    descriptions, current, body = {}, [], []
    section = ''

    def finish():
        text = clean_description(' '.join(body))
        if text:
            for flag in current:
                descriptions[flag] = text

    for line in content.splitlines():
        if re.fullmatch(r'[A-Z][A-Z /-]*', line.strip()) and not line.startswith(' '):
            finish()
            current, body = [], []
            section = line.strip()
            continue
        if section not in ('OPTIONS', 'GLOBAL OPTIONS'):
            continue
        match = re.match(r'^\s+(--[\w-]+(?:\s*[|,]\s*--[\w-]+)*)\s+\([^)]*\)(?:\s+(.*))?$', line)
        if match:
            finish()
            current = [flag for flag in re.findall(r'--[\w-]+', match[1]) if flag in flags]
            body = [match[2]] if match[2] else []
        elif current:
            if not line.strip() and body:
                finish()
                current, body = [], []
            elif line.strip():
                body.append(line.strip())
    finish()
    return descriptions


def aws_help_positionals(content):
    active = False
    headers = []
    for line in content.splitlines():
        if line == 'OPTIONS':
            active = True
            continue
        if active and line and not line[0].isspace() and line.isupper():
            break
        if active:
            match = re.match(r'^( +)(--?[\w-]+|[a-z][\w-]*)\s+\([^)]*\)(.*)$', line)
            if match:
                headers.append((len(match[1]), match[2], match[3]))
    if not headers:
        return []
    indent = min(row[0] for row in headers)
    return [{'name': name, 'label': 'Output file' if name == 'outfile' else field_label(name).capitalize(),
             'required': '[required]' in tail}
            for level, name, tail in headers if level == indent and not name.startswith('-')]


def _read_json(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8') as source:
        return json.load(source)


def import_aws_models(commands, model_directory):
    """Read installed AWS JSON models as data, without importing an AWS SDK."""
    count = 0
    cli = Path(model_directory).parent.parent / 'data' / 'cli.json'
    if cli.exists() and 'aws' in commands:
        document = _read_json(cli)
        commands['aws'].update(description=clean_description(document.get('description', '')),
                               command_group=True, documentation_source='AWS CLI cli.json')
        for name, data in document.get('options', {}).items():
            flag = '--' + name
            text = clean_description(data.get('help', ''))
            if text and flag in commands['aws'].get('flags', {}):
                commands['aws'].setdefault('flag_descriptions', {})[flag] = text
                commands['aws'].setdefault('flag_sources', {})[flag] = 'AWS CLI cli.json'
    for service in sorted(Path(model_directory).iterdir()):
        if not service.is_dir():
            continue
        candidates = sorted(service.glob('*/service-2.json*'))
        if not candidates:
            continue
        path = candidates[-1]
        model = _read_json(path)
        service_names = [service.name] + (['s3api'] if service.name == 's3' else [])
        for service_name in service_names:
            root = f'aws {service_name}'
            if root not in commands:
                continue
            source = f'AWS {service.name} model {path.parent.name}'
            commands[root].update(description=clean_description(model.get('metadata', {}).get('serviceFullName', service.name)),
                                  documentation_source=source, command_group=True)
            operations = model.get('operations', {})
            shapes = model.get('shapes', {})

            def import_operation(name, operation, description=None):
                nonlocal count
                if name not in commands:
                    return
                entry = commands[name]
                prose = clean_description(description or operation.get('documentation', ''))
                if prose:
                    entry['description'] = prose
                    entry['documentation_source'] = source
                    count += 1
                members = shapes.get(operation.get('input', {}).get('shape'), {}).get('members', {})
                by_flag = {cli_name(member): spec for member, spec in members.items()}
                labels = {cli_name(member): field_label(member) for member in members}
                for flag in entry.get('flags', {}):
                    base = flag.removeprefix('--')
                    negative = base.startswith('no-') and base[3:] in by_flag
                    member = by_flag.get(base[3:] if negative else base)
                    if member is None:
                        continue
                    if entry['flags'][flag] in ('value', 'many', 'attached', 'optional'):
                        entry.setdefault('flag_hints', {}).setdefault(flag, labels[base[3:] if negative else base])
                    text = clean_description(member.get('documentation') or
                                             shapes.get(member.get('shape'), {}).get('documentation', ''))
                    if text:
                        entry.setdefault('flag_descriptions', {})[flag] = ('Disable: ' if negative else '') + text
                        entry.setdefault('flag_sources', {})[flag] = source
                        count += 1

            for operation_name, operation in operations.items():
                import_operation(f'{root} {cli_name(operation_name)}', operation)
            waiters = sorted(service.glob('*/waiters-2.json*'))
            if waiters:
                if root + ' wait' in commands:
                    commands[root + ' wait'].update(description='Wait for a documented resource state.',
                        command_group=True, documentation_source=source)
                for waiter_name, waiter in _read_json(waiters[-1]).get('waiters', {}).items():
                    operation = operations.get(waiter.get('operation'), {})
                    import_operation(f'{root} wait {cli_name(waiter_name)}', operation,
                                     waiter.get('description') or f'Wait for {cli_name(waiter_name).replace("-", " ")}.')
    return count


def infer_effect(description):
    first = next(iter(re.findall(r'[a-z]+', description.lower())), '')
    if first in READ_VERBS:
        return 'get'
    if first in WRITE_VERBS:
        return 'set'
    return 'unknown'


def build_metadata(commands, overrides):
    """Keep curated purpose terms separate from regenerated completion fields."""
    result = {'commands': {}, 'recipes': overrides.get('recipes', [])}
    missing = []
    effects = Counter()
    flags_total = flags_described = described = 0
    for name, raw in commands.items():
        canonical = name
        seen = set()
        while commands[canonical].get('alias'):
            if canonical in seen or commands[canonical]['alias'] not in commands:
                raise ValueError(f'Invalid command alias: {name}')
            seen.add(canonical)
            canonical = commands[canonical]['alias']
        documented = commands[canonical]
        override = dict(overrides.get('commands', {}).get(canonical, {}))
        override.update(overrides.get('commands', {}).get(name, {}))
        prose = override.get('description', raw.get('description') or documented.get('description', ''))
        if raw.get('documented_positionals'):
            prose = prose.removesuffix(' Saves the response to an output file.')
        description = clean_description(prose)
        if any(value['name'] == 'outfile' for value in raw.get('documented_positionals', ())):
            if 'saves the response' not in description.lower():
                description = clean_description(description + ' Saves the response to an output file.', limit=260)
        effect = override.get('effect', raw.get('documented_effect', documented.get('documented_effect', infer_effect(description))))
        if (effect == 'unknown' and name.startswith('aws ') and description.lower().startswith(('returns ', 'gets '))
                and name.split()[-1].startswith(('get-', 'list-', 'describe-', 'search-', 'lookup-', 'batch-get-'))):
            effect = 'get'
        if effect not in ('get', 'set', 'depends', 'unknown'):
            raise ValueError(f'Invalid effect classification for {name}: {effect}')
        terms = purpose_terms(name + ' ' + description)
        terms = sorted(set(terms).union(override.get('terms', [])))
        entry = {'description': description, 'terms': terms, 'effect': effect, 'flags': {},
                 'source': 'curated' if 'description' in override else raw.get('documentation_source', documented.get('documentation_source', 'unavailable'))}
        if raw.get('command_group'):
            entry['command_group'] = True
        effects[effect] += 1
        if description:
            described += 1
        else:
            missing.append({'command': name, 'reason': 'source description unavailable'})
        for flag in raw.get('flags', {}):
            flags_total += 1
            rule = override.get('flags', {}).get(flag, {})
            text = clean_description(rule.get('description', raw.get('flag_descriptions', {}).get(flag, '')))
            flag_effect = rule.get('effect', effect)
            for prefix, classification in override.get('flag_prefix_effects', {}).items():
                if flag.startswith(prefix) and text:
                    flag_effect = classification
            if flag in ('--help', '--version', '--generate-cli-skeleton') or (flag == '-help' and name.split()[0] == 'terraform'):
                flag_effect = 'get'
            entry['flags'][flag] = {'description': text,
                'terms': sorted(set(purpose_terms(flag + ' ' + text)).union(rule.get('terms', []))),
                'effect': flag_effect,
                'source': 'curated' if 'description' in rule else raw.get('flag_sources', {}).get(flag, raw.get('documentation_source', 'unavailable'))}
            if text:
                flags_described += 1
            else:
                missing.append({'command': name, 'flag': flag, 'reason': 'source description unavailable'})
        result['commands'][name] = entry
    result['report'] = {'commands': len(commands), 'commands_described': described,
                        'flags': flags_total, 'flags_described': flags_described,
                        'effects': dict(effects), 'missing_descriptions': missing}
    return result
