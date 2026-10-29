"""Post-scoring attribute diagnostics; not imported by inference."""
import argparse
import collections
import csv
import json
from pathlib import Path
from bench import ROOT, checked_output, rows


def leaves(node):
    if node['type'] in ('all', 'any'):
        for child in node['children']:
            yield from leaves(child)
    elif node['type'] == 'not':
        yield from leaves(node['child'])
    else:
        yield node


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    out = checked_output(args.run)
    with (ROOT / 'data/practice.csv').open(encoding='utf-8-sig', newline='') as stream:
        attributes = {row['id']: {atom['attribute'] for atom in json.loads(row['form'] or '[]')}
                      for row in csv.DictReader(stream)}
    counts = collections.Counter()
    definitive = collections.Counter()
    ids = []
    for prediction, gold, plan in zip(rows(out / 'predictions.jsonl.gz'),
                                      rows(out / 'scoring/targets.jsonl.gz'),
                                      rows(out / 'features/evaluable-plans.jsonl.gz'), strict=True):
        if not prediction['id'] == gold['id'] == plan['id']:
            raise ValueError('ID mismatch')
        if plan['kind'] != 'provided' or gold['target']['label'] == prediction['label']:
            continue
        counts['error_rows'] += 1
        flags = set()
        target = list(leaves(gold['target']['structure']))
        actual = list(leaves(plan['tree'])) if 'tree' in plan else []
        if len(target) != len(actual):
            flags.add('different_leaf_count')
        else:
            for found, expected in zip(actual, target):
                if found['type'] != expected['type']:
                    flags.add('different_leaf_type')
                    continue
                if expected['type'] == 'recorded':
                    reference = found['reference']
                    if reference['attribute'] != expected['attribute']:
                        flags.add('attribute_mismatch')
                        if expected['attribute'] == 'api_version' and reference['attribute'] == 'version':
                            flags.add('api_version_as_version')
                    if reference['subject'] != expected['subject']:
                        flags.add('subject_mismatch')
                    if reference['date'] != expected['date']:
                        flags.add('date_mismatch')
                    if found.get('value') != expected['value']:
                        flags.add('literal_value_mismatch')
                else:
                    for side in ['left', 'right']:
                        if found[side]['attribute'] not in attributes[expected[side]]:
                            flags.add('comparison_attribute_mismatch')
                            if 'api_version' in attributes[expected[side]] and found[side]['attribute'] == 'version':
                                flags.add('api_version_as_version')
        counts.update(flags)
        if prediction['label'] != 'unsure':
            definitive['error_rows'] += 1
            definitive.update(flags)
            ids.append(prediction['id'])
    result = {'scope': 'Post-scoring structural diagnostics only; flags may overlap, original predictions unchanged. Every supplied-note error examined.',
              'counts': dict(counts), 'definitive_counts': dict(definitive), 'definitive_ids': ids}
    (out / 'error-causes.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
