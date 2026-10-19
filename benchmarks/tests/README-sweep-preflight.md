# Sweep preflight tests

Local checks for the Milestone 2 concurrency sweep (ADR-0003). They run on a
laptop CPU in seconds. They need no GPU, no model, no cloud and no network
beyond `127.0.0.1`. Findings and the readiness decision are in
[`docs/milestone-2-sweep-validation.md`](../../docs/milestone-2-sweep-validation.md).

## How to run

From the repo root:

```
python3 -m unittest benchmarks/tests/test_sweep_driver_preflight.py -v
```

**Prerequisites:** Python 3 (stdlib only — `unittest`, `http.server`,
`concurrent.futures`, `urllib`). No `uv sync`, no `.venv`, no packages. The
tests import `benchmarks/baseline_runner.py` (stdlib-only) and read
`benchmarks/results/baseline-20260828T172338Z.json` read-only.

To run the driver-contract group against a candidate driver:

```
CHARON_SWEEP_DRIVER=/path/to/driver.py \
  python3 -m unittest benchmarks/tests/test_sweep_driver_preflight.py -v
```

Without the variable, `benchmarks/sweep_driver.py` is used. If it is
missing, group C is skipped.

## Expected output

With `benchmarks/sweep_driver.py` present (the state on 2026-10-18):

```
Ran 26 tests in ~20s

OK
```

The driver tests print progress lines and one sweep summary table to
stderr/stdout; these are expected. One `ResourceWarning: Implicitly cleaning
up <HTTPError 500 ...>` may print; it comes from
`baseline_runner.post_generate`, which does not close the `HTTPError` it
catches. It is not a test failure.

Without the driver: `Ran 26 tests ... OK (skipped=19)`.

## What the tests cover

| Group | Tests | Runs now? | What it checks |
|---|---|---|---|
| A. Existing code and evidence | 4 | yes | Nearest-rank p99 at n = 100 is the second-largest value. The committed Week 1 TTFT p99 values and the 18.08% spread reproduce from `raw.requests`. The existing runner raises on an HTTP 500 and on a timeout (it has no per-request failure handling). |
| B. Queueing model on a fake serialized server | 3 | yes | With one lock around a fixed service time: wall time stays roughly constant from concurrency 1 to 16; queue wait shows in client latency, not in server-reported time; the server sees the requested concurrency. |
| C. Sweep-driver contract | 19 | yes | Concurrency limit respected and reached; request accounting with no retries; timeouts and HTTP failures recorded, not fatal; warmup excluded from summaries; duplicate records, incomplete runs, exceeded concurrency and token mismatches detected by validation; `main` writes a complete report. Tests marked `[Mn]` check decision n of `benchmarks/methodology.md`, "Concurrency sweep (Milestone 2)": warmup max(20, N) by send order [M2], client latency includes queue wait [M3], throughput window [M4], re-run once / flag / time box [M5], p50-only spread gate and pooled p99 [M6]. |

The interface is listed in the test module's docstring. The methodology is
decided in `benchmarks/methodology.md`, not in these tests.

## What the tests do not prove

- **Nothing about the real server.** Group B tests a stub with a
  `threading.Lock` and `time.sleep`. It does not run FastAPI, anyio, uvicorn,
  `transformers` or the GPU. It cannot show the real thread-pool limit, lock
  fairness, or how real request latency behaves at concurrency 64.
- **Not that the methodology is right.** Group C checks that the driver
  does what `benchmarks/methodology.md` says. It does not check the
  decisions themselves.
- **No measurement.** No test result here is a benchmark number (ADR-0001).
  Passing tests are preflight evidence, not progress toward the gate.
- **Timing tests are tolerant, not precise.** Group B uses 20 ms service time
  and wide bounds (0.7–1.3× ratio). A heavily loaded laptop can still make
  them flaky.

## Conditions that block GPU session 1

GPU session 1 stays blocked while any of these is true (detail in the
validation doc):

1. Group C does not pass against `benchmarks/sweep_driver.py` with zero
   skips. (Passes on 2026-10-18; the driver and methodology are not yet
   committed.)
2. The FastAPI / anyio thread-pool behaviour for the locked versions is not
   checked.
3. The owner has not approved the sweep and its estimated GPU-hours.
