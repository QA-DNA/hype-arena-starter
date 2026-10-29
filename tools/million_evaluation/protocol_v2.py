"""Declared V2 surface-language compatibility; original V1 adapter stays frozen.

Uses the lexicon and literal public language tables, never generator execution,
targets, source bank values, row IDs, profiles or label-specific rewrites.
The original value extractor and evidence/logic kernels remain unchanged.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from protocol import Protocol, ProtocolError, PREDICATES, natural_date

TABLES = json.loads(Path(__file__).with_name('v2-language.json').read_text(encoding='utf-8'))['tables']
DAY = r'\d{1,2} \w+ \d{4}'
VERSION_ATTRIBUTES = ('version', 'cli_version', 'stable_version', 'api_version', 'shipping_android')


def template_regex(template, subjects):
    parts = re.split(r'(\{[a-z]+\})', template)
    fields = {'s': '(?P<subject>' + '|'.join(re.escape(s) for s in sorted(subjects, key=len, reverse=True)) + ')',
              'v': r'(?P<value>.+?)', 'on': '(?:on|in)'}
    return re.compile(''.join(fields.get(p[1:-1], re.escape(p)) if p.startswith('{') else re.escape(p) for p in parts), re.I)


class ProtocolV2(Protocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.clauses = []
        patterns = {a: list(v) for a, v in TABLES['PATTERNS'].items()}
        for attr, template in TABLES['DATES'].items():
            patterns.setdefault(attr, []).append('{s} ' + template)
        for attr, template in TABLES['NAMES'].items():
            patterns.setdefault(attr, []).append(template)
        for attr, templates in TABLES['BOOL'].items():
            for truth, template in zip(('yes', 'no'), templates):
                self.compile_clause(attr, '{s} ' + template, truth)
                if attr == 'single_sign_on':
                    self.compile_clause(attr, '{s} ' + template + ' for administrators', truth)
        extra = {
            'version': ['{s} is on version {v}', '{s} runs version {v}'],
            'cli_version': ['the CLI for {s} is at version {v}'],
            'stable_version': ['the stable version of {s} is {v}'],
            'data_retention': ['the hosted edition of {s} keeps uploads for {v}'],
            'ticket_price': ['early-rate tickets for {s} cost {v}'],
            'uptime_sla': ['paid plans on {s} carry an uptime SLA of {v}'],
            'price': ['the {s} add-on costs {v} per user', '{s} costs {v} per user'],
            'customers': ['the customer count in {s} is {v}'],
            'active_users': ['{s} has {v} active users'],
            'paying_customers': ['{s} has {v} paying customers'],
        }
        for attr in VERSION_ATTRIBUTES:
            if attr not in ('cli_version', 'stable_version'):
                extra[attr] = ['{s} is on version {v}', '{s} runs version {v}']
        extra['price_per_user'] = ['the {s} add-on costs {v} per user']
        for attr, values in extra.items():
            patterns.setdefault(attr, []).extend(values)
        for attr, values in patterns.items():
            for value in values:
                suffix = ' users' if attr == 'active_users' and value.endswith(' active users') else ' customers' if attr == 'paying_customers' and value.endswith(' paying customers') else ''
                self.compile_clause(attr, value, suffix=suffix)
        self.noise = [re.compile(re.escape(s).replace(re.escape('{n}'), r'\d+'), re.I) for s in TABLES['NOISE']]

    def compile_clause(self, attr, template, fixed=None, suffix=''):
        subjects = [s for s, attrs in self.legal.items() if attr in attrs
                    and not (attr == 'api_version' and 'version' in attrs)]
        if subjects:
            self.clauses.append((attr, template_regex(template, subjects), fixed, suffix,
                                 len(re.sub(r'\{\w+\}', '', template))))

    def bindings(self, context):
        found = super().bindings(context)
        for note in context:
            if note.get('role') != 'discourse':
                continue
            match = re.fullmatch(r'Note (\w+) concerns (.+?): (.+?), dated (.+)\.', note.get('text', ''), re.I)
            if not match:
                continue
            ordinal, subject, field, when = match.groups()
            sid = note.get('id', '').removeprefix('binding-') if note.get('id', '').startswith('binding-') else None
            desc = self.descriptor(subject, field, when, sid)
            if ordinal.casefold() in found and found[ordinal.casefold()] != desc:
                raise ProtocolError('Ambiguous ordinal declaration')
            found[ordinal.casefold()] = desc
        return found

    def v2_reference(self, text, bindings):
        match = re.fullmatch(r'the (.+?) in note (\w+)', text, re.I)
        if match:
            field, ordinal = match.groups()
            if ordinal.casefold() not in bindings:
                raise ProtocolError('Missing ordinal declaration')
            ref = bindings[ordinal.casefold()].copy()
            check = self.descriptor(ref['subject'], field, self.iso_to_natural(ref['date']), ref['source_id'])
            if check != ref:
                raise ProtocolError('Ordinal attribute mismatch')
            return ref
        match = re.fullmatch(r'the (.+?) for (.+?) reported on (' + DAY + ')', text, re.I)
        if not match:
            raise ProtocolError('Unknown V2 comparison reference')
        return self.descriptor(match[2], match[1], match[3])

    @staticmethod
    def iso_to_natural(value):
        from datetime import date
        return date.fromisoformat(value).strftime('%d %B %Y').lstrip('0')

    def clause(self, body, when):
        proposals = []
        for attr, pattern, fixed, suffix, specificity in self.clauses:
            match = pattern.fullmatch(body)
            if match:
                value = fixed or match['value'] + suffix
                if attr in VERSION_ATTRIBUTES:
                    value = 'version ' + value
                subject = next(s for s in self.legal if s.casefold() == match['subject'].casefold())
                proposals.append((specificity, subject, attr, value))
        # Generic field fragments are another explicitly documented surface.
        for subject in self.legal:
            patterns = [r'(.+?) for ' + re.escape(subject) + r': (.+)', re.escape(subject) + r', (.+?): (.+)']
            for pattern in patterns:
                match = re.fullmatch(pattern, body, re.I)
                if match:
                    try:
                        desc = self.descriptor(subject, match[1], when)
                        proposals.append((len(body) - len(match[2]), subject, desc['attribute'], match[2]))
                    except ProtocolError:
                        pass
        best = max((p[0] for p in proposals), default=0)
        unique = {tuple(p[1:]) for p in proposals if p[0] == best}
        if len(unique) != 1:
            raise ProtocolError('Unresolved V2 subject/attribute clause')
        subject, attr, value = unique.pop()
        # Use the established value-grammar path after resolving language only.
        ref = {'subject': subject, 'attribute': attr, 'date': natural_date(when), 'source_id': None}
        return self.recorded(ref, value)

    @staticmethod
    def recorded(ref, value):
        return {'type': 'recorded', 'reference': ref,
                'literal': f"{ref['subject']}'s {ref['attribute']} is {value}.", 'value_text': value}

    def v2_leaf(self, text, bindings):
        predicates = {'is ' + phrase: op for phrase, op in PREDICATES.items()}
        predicates['equals'] = 'eq'
        match = re.fullmatch(r'(.+?) (' + '|'.join(map(re.escape, sorted(predicates, key=len, reverse=True))) + r') (.+)', text, re.I)
        if match and match[1].casefold().startswith('the '):
            return {'type': 'compare', 'left': self.v2_reference(match[1], bindings),
                    'right': self.v2_reference(match[3], bindings), 'op': predicates[match[2].casefold()]}
        match = re.fullmatch(r'(.+?) in note (\w+): (.+)', text, re.I)
        if match:
            field, ordinal, value = match.groups()
            if ordinal.casefold() not in bindings:
                raise ProtocolError('Missing ordinal declaration')
            ref = bindings[ordinal.casefold()].copy()
            check = self.descriptor(ref['subject'], field, self.iso_to_natural(ref['date']), ref['source_id'])
            if check != ref:
                raise ProtocolError('Ordinal attribute mismatch')
            if ref['attribute'] in VERSION_ATTRIBUTES:
                value = 'version ' + value
            return self.recorded(ref, value)
        patterns = [r'the (' + DAY + r') note says (.+)',
                    r'from the note dated (' + DAY + r'): (.+)',
                    r'according to the (' + DAY + r') note, (.+)']
        for pattern in patterns:
            match = re.fullmatch(pattern, text, re.I)
            if match:
                return self.clause(match[2], match[1])
        match = re.fullmatch(r'(.+), as reported on (' + DAY + ')', text, re.I)
        if match:
            return self.clause(match[1], match[2])
        raise ProtocolError('Unknown V2 recorded-value clause')

    def parse(self, inp):
        if inp['text'].startswith('Using only the supplied notes, '):
            return super().parse(inp)
        if inp.get('evidence_policy') != 'provided_notes_only':
            raise ProtocolError('Not the supplied-notes protocol')
        text = inp['text']
        if len(text) > 65536:
            raise ProtocolError('Query length limit')
        for noise in self.noise:
            match = re.search(r' ' + noise.pattern + r'$', text, re.I)
            if match:
                text = text[:match.start()]
                break
        if not text.endswith('.'):
            raise ProtocolError('Missing query terminator')
        text = text[:-1]
        bindings = self.bindings(inp.get('context', []))
        nodes = 0

        def split(text, separator):
            parts = []; depth = 0; begin = 0; i = 0
            while i < len(text):
                if depth == 0 and text.startswith(separator, i):
                    parts.append(text[begin:i]); i += len(separator); begin = i; continue
                if text[i] == '(':
                    depth += 1
                elif text[i] == ')':
                    depth -= 1
                    if depth < 0:
                        raise ProtocolError('Unbalanced V2 group')
                i += 1
            if depth:
                raise ProtocolError('Unbalanced V2 group')
            parts.append(text[begin:]); return parts

        def expression(text, depth=0):
            nonlocal nodes
            nodes += 1; text = text.strip()
            if depth > 16 or nodes > 64:
                raise ProtocolError('Program size/depth limit')
            for lead, op in [('not all of these hold: ', 'all'), ('none of these holds: ', 'any')]:
                if text.casefold().startswith(lead):
                    children = [expression(s, depth + 1) for s in split(text[len(lead):], '; ')]
                    return {'type': 'not', 'child': {'type': op, 'children': children}}
            lead = "it isn't true that "
            if text.casefold().startswith(lead):
                return {'type': 'not', 'child': expression(text[len(lead):], depth + 1)}
            for separator, op in [('. ', 'all'), (' and ', 'all'), (' or ', 'any')]:
                parts = split(text, separator)
                if len(parts) > 1:
                    return {'type': op, 'children': [expression(s, depth + 1) for s in parts]}
            if text.startswith('(') and text.endswith(')'):
                return expression(text[1:-1], depth + 1)
            return self.v2_leaf(text, bindings)
        return expression(text)
