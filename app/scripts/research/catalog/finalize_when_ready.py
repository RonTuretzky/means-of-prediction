"""Finish an in-flight catalog expansion without further model calls."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone


def atomic(path: Path, value: dict) -> None:
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.chmod(0o600)
    os.replace(temporary, path)


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def ready(collections: list[Path], pids: list[int]) -> tuple[bool, list[dict]]:
    states = []
    for directory, pid in zip(collections, pids):
        checkpoint = json.loads((directory / 'checkpoint.json').read_bytes())
        checkpoint.pop('nextCursor', None)
        checkpoint.pop('lastEntry', None)
        manifest_path = directory / 'manifest.json'
        complete = manifest_path.exists() and json.loads(manifest_path.read_bytes()).get('complete') is True
        states.append({'directory': str(directory), 'complete': complete, 'checkpoint': checkpoint})
        if not complete and not alive(pid):
            raise RuntimeError(f'collector exited before completion: {directory}; inspect its checkpoint and failure receipts')
    return all(state['complete'] for state in states), states


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collection', type=Path, action='append', required=True)
    parser.add_argument('--worker-pid', type=int, action='append', required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--catalog-output', type=Path, required=True)
    parser.add_argument('--mapping-output', type=Path, required=True)
    args = parser.parse_args()
    if len(args.collection) != len(args.worker_pid):
        parser.error('each collection needs its worker PID')
    os.umask(0o077)
    args.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    state_path = args.state_dir / 'state.json'
    state = {'startedAt': datetime.now(timezone.utc).isoformat(), 'phase': 'waiting_for_collection'}

    def publish():
        state['updatedAt'] = datetime.now(timezone.utc).isoformat()
        atomic(state_path, state)

    def run(module: str, arguments: list[str], log_name: str):
        with (args.state_dir / log_name).open('xb') as log:
            subprocess.run([sys.executable, '-m', module, *arguments], check=True, stdout=log, stderr=subprocess.STDOUT)

    try:
        while True:
            finished, states = ready(args.collection, args.worker_pid)
            state['collections'] = states
            publish()
            if finished:
                break
            time.sleep(30)
        state['phase'] = 'auditing_and_building_catalog'
        publish()
        arguments = ['--output', str(args.catalog_output)]
        for directory in args.collection:
            arguments.extend(['--api-pages', str(directory / 'raw-pages')])
        run('app.scripts.research.catalog', arguments, 'catalog-build.log')
        state['catalogCounts'] = json.loads((args.catalog_output / 'manifest.json').read_bytes())['counts']
        state['catalogOutput'] = str(args.catalog_output)
        state['phase'] = 'mapping_separate_disputed_cohort'
        publish()
        run('app.scripts.research.catalog.map_disputes', [
            '--catalog-dir', str(args.catalog_output), '--output', str(args.mapping_output),
        ], 'dispute-map.log')
        state['disputeMappingCounts'] = json.loads((args.mapping_output / 'manifest.json').read_bytes())['counts']
        state['mappingOutput'] = str(args.mapping_output)
        state['phase'] = 'complete'
        state['trainingAdmission'] = 'none; article evidence and independent review still required'
        publish()
        return 0
    except Exception as error:
        state['failedPhase'] = state['phase']
        state['phase'] = 'needs_attention'
        state['error'] = str(error)
        publish()
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
