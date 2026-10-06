"""Checks for benchmarks/roofline.py — stdlib unittest, no GPU, no new deps.

    python3 -m unittest benchmarks/test_roofline.py

Guards the arithmetic and, more importantly, the labelling: a derived or
hypothetical value must never come out tagged 'measured'.
"""
import json, math, pathlib, sys, tempfile, unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import roofline as rl  # noqa: E402


class Formulas(unittest.TestCase):
    def test_ridge_point(self):
        self.assertAlmostEqual(rl.ridge_point(121e12, 300e9), 403.333, places=3)

    def test_attainable_is_min_of_roofs(self):
        self.assertAlmostEqual(rl.attainable(1.0, 121e12, 300e9), 300e9)
        self.assertEqual(rl.attainable(1e4, 121e12, 300e9), 121e12)

    def test_model_flops(self):
        self.assertAlmostEqual(rl.model_flops_per_s(1.54e9, 34.5), 106.26e9, delta=1e6)

    def test_cost_per_1m_tokens(self):
        for tok_s, inr in ((34.5, 555.56), (50, 383.33), (70, 273.81), (100, 191.67)):
            self.assertAlmostEqual(rl.cost_per_1m_tokens(69, tok_s), inr, places=2)

    def test_duty_cycle_raises_cost(self):
        self.assertGreater(rl.cost_per_1m_tokens(69, 34.5, 0.5), rl.cost_per_1m_tokens(69, 34.5))


class Week1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg, cls.measured = rl.load(rl.DEFAULT_CONFIG)
        cls.v, cls.rows = rl.compute(cls.cfg, cls.measured)

    def val(self, name):
        return self.v[name]["value"]

    def test_measured_values_match_committed_run(self):
        self.assertAlmostEqual(self.val("decode_tokens_per_s"), 34.5, delta=0.05)
        self.assertEqual(self.val("weights_vram_bytes"), 3087429632)

    def test_arithmetic_intensity(self):
        expected = 2 * 1.54e9 / 3087429632
        self.assertAlmostEqual(self.val("arithmetic_intensity"), expected, places=9)
        self.assertAlmostEqual(self.val("arithmetic_intensity"), 1.0, delta=0.01)

    def test_baseline_flops_and_mfu(self):
        self.assertAlmostEqual(self.val("model_flops_per_s") / 1e9, 106.3, delta=0.1)
        self.assertAlmostEqual(self.val("mfu") * 100, 0.088, delta=0.001)

    def test_baseline_sits_below_memory_roof(self):
        self.assertLess(self.val("model_flops_per_s"), self.val("memory_roof_at_ai"))
        self.assertLess(self.val("arithmetic_intensity"), self.val("ridge_point"))

    def test_100_tok_s_exceeds_batch1_roof(self):
        by = {r["tok_s"]: r for r in self.rows}
        self.assertTrue(by[100.0]["above_memory_roof"])
        self.assertFalse(by[70.0]["above_memory_roof"])

    def test_kinds(self):
        for name, item in self.v.items():
            self.assertIn(item["kind"], rl.KINDS, name)
        for name in ("arithmetic_intensity", "ridge_point", "model_flops_per_s", "mfu",
                     "weight_traffic_rate", "bytes_per_token", "memory_roof_at_ai"):
            self.assertEqual(self.v[name]["kind"], "derived", name)
        for name in ("peak_bf16_flops", "memory_bandwidth"):
            self.assertEqual(self.v[name]["kind"], "datasheet", name)
        self.assertEqual(self.v["gpu_cost_inr_per_hour"]["kind"], "assumption")
        measured = {k for k, i in self.v.items() if i["kind"] == "measured"}
        self.assertEqual(measured, set(self.cfg["measured"]))

    def test_weight_traffic_never_called_measured_bandwidth(self):
        item = self.v["weight_traffic_rate"]
        self.assertEqual(item["kind"], "derived")
        self.assertIn("NOT measured", item["basis"])

    def test_only_the_run_is_measured_in_scenarios(self):
        self.assertEqual([r["kind"] for r in self.rows].count("measured"), 1)
        self.assertTrue(all(r["kind"] == "hypothetical" for r in self.rows[1:]))

    def test_inline_measured_value_rejected(self):
        cfg = json.loads(rl.DEFAULT_CONFIG.read_text())
        cfg["measured"]["decode_tokens_per_s"]["value"] = 99.0
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(cfg, f)
        with self.assertRaises(ValueError):
            rl.load(f.name)
        pathlib.Path(f.name).unlink()

    def test_svg_renders(self):
        svg = rl.render_svg(self.cfg, self.v, self.rows)
        self.assertTrue(svg.startswith("<svg") and svg.endswith("</svg>"))
        self.assertIn("hypothetical", svg)
        self.assertFalse(any(math.isnan(r["flops_per_s"]) for r in self.rows))


if __name__ == "__main__":
    unittest.main()
