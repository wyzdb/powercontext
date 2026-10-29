"""Verify the delivered snapshots, the archived records and the newest live run.

Does not install dependencies, start a database, invoke a model, or launch
Linux. The service records are the evidence: every check below re-derives a
fact from a record or from the delivered sources.

Checks performed:

* the newest recorded MiniMax run (live round or archived) is reproduced by
  applying its patch to a copy of ``artifacts/before``;
* every archived run still applies to the pristine sources and reproduces the
  digests it recorded for itself, even when a later round overwrote the
  ``artifacts/after`` snapshot;
* the newest sample record proves the red/green sequence, the full suite and
  the state reuse performed by a fresh process;
* the seekdb query log and the PowerContext state log carry the evidence of
  this task;
* the business test suite still fails before the change and passes after it.

The ``live_*`` flags are computed from those records; they are not asserted by
hand.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'context'))
from sdd_context.patcher import apply_patch
from sdd_context.minimax_client import extract_patch
from sdd_context.indexer import build_index

TEMP_ROOT = ROOT / 'artifacts' / '.verify-tmp'


def digest(path):
    return hashlib.sha256(path.read_text(encoding='utf-8').encode('utf-8')).hexdigest()


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def latest(paths):
    return sorted(paths, key=lambda p: p.stat().st_mtime)[-1]


def apply_to_copy(before, patch, changes, label):
    """Apply ``patch`` to a throwaway copy of ``before`` and check the digests."""
    project = TEMP_ROOT / label
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(before, project, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    apply_patch(patch, project)
    for change in changes:
        name = change['path']
        assert digest(before / name) == change['before_sha'], f'{label}: {name} before digest'
        assert digest(project / name) == change['after_sha'], f'{label}: {name} patched digest'
    return project


def verify(output):
    output.mkdir(parents=True, exist_ok=True)
    before, after = (ROOT / 'artifacts' / x for x in ('before', 'after'))

    tests = sorted(p.relative_to(before).as_posix() for p in (before / 'tests').rglob('*.py'))
    after_tests = sorted(p.relative_to(after).as_posix() for p in (after / 'tests').rglob('*.py'))
    assert tests == after_tests
    assert all(digest(before / p) == digest(after / p) for p in tests), 'test sets changed'

    runs = read_jsonl(ROOT / 'records/minimax/runs.jsonl')
    run_ids = [run['run_id'] for run in runs if run.get('outcome') == 'success']
    assert run_ids, 'no successful MiniMax run recorded'

    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        # The newest run must reproduce the delivered snapshots.
        newest_id = run_ids[-1]
        newest = json.loads((ROOT / 'records/minimax' / (newest_id + '.json')).read_text(encoding='utf-8'))
        assert newest['outcome'] == 'success'
        assert extract_patch(newest['response']['text']) == newest['patch']
        apply_to_copy(before, newest['patch'], newest['changes'], 'newest')
        for change in newest['changes']:
            name = change['path']
            assert digest(after / name) == change['after_sha'], f'after snapshot: {name}'

        # Every archived run still applies to the pristine sources.
        archived = []
        for run_id in run_ids[:-1]:
            record = json.loads((ROOT / 'records/minimax' / (run_id + '.json')).read_text(encoding='utf-8'))
            assert record['outcome'] == 'success'
            assert extract_patch(record['response']['text']) == record['patch']
            apply_to_copy(before, record['patch'], record['changes'], run_id)
            archived.append(run_id)
    finally:
        shutil.rmtree(TEMP_ROOT, ignore_errors=True)

    # The newest sample record carries the live round.
    sample = latest(list((ROOT / 'records/sample').glob('sample-*.json')))
    sample_payload = json.loads(sample.read_text(encoding='utf-8'))
    steps = {step.get('step'): step for step in sample_payload['steps']}
    assert sample_payload['outcome'] == 'success'

    before_step = steps['target-tests-before-change']
    assert before_step['exit_code'] == 1 and before_step['ok']
    assert any('AssertionError' in line for line in before_step['tail'])
    assert any('4 failed' in line for line in before_step['tail'])

    change_step = steps['minimax-change']
    assert change_step['ok'] and change_step['model']['request_id']
    assert change_step['tests']['target']['exit_code'] == 0
    assert change_step['tests']['regression']['exit_code'] == 0

    suite_step = steps['full-test-suite']
    assert suite_step['exit_code'] == 0 and suite_step['ok']

    restart_step = steps['state-reuse-after-restart']
    assert restart_step['ok'] and restart_step['state_status'] == 'completed'
    assert restart_step['context_state_status'] == 'completed'
    assert restart_step['verifications'] >= 2

    # Database evidence: the queries that produced this round's context.
    queries = read_jsonl(ROOT / 'records/seekdb/queries.jsonl')
    task_id = sample_payload['task_id']
    task_queries = [q for q in queries if q.get('task_id') == task_id and q.get('row_count', 0) > 0]
    assert task_queries, 'no seekdb query with rows for the task'
    live_queries = [q for q in task_queries if q.get('at', '') >= sample_payload['at'][:10]]

    # PowerContext evidence: the state this round wrote and re-read.
    states = read_jsonl(ROOT / 'records/powercontext/state.jsonl')
    completed_states = [s for s in states if s.get('task_id') == task_id and s.get('status') == 'completed']
    assert completed_states, 'no completed PowerContext state for the task'

    bundle = build_index(ROOT / 'business')
    assert len(bundle.specs) >= 6 and len(bundle.tests) >= 20

    outcomes = []
    jobs = [('before-target', before, ['tests/test_created_after_api.py'], 1, '4 failed'),
            ('before-regression', before, ['tests/test_service_listing.py', 'tests/test_api_listing.py'], 0, '17 passed'),
            ('after-full', after, ['tests'], 0, '21 passed'),
            ('module', ROOT, ['tests'], 0, None)]
    for label, cwd, args, code, expected in jobs:
        env = os.environ.copy()
        source_root = str(cwd / 'src') if cwd != ROOT else str(ROOT / 'context')
        env['PYTHONPATH'] = source_root
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        env['NO_PROXY'] = env['no_proxy'] = 'localhost,127.0.0.1,::1'
        # Embedded interpreters ship a ``pythonXY._pth`` that ignores PYTHONPATH,
        # so the source root is injected through the interpreter itself. The
        # logical command stays the plain pytest invocation.
        bootstrap = ('import sys; sys.path.insert(0, r\'{0}\'); import pytest; '
                     'raise SystemExit(pytest.main({1!r}))').format(source_root, list(args))
        command = [sys.executable, '-c', bootstrap]
        logical = [sys.executable, '-m', 'pytest', *args, '-q', '-p', 'no:cacheprovider']
        result = subprocess.run(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', timeout=90)
        log = result.stdout
        normalized_log = '\n'.join(line.rstrip() for line in log.splitlines()) + '\n'
        (output / (label + '.log')).write_text(normalized_log, encoding='utf-8', newline='\n')
        assert result.returncode == code, f'{label}: exit {result.returncode}'
        if expected:
            assert expected in log, label
        if code:
            assert 'AssertionError' in log and 'ImportError' not in log and 'ERROR collecting' not in log
        outcomes.append(dict(label=label, command=logical, executed_command=command,
                             exit_code=result.returncode,
                             expected_exit_code=code, log=label + '.log'))

    return dict(status='passed',
                scope='native_tests_archived_evidence_and_live_round_consistency',
                platform=platform.platform(), python=platform.python_version(),
                newest_run_id=newest_id, newest_run_origin=sample_payload.get('at'),
                archived_runs=archived,
                live_model_called=bool(change_step['model'].get('request_id')),
                live_model_request_id=change_step['model'].get('request_id'),
                live_model_base_url=change_step['model'].get('base_url'),
                live_database_queried=bool(task_queries),
                live_database_queries_for_task=len(task_queries),
                live_queries_recorded_this_round=len(live_queries),
                live_powercontext_restart=bool(restart_step['ok']),
                live_powercontext_state_records=len(completed_states),
                sample_record=sample.name,
                unchanged_test_files=tests, archived_queries=len(queries), tests=outcomes,
                snapshot_sources={stage: {str(p.relative_to(base)): digest(p) for p in sorted((base / 'src').rglob('*.py'))}
                                  for stage, base in [('before', before), ('after', after)]})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'records/native-validation-2026-10-29-live')
    args = parser.parse_args()
    result = verify(args.output)
    (args.output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('snapshot_sources', 'tests')}, ensure_ascii=False, indent=2))
