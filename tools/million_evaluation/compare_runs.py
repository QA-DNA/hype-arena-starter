"""Scoring-only paired analysis; never imported by either inference adapter."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
from bench import canonical, rows, Metrics, checked_output


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).digest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--v1-dataset', type=Path, required=True)
    parser.add_argument('--v2-dataset', type=Path, required=True)
    parser.add_argument('--v1-run', type=Path, required=True)
    parser.add_argument('--v2-run', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = checked_output(args.out)
    out.mkdir(exist_ok=False)
    counts = collections.Counter()
    changes = collections.Counter()
    strata = {}
    transitions = collections.Counter()
    v1_inputs = {}
    v2_inputs = set()
    error_examples = {'fixed': [], 'regressed': [], 'still_wrong': []}

    def metric(group, version):
        return strata.setdefault(group, {}).setdefault(version, Metrics())

    inputs = zip(rows(args.v1_dataset / 'pool.jsonl.gz'), rows(args.v2_dataset / 'pool.jsonl.gz'),
                 rows(args.v1_run / 'predictions.jsonl.gz'), rows(args.v2_run / 'predictions.jsonl.gz'), strict=True)
    for before, after, prediction1, prediction2 in inputs:
        if len({before['id'], after['id'], prediction1['id'], prediction2['id']}) != 1:
            raise ValueError('Stable row IDs or ordering differ; perform an explicit ID join')
        gold1, gold2 = before['target']['label'], after['target']['label']
        pred1, pred2 = prediction1['label'], prediction2['label']
        hash1, hash2 = fingerprint(before['input']), fingerprint(after['input'])
        if hash1 in v1_inputs or hash2 in v2_inputs:
            raise ValueError('Duplicate full input in an archive')
        v1_inputs[hash1] = (gold1, pred1)
        v2_inputs.add(hash2)
        counts['rows'] += 1
        counts['same_input_at_same_id'] += hash1 == hash2
        counts['changed_input_at_same_id'] += hash1 != hash2
        counts['changed_label'] += gold1 != gold2
        counts['changed_target'] += before['target'] != after['target']
        counts['changed_ast'] += before['target']['structure'] != after['target']['structure']
        counts['changed_prediction_at_same_id'] += pred1 != pred2
        counts['same_case_key'] += before['metadata'].get('case_key') == after['metadata'].get('case_key')
        for name in after['metadata'].get('changes', []):
            changes[name] += 1
        family = before['metadata'].get('family', 'profile-' + str(before['metadata'].get('profile_id')))
        for group in ['all', 'unchanged_inputs' if hash1 == hash2 else 'rewritten_inputs', 'original_family:' + family]:
            metric(group, 'v1').add(gold1, pred1)
            metric(group, 'v2').add(gold2, pred2)
        transition = before['metadata']['task_schema'] + ' -> ' + after['metadata']['task_schema']
        transitions[transition] += 1
        if gold1 is not None and gold1 == gold2:
            correct1, correct2 = pred1 == gold1, pred2 == gold2
            key = 'both_correct' if correct1 and correct2 else 'fixed' if correct2 else 'regressed' if correct1 else 'both_wrong'
            counts[key] += 1
            example_key = 'still_wrong' if key == 'both_wrong' else key
            if example_key in error_examples and len(error_examples[example_key]) < 12:
                error_examples[example_key].append({'id': before['id'], 'label': gold1,
                    'v1_prediction': pred1, 'v2_prediction': pred2, 'v1_text': before['input']['text'],
                    'v2_text': after['input']['text'], 'original_family': family})
        if counts['rows'] % 100000 == 0:
            print(json.dumps({'compared': counts['rows']}), flush=True)

    exact_overlap = collections.Counter()
    # Full-input fingerprints, not stable IDs, establish unchanged-input overlap.
    for after, prediction in zip(rows(args.v2_dataset / 'pool.jsonl.gz'), rows(args.v2_run / 'predictions.jsonl.gz'), strict=True):
        old = v1_inputs.get(fingerprint(after['input']))
        if old is not None:
            exact_overlap['rows'] += 1
            exact_overlap['changed_label'] += old[0] != after['target']['label']
            exact_overlap['changed_prediction'] += old[1] != prediction['label']
    report = {'scope': 'Paired development rewrites; stable IDs can denote different questions. No independent facts or blind language generalization claimed.',
              'counts': dict(counts), 'exact_public_input_overlap': dict(exact_overlap),
              'changes': dict(changes), 'schema_transitions': dict(transitions),
              'strata': {g: {v: m.result() for v, m in versions.items()} for g, versions in strata.items()},
              'examples': error_examples,
              'source_inputs': {'v1_pool_sha256': hashlib.file_digest((args.v1_dataset / 'pool.jsonl.gz').open('rb'), 'sha256').hexdigest(),
                                'v2_pool_sha256': hashlib.file_digest((args.v2_dataset / 'pool.jsonl.gz').open('rb'), 'sha256').hexdigest()}}
    (out / 'comparison.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'counts': dict(counts), 'exact_public_input_overlap': dict(exact_overlap)}), flush=True)


if __name__ == '__main__':
    main()
