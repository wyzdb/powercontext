"""Windows/native verification of delivered snapshots and historical records.

Does not install dependencies, start a database, invoke a model, or launch Linux.
Historical service records are checked for consistency, not authenticated anew.
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
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'context'))
from sdd_context.patcher import apply_patch
from sdd_context.minimax_client import extract_patch
from sdd_context.indexer import build_index


def digest(path):
    return hashlib.sha256(path.read_text(encoding='utf-8').encode('utf-8')).hexdigest()


def verify(output):
    output.mkdir(parents=True, exist_ok=True)
    before, after = (ROOT / 'artifacts' / x for x in ('before', 'after'))
    tests = sorted(p.relative_to(before).as_posix() for p in (before / 'tests').rglob('*.py'))
    after_tests = sorted(p.relative_to(after).as_posix() for p in (after / 'tests').rglob('*.py'))
    assert tests == after_tests
    assert all(digest(before/p) == digest(after/p) for p in tests), 'test sets changed'
    run_id = 'run-20261027T132226460027-6a9b05'
    record = json.loads((ROOT / 'records/minimax' / (run_id+'.json')).read_text(encoding='utf-8'))
    assert record['outcome'] == 'success'
    assert extract_patch(record['response']['text']) == record['patch']
    with tempfile.TemporaryDirectory(prefix='sdd-proof-') as temp:
        project = Path(temp) / 'business'
        shutil.copytree(before, project, ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        apply_patch(record['patch'], project)
        for change in record['changes']:
            name = change['path']
            assert digest(before/name) == change['before_sha'], name
            assert digest(after/name) == change['after_sha'], name
            assert digest(project/name) == change['after_sha'], name
    state = json.loads((ROOT/'records/powercontext/restart-context.json').read_text(encoding='utf-8'))
    assert state['state_used_in_context'] is True
    assert state['state']['status'] == 'completed'
    assert state['state']['task_id'] == record['task_id']
    assert all(v['exit_code'] == 0 for v in state['state']['verifications'])
    queries = [json.loads(s) for s in (ROOT/'records/seekdb/queries.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()]
    assert any(q['row_count'] > 0 and q['task_id'] == record['task_id'] for q in queries)
    bundle = build_index(ROOT/'business')
    assert len(bundle.specs) >= 6 and len(bundle.tests) >= 20
    outcomes = []
    jobs = [('before-target', before, ['tests/test_created_after_api.py'], 1, '4 failed'),
            ('before-regression', before, ['tests/test_service_listing.py','tests/test_api_listing.py'], 0, '17 passed'),
            ('after-full', after, ['tests'], 0, '21 passed'),
            ('module', ROOT, ['tests'], 0, None)]
    for label, cwd, args, code, expected in jobs:
        env = os.environ.copy()
        env['PYTHONPATH'] = str(cwd/'src') if cwd != ROOT else str(ROOT/'context')
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        env['NO_PROXY'] = env['no_proxy'] = 'localhost,127.0.0.1,::1'
        command = [sys.executable,'-m','pytest',*args,'-q','-p','no:cacheprovider']
        result = subprocess.run(command,cwd=cwd,env=env,stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',timeout=90)
        log = result.stdout
        normalized_log = '\n'.join(line.rstrip() for line in log.splitlines()) + '\n'
        (output/(label+'.log')).write_text(normalized_log,encoding='utf-8',newline='\n')
        assert result.returncode == code, f'{label}: exit {result.returncode}'
        if expected:
            assert expected in log, label
        if code:
            assert 'AssertionError' in log and 'ImportError' not in log and 'ERROR collecting' not in log
        outcomes.append(dict(label=label,command=command,exit_code=result.returncode,
                             expected_exit_code=code,log=label+'.log'))
    return dict(status='passed',scope='native_tests_and_archived_evidence_consistency',
                platform=platform.platform(),python=platform.python_version(),
                historical_record_id=run_id,historical_record_origin='existing user repository, 2026-10-27',
                live_model_called=False,live_database_queried=False,live_powercontext_restart=False,
                unchanged_test_files=tests,archived_queries=len(queries),tests=outcomes,
                snapshot_sources={stage:{str(p.relative_to(base)):digest(p) for p in sorted((base/'src').rglob('*.py'))}
                                  for stage,base in [('before',before),('after',after)]})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'records/native-validation-2026-10-29')
    args = parser.parse_args()
    result = verify(args.output)
    (args.output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('snapshot_sources','tests')},ensure_ascii=False,indent=2))
