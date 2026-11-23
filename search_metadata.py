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
              'show', 'shows', 'print', 'prints', 'read', 'reads', 'inspect', 'inspects'}
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
    return sorted(word for word in tokens(text) - STOP_WORDS if len(word) > 1)


def cli_name(name):
    name = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1-\2', name)
    return re.sub(r'([a-z0-9])([A-Z])', r'\1-\2', name).replace('_', '-').lower()


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


def _read_json(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8') as source:
        return json.load(source)


def import_aws_models(commands, model_directory):
    """Read installed AWS JSON models as data, without importing an AWS SDK."""
    count = 0
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
                for flag in entry.get('flags', {}):
                    base = flag.removeprefix('--')
                    negative = base.startswith('no-') and base[3:] in by_flag
                    member = by_flag.get(base[3:] if negative else base)
                    if member is None:
                        continue
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
        override = overrides.get('commands', {}).get(name, {})
        description = clean_description(override.get('description', raw.get('description', '')))
        effect = override.get('effect', infer_effect(description))
        if effect not in ('get', 'set', 'depends', 'unknown'):
            raise ValueError(f'Invalid effect classification for {name}: {effect}')
        terms = purpose_terms(name + ' ' + description)
        terms = sorted(set(terms).union(override.get('terms', [])))
        entry = {'description': description, 'terms': terms, 'effect': effect, 'flags': {},
                 'source': 'curated' if 'description' in override else raw.get('documentation_source', 'unavailable')}
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
            entry['flags'][flag] = {'description': text,
                'terms': sorted(set(purpose_terms(flag + ' ' + text)).union(rule.get('terms', []))),
                'effect': rule.get('effect', effect),
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
