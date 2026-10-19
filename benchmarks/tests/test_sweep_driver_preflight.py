"""Local preflight checks for the Milestone 2 concurrency sweep — stdlib
unittest, no GPU, no model, no new deps, network on 127.0.0.1 only.

    python3 -m unittest benchmarks/tests/test_sweep_driver_preflight.py -v

Three groups (see benchmarks/tests/README-sweep-preflight.md):

  A. Existing code and committed evidence. Runs now. Read-only.
  B. Queueing model on a fake *serialized* server. Runs now. It tests the
     stub, not serving/naive_server.py: it shows what the sweep should look
     like if the real server behaves like the stub.
  C. Sweep-driver contract, against benchmarks/sweep_driver.py (skipped if
     it is missing). To run them against another module:

         CHARON_SWEEP_DRIVER=/path/to/driver.py python3 -m unittest ...

     Interface:

         run_level(url, prompts, *, concurrency, warmup, requests,
                   output_tokens, timeout_s) -> {"records": [...], "max_in_flight": int, ...}
             record: {"seq", "is_warmup", "in_flight_at_send", "ok", "error",
                      "t_start", "t_end", "client_e2e_s", "server"}
         validate_level(result, *, warmup, requests) -> list[str]   # [] == clean
         summarize_level(result) -> {"n", "n_failed", "client_e2e_s", "ttft_s", ...,
                                     "requests_per_s", "output_tokens_per_s"}
         warmup_for(concurrency) -> int
         aggregate_level(attempts, spread_threshold) -> dict
         run_sweep(url, prompts, *, levels, runs, requests, warmup_base, seed, ...) -> list
         schedule(levels, runs, seed) -> list[list[int]]
         main(argv) -> int

     Tests marked [Mn] check decision n of benchmarks/methodology.md,
     "Concurrency sweep (Milestone 2)". The methodology is decided there,
     not here.
"""
import importlib.util
import json
import os
import pathlib
import statistics
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BENCH = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BENCH))
import baseline_runner as br  # noqa: E402

BASELINE = BENCH / "results" / "baseline-20260828T172338Z.json"


# --------------------------------------------------------------------------- #
# Fake server: one lock around a fixed sleep, like naive_server's _GEN_LOCK.
# --------------------------------------------------------------------------- #
class FakeServer:
    """Serialized stand-in for naive_server on 127.0.0.1.

    service_s: time spent inside the lock per request.
    fail_on:   arrival numbers (0-based) answered with HTTP 500.
    slow_on:   {arrival: extra seconds} slept *outside* the lock.
    ttft_for:  callable(arrival) -> ttft_s reported in the payload.
    """

    def __init__(self, service_s=0.02, fail_on=(), slow_on=None, ttft_for=None):
        self.service_s = service_s
        self.fail_on = set(fail_on)
        self.slow_on = dict(slow_on or {})
        self.ttft_for = ttft_for or (lambda n: 0.01)
        self.gen_lock = threading.Lock()
        self.count_lock = threading.Lock()
        self.received = 0
        self.in_flight = 0
        self.max_in_flight = 0

        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep test output clean
                pass

            def do_GET(self):
                body = json.dumps({"status": "ok", "model_id": "fake", "device": "cpu",
                                   "model_revision": "0" * 40}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                with fake.count_lock:
                    n = fake.received
                    fake.received += 1
                    fake.in_flight += 1
                    fake.max_in_flight = max(fake.max_in_flight, fake.in_flight)
                try:
                    time.sleep(fake.slow_on.get(n, 0.0))
                    if n in fake.fail_on:
                        self.send_response(500)
                        self.end_headers()
                        self.wfile.write(b'{"detail": "injected failure"}')
                        return
                    with fake.gen_lock:
                        t0 = time.perf_counter()
                        time.sleep(fake.service_s)
                        e2e = time.perf_counter() - t0
                    body = json.dumps({
                        "text": "x", "prompt_tokens": 41, "output_tokens": 128,
                        "ttft_s": fake.ttft_for(n), "tpot_s": e2e / 128, "e2e_s": e2e,
                        "decode_tokens_per_s": 128 / e2e, "itl_s": [], "peak_vram_bytes": None,
                    }).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                finally:
                    with fake.count_lock:
                        fake.in_flight -= 1

        class Server(ThreadingHTTPServer):
            daemon_threads = True
            block_on_close = False
            request_queue_size = 128

        self.httpd = Server(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


def closed_loop(url, concurrency, total):
    """Minimal closed-loop client for group B: (wall_s, client latencies, payloads)."""
    def one(i):
        t = time.perf_counter()
        payload, _ = br.post_generate(url, "p", 128, 10.0)
        return time.perf_counter() - t, payload

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        out = list(pool.map(one, range(total)))
    return time.perf_counter() - t0, [o[0] for o in out], [o[1] for o in out]


# --------------------------------------------------------------------------- #
# A. Existing code and committed evidence
# --------------------------------------------------------------------------- #
class ExistingRunnerAndEvidence(unittest.TestCase):
    def test_nearest_rank_p99_is_second_largest_at_n100(self):
        # At 100 measured requests per run, p99 is decided by two samples.
        vals = [float(i) for i in range(1, 101)]
        self.assertEqual(br.percentile(vals, 99), 99.0)
        self.assertEqual(br.percentile(vals, 50), 50.0)

    def test_committed_ttft_p99_spread_reproduces(self):
        data = json.loads(BASELINE.read_text())
        p99 = []
        for run in (1, 2, 3):
            ttft = [r["server"]["ttft_s"] for r in data["raw"]["requests"]
                    if r["run"] == run and not r["is_warmup"]]
            self.assertEqual(len(ttft), 100)
            p = br.percentile(ttft, 99)
            self.assertEqual(p, data["summary"]["per_run"][run - 1]["ttft_s"]["p99"])
            p99.append(p)
        self.assertAlmostEqual(br.spread(p99), 0.1808, places=4)

    def test_runner_raises_on_http_error(self):
        # Documents current behaviour: one failed request aborts the run.
        with FakeServer(fail_on={0}) as fs:
            with self.assertRaises(RuntimeError):
                br.post_generate(fs.url, "p", 128, 5.0)

    def test_runner_raises_on_timeout(self):
        # Documents current behaviour: a timeout is an uncaught exception.
        with FakeServer(slow_on={0: 1.5}) as fs:
            with self.assertRaises(OSError):  # TimeoutError / URLError are OSError
                br.post_generate(fs.url, "p", 128, 0.3)


# --------------------------------------------------------------------------- #
# B. Queueing model on the fake serialized server (tests the stub only)
# --------------------------------------------------------------------------- #
class SerializedQueueingModel(unittest.TestCase):
    SERVICE_S = 0.02
    TOTAL = 40

    def test_wall_time_roughly_independent_of_concurrency(self):
        walls = {}
        for c in (1, 4, 16):
            with FakeServer(service_s=self.SERVICE_S) as fs:
                walls[c], _, _ = closed_loop(fs.url, c, self.TOTAL)
        floor = self.TOTAL * self.SERVICE_S
        for c, w in walls.items():
            self.assertGreaterEqual(w, floor * 0.95, f"c={c} faster than serial floor")
        self.assertLess(walls[16] / walls[1], 1.3, walls)
        self.assertGreater(walls[16] / walls[1], 0.7, walls)

    def test_queue_wait_shows_in_client_latency_not_server_time(self):
        with FakeServer(service_s=self.SERVICE_S) as fs:
            _, client_lat, payloads = closed_loop(fs.url, 8, self.TOTAL)
        server_e2e = statistics.median(p["e2e_s"] for p in payloads)
        self.assertLess(server_e2e, self.SERVICE_S * 2)
        self.assertGreater(statistics.median(client_lat), self.SERVICE_S * 3)

    def test_fake_server_sees_requested_concurrency(self):
        with FakeServer(service_s=self.SERVICE_S) as fs:
            closed_loop(fs.url, 8, self.TOTAL)
            self.assertEqual(fs.max_in_flight, 8)


# --------------------------------------------------------------------------- #
# C. Sweep-driver contract (skipped until a driver exists)
# --------------------------------------------------------------------------- #
def _load_driver():
    path = os.environ.get("CHARON_SWEEP_DRIVER") or str(BENCH / "sweep_driver.py")
    if not pathlib.Path(path).is_file():
        return None, path
    spec = importlib.util.spec_from_file_location("charon_sweep_driver", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, path


DRIVER, DRIVER_PATH = _load_driver()


@unittest.skipIf(DRIVER is None, f"sweep driver not implemented (looked for {DRIVER_PATH})")
class SweepDriverContract(unittest.TestCase):
    PROMPTS = ["a", "b", "c"]

    def run_level(self, fs, **kw):
        args = dict(concurrency=4, warmup=4, requests=20, output_tokens=128, timeout_s=5.0)
        args.update(kw)
        return DRIVER.run_level(fs.url, self.PROMPTS, **args)

    def test_concurrency_limit_respected_and_reached(self):
        with FakeServer(service_s=0.01) as fs:
            res = self.run_level(fs, concurrency=4, warmup=4, requests=20)
            self.assertEqual(fs.max_in_flight, 4)
        self.assertLessEqual(res["max_in_flight"], 4)

    def test_request_accounting_and_no_retries(self):
        with FakeServer(service_s=0.005) as fs:
            res = self.run_level(fs, warmup=4, requests=20)
            self.assertEqual(fs.received, 24, "driver sent extra requests (retries?)")
        seqs = [r["seq"] for r in res["records"]]
        self.assertEqual(sorted(seqs), list(range(24)))
        self.assertEqual(sum(r["is_warmup"] for r in res["records"]), 4)
        self.assertEqual(DRIVER.validate_level(res, warmup=4, requests=20), [])

    def test_timeout_recorded_not_fatal(self):
        with FakeServer(service_s=0.005, slow_on={5: 2.0}) as fs:
            res = self.run_level(fs, timeout_s=0.5)
        bad = [r for r in res["records"] if not r["ok"]]
        self.assertEqual(len(bad), 1)
        self.assertIn("timeout", (bad[0]["error"] or "").lower())
        self.assertEqual(len(res["records"]), 24)
        self.assertTrue(DRIVER.validate_level(res, warmup=4, requests=20))

    def test_http_failure_recorded_not_fatal(self):
        with FakeServer(service_s=0.005, fail_on={10}) as fs:
            res = self.run_level(fs)
        bad = [r for r in res["records"] if not r["ok"]]
        self.assertEqual(len(bad), 1)
        self.assertIn("500", bad[0]["error"] or "")
        self.assertTrue(DRIVER.validate_level(res, warmup=4, requests=20))
        summary = DRIVER.summarize_level(res)
        if not bad[0]["is_warmup"]:
            self.assertEqual(summary["n_failed"], 1)
            self.assertEqual(summary["n"], 19)

    def test_warmup_excluded_from_summary_at_concurrency_1(self):
        with FakeServer(service_s=0.002, ttft_for=lambda n: 10.0 if n < 4 else 0.01) as fs:
            res = self.run_level(fs, concurrency=1, warmup=4, requests=20)
        summary = DRIVER.summarize_level(res)
        self.assertEqual(summary["n"], 20)
        self.assertLess(summary["ttft_s"]["p99"], 1.0)

    def test_validate_flags_duplicate_records(self):
        with FakeServer(service_s=0.002) as fs:
            res = self.run_level(fs)
        res["records"].append(dict(res["records"][7]))
        problems = DRIVER.validate_level(res, warmup=4, requests=20)
        self.assertTrue(any("duplicate" in p.lower() for p in problems), problems)

    def test_validate_flags_incomplete_run(self):
        with FakeServer(service_s=0.002) as fs:
            res = self.run_level(fs)
        del res["records"][-3:]
        self.assertTrue(DRIVER.validate_level(res, warmup=4, requests=20))

    # -- methodology decisions ------------------------------------------- #
    def test_m2_warmup_is_max_20_n(self):
        self.assertEqual([DRIVER.warmup_for(n) for n in (1, 2, 4, 8, 16, 32, 64)],
                         [20, 20, 20, 20, 20, 32, 64])

    def test_m2_seq_is_dispatch_order_and_warmup_is_first_sent(self):
        with FakeServer(service_s=0.003) as fs:
            res = self.run_level(fs, concurrency=4, warmup=6, requests=20)
        by_start = [r["seq"] for r in sorted(res["records"], key=lambda r: (r["t_start"], r["seq"]))]
        self.assertEqual(by_start, list(range(26)))
        self.assertEqual({r["seq"] for r in res["records"] if r["is_warmup"]}, set(range(6)))

    def test_m2_in_flight_at_send_recorded_and_bounded(self):
        with FakeServer(service_s=0.003) as fs:
            res = self.run_level(fs, concurrency=4, warmup=4, requests=20)
        self.assertTrue(all(1 <= r["in_flight_at_send"] <= 4 for r in res["records"]))

    def test_m2_validate_flags_warmup_shorter_than_n(self):
        with FakeServer(service_s=0.003) as fs:
            res = self.run_level(fs, concurrency=4, warmup=1, requests=20)
        problems = DRIVER.validate_level(res, warmup=1, requests=20)
        self.assertTrue(any("start-up wave" in p for p in problems), problems)

    def test_m3_client_latency_includes_queue_wait(self):
        service = 0.01
        with FakeServer(service_s=service) as fs:
            res = self.run_level(fs, concurrency=8, warmup=8, requests=24)
        summary = DRIVER.summarize_level(res)
        self.assertGreater(summary["client_e2e_s"]["p50"], service * 5)
        self.assertLess(summary["e2e_s"]["p50"], service * 2)

    def test_m4_throughput_window_first_to_last_completion(self):
        service = 0.02
        with FakeServer(service_s=service) as fs:
            res = self.run_level(fs, concurrency=4, warmup=4, requests=30)
        s = DRIVER.summarize_level(res)
        ok = sorted(r["t_end"] for r in res["records"] if not r["is_warmup"] and r["ok"])
        self.assertAlmostEqual(s["requests_per_s"], (len(ok) - 1) / (ok[-1] - ok[0]))
        self.assertAlmostEqual(s["output_tokens_per_s"], s["requests_per_s"] * 128)
        # Serialized stub: the lock is always busy, so ~1 / service_s.
        self.assertGreater(s["requests_per_s"], 0.6 / service)
        self.assertLess(s["requests_per_s"], 1.05 / service)

    def test_m5_failed_run_rerun_once_and_kept(self):
        # Arrival 3 is a warmup request of c=2 run 1; any failure marks the run.
        with FakeServer(service_s=0.002, fail_on={3}) as fs:
            levels = DRIVER.run_sweep(fs.url, self.PROMPTS, levels=(2,), runs=2, requests=6,
                                      warmup_base=4, output_tokens=128, timeout_s=5.0)
            self.assertEqual(fs.received, 3 * 10)
        attempts = [(a["run"], a["attempt"], bool(a["problems"])) for a in levels[0]["attempts"]]
        self.assertEqual(attempts, [(1, 1, True), (2, 1, False), (1, 2, False)])
        agg = levels[0]["across_runs"]
        self.assertEqual(agg["runs_used"], [{"run": 1, "attempt": 2}, {"run": 2, "attempt": 1}])
        self.assertTrue(agg["usable_for_knee"])

    def test_m5_rerun_fails_again_level_flagged(self):
        with FakeServer(service_s=0.002, fail_on={3, 13}) as fs:
            levels = DRIVER.run_sweep(fs.url, self.PROMPTS, levels=(2,), runs=1, requests=6,
                                      warmup_base=4, output_tokens=128, timeout_s=5.0)
        agg = levels[0]["across_runs"]
        self.assertEqual(agg["flagged_runs"], [1])
        self.assertFalse(agg["usable_for_knee"])

    def test_m5_rerun_skipped_after_time_box(self):
        with FakeServer(service_s=0.002, fail_on={3}) as fs:
            levels = DRIVER.run_sweep(fs.url, self.PROMPTS, levels=(2,), runs=1, requests=6,
                                      warmup_base=4, output_tokens=128, timeout_s=5.0,
                                      deadline=time.monotonic() - 1)
        self.assertEqual(len(levels[0]["attempts"]), 1)
        self.assertEqual(levels[0]["reruns_skipped"], [{"run": 1, "reason": "time box reached"}])
        self.assertFalse(levels[0]["across_runs"]["usable_for_knee"])

    def test_m6_spread_gate_on_p50_and_pooled_p99(self):
        with FakeServer(service_s=0.002) as fs:
            levels = DRIVER.run_sweep(fs.url, self.PROMPTS, levels=(1,), runs=3, requests=10,
                                      warmup_base=2, output_tokens=128, timeout_s=5.0)
        agg = levels[0]["across_runs"]
        self.assertEqual(agg["client_e2e_s"]["pooled"]["n"], 30)
        self.assertEqual(len(agg["ttft_s"]["p99"]["per_run"]), 3)
        self.assertIn("spread", agg["ttft_s"]["p99"])
        fake = [{"run": i, "attempt": 1, "problems": [],
                 "summary": {**{k: {"p50": v, "p95": v, "p99": 1.0} for k in DRIVER.LATENCY_KEYS},
                             "requests_per_s": 1.0, "output_tokens_per_s": 128.0},
                 "result": {"records": []}} for i, v in ((1, 1.0), (2, 1.0), (3, 1.5))]
        warnings = DRIVER.aggregate_level(fake, 0.10)["warnings"]
        self.assertTrue(any("client_e2e_s p50 spread" in w for w in warnings), warnings)
        fake[2]["summary"] = {**{k: {"p50": 1.0, "p95": 1.0, "p99": 9.0} for k in DRIVER.LATENCY_KEYS},
                              "requests_per_s": 1.0, "output_tokens_per_s": 128.0}
        self.assertEqual(DRIVER.aggregate_level(fake, 0.10)["warnings"], [], "p99 must not gate")

    def test_m6_throughput_spread_gated(self):
        lat = {k: {"p50": 1.0, "p95": 1.0, "p99": 1.0} for k in DRIVER.LATENCY_KEYS}
        fake = [{"run": i, "attempt": 1, "problems": [],
                 "summary": {**lat, "requests_per_s": v, "output_tokens_per_s": v * 128},
                 "result": {"records": []}} for i, v in ((1, 1.0), (2, 1.0), (3, 1.2))]
        warnings = DRIVER.aggregate_level(fake, 0.10)["warnings"]
        self.assertTrue(any(w.startswith("requests_per_s spread") for w in warnings), warnings)
        self.assertTrue(any(w.startswith("output_tokens_per_s spread") for w in warnings), warnings)

    def test_m9_schedule_rounds_shuffled_and_seeded(self):
        levels = (1, 2, 4, 8, 16, 32, 64)
        rounds = DRIVER.schedule(levels, 3, seed=7)
        self.assertEqual(len(rounds), 3)
        for order in rounds:
            self.assertEqual(sorted(order), list(levels))
        self.assertEqual(rounds, DRIVER.schedule(levels, 3, seed=7))
        self.assertNotEqual(
            {tuple(o) for s in range(20) for o in DRIVER.schedule(levels, 3, seed=s)},
            {levels}, "order never shuffled")

    def test_m9_run_sweep_follows_schedule(self):
        levels, seed = (1, 2, 4), 3
        with FakeServer(service_s=0.002) as fs:
            out = DRIVER.run_sweep(fs.url, self.PROMPTS, levels=levels, runs=3, requests=4,
                                   warmup_base=2, output_tokens=128, timeout_s=5.0, seed=seed)
        self.assertEqual([lv["concurrency"] for lv in out], list(levels))
        executed = sorted(((a["started_at"], lv["concurrency"], a["run"])
                           for lv in out for a in lv["attempts"]))
        expected = [(n, k) for k, order in enumerate(DRIVER.schedule(levels, 3, seed), 1)
                    for n in order]
        self.assertEqual([(n, k) for _, n, k in executed], expected)

    def test_validate_flags_concurrency_exceeded_and_token_mismatch(self):
        with FakeServer(service_s=0.002) as fs:
            res = self.run_level(fs)
        res["max_in_flight"] = 5
        res["records"][10]["server"]["output_tokens"] = 127
        problems = DRIVER.validate_level(res, warmup=4, requests=20)
        self.assertTrue(any("exceeds concurrency" in p for p in problems), problems)
        self.assertTrue(any("output_tokens" in p for p in problems), problems)

    def test_main_writes_report_end_to_end(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp, FakeServer(service_s=0.002) as fs:
            out = pathlib.Path(tmp) / "sweep.json"
            rc = DRIVER.main(["--url", fs.url, "--levels", "1,2", "--runs", "1",
                              "--requests", "4", "--warmup-base", "2", "--seed", "11",
                              "--out", str(out)])
            text = out.read_text()
            report = json.loads(text)
            self.assertFalse(out.with_suffix(".json.tmp").exists())
        self.assertEqual(rc, 0)
        self.assertEqual(report["schema"], "charon-sweep-v1")
        self.assertTrue(report["complete"])
        self.assertEqual([lv["concurrency"] for lv in report["levels"]], [1, 2])
        self.assertEqual(report["config"]["request_timeout_s"], 1800.0)
        self.assertIn("python", report["environment"]["client"])
        self.assertNotIn("\n", text, "results file must be compact JSON [M10]")
        self.assertEqual(report["config"]["seed"], 11)
        self.assertEqual(report["config"]["schedule"], DRIVER.schedule((1, 2), 1, 11))
        for lv in report["levels"]:
            self.assertEqual(lv["attempts"][0]["problems"], [])


if __name__ == "__main__":
    unittest.main()
