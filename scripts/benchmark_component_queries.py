"""Paired warm-query benchmark against exact historical server.py revisions.

Example (from any directory):
    python3 scripts/benchmark_component_queries.py --output component-benchmark.json

Only the query calls (SQL, fetching, formatting) are timed, excluding imports,
connections, warmup, output hashing and HTTP/JSON transport. Each fresh worker
warms every case, then randomizes all variant/case calls. Workers share the same
read-only private database and host/OS cache. By default the database is
decompressed from tracked data/kanji_explorer.db.gz; --database uses a SQLite backup. Bootstrap intervals resample entire
worker blocks; they are conditional on this machine, database and workload and
assume exchangeable blocks, not independent HTTP users or independent machines.
Historical server.py files use current supporting modules, whose hashes are
recorded. Main has different semantics and no component-search helper; only its
usage helper is benchmarked. Baseline/candidate outputs must match exactly.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import gzip
import json
import os
from pathlib import Path
import platform
import random
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()


def load_server(source: str, name: str):
    module = types.ModuleType('benchmark_' + name)
    module.__file__ = str(ROOT / 'server.py')
    sys.modules[module.__name__] = module
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    return module


def worker(config: dict, block: int) -> dict:
    rng = random.Random(config['seed'] + block)
    modules = {name: load_server(source, name) for name, source in config['sources'].items()}
    connections = {}
    for name in modules:
        conn = sqlite3.connect(Path(config['snapshot']).as_uri() + '?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
        connections[name] = conn
    cases = [(name, kind, char) for char in config['characters']
             for kind in ('usage', 'search') for name in modules
             if kind == 'usage' or name != 'main']

    def call(case):
        name, kind, char = case
        module, conn = modules[name], connections[name]
        if kind == 'usage':
            return module.query_component_closure_db(conn, char)
        return module.query_component_matches_db(conn, [char])

    outputs = defaultdict(list)
    for _ in range(config['warmup']):
        order = cases.copy()
        rng.shuffle(order)
        for case in order:
            outputs[case].append(call(case))
    samples = []
    for repetition in range(config['repetitions']):
        order = cases.copy()
        rng.shuffle(order)
        for case in order:
            start = time.perf_counter_ns()
            result = call(case)
            elapsed = time.perf_counter_ns() - start
            outputs[case].append(result)
            name, kind, char = case
            samples.append({'variant': name, 'kind': kind, 'char': char,
                            'repetition': repetition, 'elapsed_ns': elapsed})
    # Compare full structures, including counts, metadata, card ordering and paths.
    for kind in ('usage', 'search'):
        for char in config['characters']:
            assert outputs['baseline', kind, char] == outputs['candidate', kind, char], (kind, char)
    fingerprints = {f'{name}/{kind}/{char}': hashlib.sha256(
        json.dumps(results[0], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        for (name, kind, char), results in outputs.items()}
    plans = []
    if block == 0:
        for case in cases:
            name, kind, char = case
            conn = connections[name]
            statements = []
            conn.set_trace_callback(statements.append)
            call(case)
            conn.set_trace_callback(None)
            plans.append({'variant': name, 'kind': kind, 'char': char, 'statements': [
                {'sql': sql, 'plan': [list(row) for row in conn.execute('EXPLAIN QUERY PLAN ' + sql)]}
                for sql in statements if sql.lstrip().upper().startswith(('SELECT', 'WITH'))]})
    for conn in connections.values():
        conn.close()
    return {'block': block, 'pid': os.getpid(), 'samples': samples,
            'output_sha256': fingerprints, 'baseline_candidate_equal': True, 'plans': plans}


def percentile(sorted_values: list[float], probability: float) -> float:
    index = (len(sorted_values) - 1) * probability
    low = int(index)
    fraction = index - low
    return sorted_values[low] * (1 - fraction) + sorted_values[min(low + 1, len(sorted_values) - 1)] * fraction


def summarize(blocks: list[dict], bootstrap: int, seed: int) -> dict:
    # Average within a worker first; only whole worker blocks are resampled.
    values = defaultdict(list)
    for block in blocks:
        within = defaultdict(list)
        for sample in block['samples']:
            within[sample['variant'], sample['kind'], sample['char']].append(sample['elapsed_ns'] / 1e6)
        for key, samples in within.items():
            values[key].append(statistics.fmean(samples))
    estimates = {f'{variant}/{kind}/{char}/mean_ms': vals
                 for (variant, kind, char), vals in values.items()}
    ratios = {}
    for variant, kind, char in values:
        if variant == 'candidate':
            ratios[f'candidate/baseline/{kind}/{char}'] = (
                values[variant, kind, char], values['baseline', kind, char])
        if variant == 'baseline' and ('main', kind, char) in values:
            ratios[f'baseline/main/{kind}/{char}'] = (
                values[variant, kind, char], values['main', kind, char])
    distributions = defaultdict(list)
    rng = random.Random(seed)
    n = len(blocks)
    for _ in range(bootstrap):
        indices = [rng.randrange(n) for _ in range(n)]
        for key, vals in estimates.items():
            distributions[key].append(statistics.fmean(vals[i] for i in indices))
        for key, (numerator, denominator) in ratios.items():
            distributions[key].append(sum(numerator[i] for i in indices) / sum(denominator[i] for i in indices))
    summary = {}
    for key, distribution in distributions.items():
        distribution.sort()
        estimate = (statistics.fmean(estimates[key]) if key in estimates else
                    statistics.fmean(ratios[key][0]) / statistics.fmean(ratios[key][1]))
        summary[key] = {'estimate': estimate,
                        'ci95': [percentile(distribution, .025), percentile(distribution, .975)]}
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, help='Override tracked .db.gz with a backed-up runtime database')
    parser.add_argument('--baseline-ref', default='123da9d')
    parser.add_argument('--main-ref', default='65d38e5')
    parser.add_argument('--candidate-ref', default='WORKTREE')
    parser.add_argument('--characters', nargs='+', default=['一', '木', '日'])
    parser.add_argument('--blocks', type=int, default=30)
    parser.add_argument('--warmup', type=int, default=1)
    parser.add_argument('--repetitions', type=int, default=1)
    parser.add_argument('--bootstrap', type=int, default=10000)
    parser.add_argument('--seed', type=int, default=20261103)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker-config', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--block', type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker_config:
        print(json.dumps(worker(json.loads(args.worker_config.read_text()), args.block), ensure_ascii=False))
        return
    if args.output is None:
        parser.error('--output is required')
    if min(args.blocks, args.warmup, args.repetitions, args.bootstrap) < 1:
        parser.error('blocks, warmup, repetitions and bootstrap must be positive')
    started = datetime.now(timezone.utc).isoformat()
    refs = {'main': args.main_ref, 'baseline': args.baseline_ref, 'candidate': args.candidate_ref}
    sources = {name: ((ROOT / 'server.py').read_text() if ref == 'WORKTREE'
                      else subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{ref}:server.py'], text=True))
               for name, ref in refs.items()}
    metadata = {
        'started_utc': started,
        'command': sys.argv,
        'python': sys.version, 'sqlite': sqlite3.sqlite_version,
        'platform': platform.platform(), 'processor': platform.processor(),
        'cpu_count': os.cpu_count(), 'load_average_start': os.getloadavg(),
        'perf_counter': vars(time.get_clock_info('perf_counter')),
        'cpu_governor': (Path('/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor').read_text().strip()
                         if Path('/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor').exists() else None), 'cpu_affinity': sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None,
        'cpu_model': next((line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                           if line.startswith('model name')), '') if Path('/proc/cpuinfo').exists() else None,
        'git_head': git('rev-parse', 'HEAD'), 'git_status': git('status', '--short'),
        'sources': {name: {'ref': ref, 'commit': git('rev-parse', ref) if ref != 'WORKTREE' else None,
                           'server_sha256': hashlib.sha256(sources[name].encode()).hexdigest()}
                    for name, ref in refs.items()},
        'shared_current_dependencies_sha256': {str(path.relative_to(ROOT)): sha256(path)
                                                for path in sorted(ROOT.glob('*.py')) if path.name != 'server.py'},
        'benchmark_sha256': sha256(Path(__file__).resolve()),
        'dependencies_changed_since_historical_refs': {name: [path for path in git('diff', '--name-only', ref, '--', '*.py').splitlines()
                                                             if '/' not in path and path != 'server.py']
                                                      for name, ref in refs.items() if name != 'candidate'},
        'design': {'seed': args.seed, 'blocks': args.blocks, 'warmup_per_case_per_block': args.warmup,
                   'measured_calls_per_case_per_block': args.repetitions, 'characters': args.characters,
                   'timing': 'perf_counter_ns around full query helper, including fetching/formatting; no HTTP/JSON/import/setup',
                   'order': 'fresh subprocess per block; shuffle all variant/kind/character cases in every warmup and measured repetition',
                   'estimator': 'arithmetic mean of block mean milliseconds; paired ratios of arithmetic means (lower is faster)',
                   'interval': f'95% percentile bootstrap, {args.bootstrap} resamples of whole fresh-worker blocks, linearly interpolated percentiles',
                   'bootstrap_seed': args.seed + 1000000,
                   'limitations': 'Warm shared OS cache and host, no CPU isolation, fixed database/workload and current shared supporting modules. No cold-cache or tail-latency claims. Worker blocks are the resampling unit; exchangeability assumed despite possible temporal host correlation. CIs do not measure between-machine/database/cold-start/HTTP/concurrent-load variation. Main semantics differ; only baseline/candidate exact equality is required.'},
    }
    with tempfile.TemporaryDirectory(prefix='kanji-query-benchmark-') as temporary:
        snapshot = Path(temporary) / 'snapshot.db'
        package = ROOT / 'data/kanji_explorer.db.gz'
        if args.database:
            with sqlite3.connect(args.database.resolve().as_uri() + '?mode=ro', uri=True) as source:
                with sqlite3.connect(snapshot) as target:
                    source.backup(target)
                    target.execute('PRAGMA journal_mode=DELETE')
            metadata['database_input'] = {'source_path': str(args.database.resolve()), 'method': 'SQLite backup'}
        else:
            with gzip.open(package, 'rb') as source, snapshot.open('wb') as target:
                shutil.copyfileobj(source, target)
            metadata['database_input'] = {'package_path': str(package), 'package_sha256': sha256(package),
                                          'method': 'decompress tracked package into private database'}
        with sqlite3.connect(snapshot.as_uri() + '?mode=ro', uri=True) as conn:
            metadata['database'] = {'snapshot_sha256': sha256(snapshot),
                                    'snapshot_bytes': snapshot.stat().st_size,
                                    'characters': conn.execute('SELECT COUNT(*) FROM characters').fetchone()[0],
                                    'closure_rows': conn.execute('SELECT COUNT(*) FROM component_closure').fetchone()[0],
                                    'pragmas': {name: conn.execute('PRAGMA ' + name).fetchone()[0]
                                                for name in ('page_size', 'cache_size', 'temp_store', 'journal_mode', 'mmap_size')}}
        config = {'sources': sources, 'snapshot': str(snapshot), 'seed': args.seed,
                  'characters': args.characters, 'warmup': args.warmup, 'repetitions': args.repetitions}
        config_path = Path(temporary) / 'config.json'
        config_path.write_text(json.dumps(config))
        blocks = []
        for block in range(args.blocks):
            result = subprocess.check_output([sys.executable, str(Path(__file__).resolve()),
                                               '--worker-config', str(config_path), '--block', str(block)], text=True)
            blocks.append(json.loads(result))
            print(f'Completed worker block {block + 1}/{args.blocks}', file=sys.stderr, flush=True)
    report = {'metadata': metadata, 'blocks': blocks,
              'summary': summarize(blocks, args.bootstrap, args.seed + 1000000)}
    report['metadata']['finished_utc'] = datetime.now(timezone.utc).isoformat()
    report['metadata']['load_average_end'] = os.getloadavg()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report['summary'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
