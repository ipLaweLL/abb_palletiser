# Randomized planner benchmark

This branch introduces a **standalone benchmark** for the current
`NewPalletPlanner`. It does not modify the planner, GUI, ABB TCP protocol,
RAPID, or any existing validation case.

## Run on Windows (from project root)

```powershell
git fetch origin
git switch feature/planner-benchmark
git pull
python -m planner.random_benchmark_test
python -m planner.random_benchmark --cases 1000 --seed 2026
```

Optional quick trial:

```powershell
python -m planner.random_benchmark --cases 30 --seed 2026 --output benchmark_results/smoke
```

The full run prints progress every 50 orders and saves reports to
`benchmark_results/` (ignored by Git). CLI switches:

- `--cases` total orders (default: 1000)
- `--seed` deterministic random seed (default: 2026)
- `--output` report directory (default: benchmark_results)
- `--progress-every` progress cadence; 0 disables progress

## Report files

- `cases.csv`: all 1,000 orders, assigned pallet preset, quantities, status,
  planner runtime, rejection class, floor columns and volume utilization.
  Filter `status=INVALID` or `status=CRASH` first; then examine
  `rejection_class=UNRESOLVED_HEURISTIC_REJECT`.
- `summary.json`: totals, runtime mean/median/p95/max, counts by case
  profile and pallet preset, and successful-case mean utilization.
- `summary.txt`: small human-readable summary.

## What this test *can* and *cannot* show

The script cycles over the five pallet presets already used by
`planner.validation_test` (including height and weight limits) and seven
reproducible order profiles: sparse, bucket-heavy, carton-heavy, balanced,
single-SKU, dense, and boundary orders.

- **PASS**: all requested units placed and existing geometric validator
  plus additional margin, gap, stacking, level and execution-order checks
  passed. This does **not** certify physical stability or robot reachability.
- **REJECT / PROVEN_NECESSARY_BOUND**: a necessary weight, volume, height or
  individual-footprint bound rules out the order under the planner's
  conservative box-based model. The volume calculation uses SKU bounding
  boxes (including buckets), consistent with the planner's footprint model.
- **REJECT / UNRESOLVED_HEURISTIC_REJECT**: the planner could not find a full
  arrangement; we have **not proved** that the order is infeasible.
- **INVALID**: planner returned a success that failed validation.
- **CRASH**: an unhandled planner/test exception; the traceback is recorded
  in `cases.csv`.

A nonzero `INVALID` or `CRASH` count causes the CLI to exit with status 1.
`REJECT` is an expected outcome, not an automatic failure.

Utilization is **total product bounding-box volume / available pallet
bounding volume**, not percent of the floor used, stability margin, or
a robot feasibility measure.

When comparing planner changes, rerun with the **same seed, case count,
Python environment and pallet settings**. Different profiles can have
different difficulty, so the PASS percentage should never be represented
as a general capacity or optimality guarantee.

## Follow-on actions

1. Inspect any INVALID/CRASH rows.
2. Inspect UNRESOLVED_HEURISTIC_REJECT rows with small orders first,
   especially where a human can construct a feasible arrangement.
3. Convert confirmed missed-feasibility examples into narrow regression
   fixtures before changing heuristics.
4. Only then compare planner improvements using the **same 1,000 inputs**.
