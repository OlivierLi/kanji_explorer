# Component query performance, 2026-11-03

The fix computes the ranked component matches once per query, reuses them for
counts and independently limited direct/indirect lists, and keeps only needed
path fields in the ranked intermediate result. It preserves the pre-fix output,
including equivalent-component classification, ordering, counts, and paths.

The short exploratory medians quoted in the preceding review had no confidence
intervals and are superseded by the measurements below. They used the generated
runtime database; this experiment uses the tracked database package instead.

## Reproduce

From the repository root, with the Python dependencies needed by `server.py`:

```bash
python3 scripts/benchmark_component_queries.py \
  --main-ref 65d38e5 --baseline-ref 123da9d --candidate-ref 794001f \
  --blocks 30 --warmup 1 --repetitions 1 --bootstrap 10000 --seed 20261103 \
  --output /tmp/component_queries_reproduced.json
```

Recompute the reported statistics from the committed samples without retiming:

```bash
python3 scripts/benchmark_component_queries.py \
  --reanalyze benchmarks/component_queries_20261103_narrow.json \
  --bootstrap 10000 --output /tmp/component_queries_reanalyzed.json
```

The raw confirmation run is
[`component_queries_20261103_narrow.json`](component_queries_20261103_narrow.json).
It records every measured call in execution order, worker PIDs, output hashes,
the actual SQL and query plans, full source revisions and hashes, database
hashes, environment, and statistical settings. The timing script was committed
before the run; its SHA-256 is recorded in the artifact.

Historical `server.py` implementations are loaded from the specified commits
and use the same current supporting modules and current packaged database.
Supporting-module hashes and changes relative to the historical commits are
recorded. This compares query implementations on controlled inputs, not complete
historical deployments. Main's classification semantics differ, notably for
equivalent components of 日; its outputs are not required to equal the branch's.

## Experimental design

- Thirty sequential fresh worker processes. Each opens a separate read-only
  connection per variant to one private extraction of the tracked package.
- One untimed warmup and one measured call per variant/query/character per
  worker. All cases are shuffled in each warmup and measurement pass, using the
  recorded seed. There are 30 measured observations for each case.
- Usage calls are `query_component_closure_db(conn, char)` for 一, 木, and 日,
  comparing main, pre-fix, and fixed code. Search calls are
  `query_component_matches_db(conn, [char])`, comparing pre-fix and fixed code;
  main has no corresponding helper.
- `perf_counter_ns` surrounds the entire helper call: SQL execution, fetching,
  row formatting, and the helper's normal transaction lifecycle. Imports,
  connections, warmup, output validation, and HTTP/JSON transport are excluded.
  No caller transaction is held open around the measured calls.
- Full pre-fix/fixed output equality is checked after every worker's warmup
  and measurement results have been collected. All 30 workers passed.
- Latencies are arithmetic means of worker means. With one measured call per
  case per worker, these are ordinary arithmetic means of the 30 observations.
  Ratios are ratios of arithmetic means, not means of individual-call ratios.
- Intervals are pointwise 95% percentile bootstrap confidence intervals with
  10,000 resamples, seed 21261103, and linearly interpolated percentiles. Each
  resample draws whole worker blocks, retaining pairing across all variants and
  cases. They are not simultaneous intervals. No observations were discarded.

## Confirmation results

Every bracketed range below is a 95% confidence interval computed as described
above. Lower latency and lower fixed/pre-fix ratios are better.

### Character usage

| Character | Pre-fix mean ms | Fixed mean ms | Fixed / pre-fix |
| --- | ---: | ---: | ---: |
| 一 | 1270.46 [1263.19, 1279.49] | 452.56 [450.98, 454.39] | 0.3562 [0.3539, 0.3581] |
| 木 | 149.40 [148.85, 149.99] | 56.21 [55.95, 56.51] | 0.3763 [0.3749, 0.3777] |
| 日 | 163.00 [162.26, 163.91] | 61.52 [60.82, 62.63] | 0.3774 [0.3733, 0.3843] |

### Component search

| Character | Pre-fix mean ms | Fixed mean ms | Fixed / pre-fix |
| --- | ---: | ---: | ---: |
| 一 | 709.62 [706.33, 713.33] | 468.29 [463.48, 475.34] | 0.6599 [0.6530, 0.6698] |
| 木 | 83.45 [83.02, 83.98] | 55.72 [55.49, 55.97] | 0.6677 [0.6631, 0.6713] |
| 日 | 92.14 [90.83, 94.37] | 60.79 [60.53, 61.07] | 0.6597 [0.6446, 0.6687] |

### Historical main comparison for usage

| Character | Main mean ms | Fixed / main |
| --- | ---: | ---: |
| 一 | 451.27 [446.84, 457.79] | 1.0028 [0.9901, 1.0117] |
| 木 | 58.04 [57.79, 58.32] | 0.9686 [0.9639, 0.9734] |
| 日 | 67.09 [64.00, 72.95] | 0.9170 [0.8371, 0.9716] |

The tested fix improves both query families relative to the pre-fix branch.
For 一 versus main, the paired interval spans 1: this run establishes neither
a slowdown nor a speedup. This is not an equivalence test, nor evidence that
every query or endpoint is faster than main.

## Environment and limits

Intel Core i9-9900, Linux x86-64, Python 3.12.3, SQLite 3.45.1. CPU governor was
`powersave`; affinity allowed logical CPUs 0–15. No CPUs were isolated or pinned,
and unrelated host activity was not controlled. Start/end load averages and
clock details are in the artifact.

The private database contained 239,741 character rows and 1,481,503 closure
rows. SQLite settings included page size 4096, cache size -2000, temp store 0,
WAL journal mode, and mmap size 0. Package SHA-256:
`1c2bd164fe049ba92dc3293944f41012aa312d1a276190ca0ba2900538512720`.
Extracted database SHA-256:
`d9d8e7e5aabb44e6a65c0adfdfbf459a69ea86c6493eb8948bc545c1573bf20d`.

These are warm-query measurements with shared OS caches, not cold-start,
tail-latency, concurrency, or full HTTP measurements. Fresh processes are the
resampling unit, not proof of statistical independence: the intervals assume
exchangeable worker blocks despite possible shared-host temporal correlation.
They describe sampling uncertainty under this experiment, not variability
across machines, datasets, workloads, or SQLite versions. The case set is three
common components; it does not establish performance for every filter or input.

Captured confirmation plans show one materialized `ranked` set and one
materialized `matches` set per fixed query. Planner text is retained as evidence
for the recorded SQLite version, rather than asserted as a portable test API.
Regression tests cover a single ranked SQL statement, complete counts with an
empty selection, separate category limits, output semantics, and snapshots
during concurrent writes. The full suite passes 712 tests.

## Preserved first experiment

[`component_queries_20261103.json`](component_queries_20261103.json) records the
first fix, candidate `cfed3ba`, before narrowing the ranked projection. Its
paired fixed/main usage ratio for 一 was 1.0555 [1.0494, 1.0606], motivating the
projection refinement. That run is retained, not pooled with the confirmation
run or silently replaced. It was reanalyzed with committed tooling to add
fixed/main ratios; original timing provenance and separate analysis provenance
are both recorded.
