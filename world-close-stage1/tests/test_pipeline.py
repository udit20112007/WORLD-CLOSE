"""Run with:  python -m unittest discover tests"""
import datetime as dt
import importlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

FIX = Path(__file__).parent / "fixtures"


class ParserTests(unittest.TestCase):
    def setUp(self):
        from pipeline.common import load_config
        self.cfg = load_config()

    def test_nse_udiff(self):
        from pipeline.common import read_csv_maybe_zipped
        from pipeline.sources import nse
        df = nse.parse(read_csv_maybe_zipped((FIX / "nse_udiff.csv.zip").read_bytes()), self.cfg["NSE"])
        self.assertEqual(sorted(df.symbol), ["RELIANCE", "SMALLCO", "SMEFIRM", "TCS"])  # GS and bonds dropped
        r = df.set_index("symbol").loc["RELIANCE"]
        self.assertAlmostEqual(r.close, 1415.2)
        self.assertAlmostEqual(r.prev_close, 1402)
        self.assertEqual(r["isin"], "INE002A01018")
        self.assertEqual(r["name"], "RELIANCE INDUSTRIES LTD")

    def test_nse_legacy_columns(self):
        from pipeline.common import read_csv_maybe_zipped
        from pipeline.sources import nse
        df = nse.parse(read_csv_maybe_zipped((FIX / "nse_legacy.csv").read_bytes()), self.cfg["NSE"])
        self.assertEqual(list(df.symbol), ["INFY"])
        self.assertAlmostEqual(df.iloc[0].close, 1505.3)

    def test_bse_udiff(self):
        from pipeline.common import read_csv_maybe_zipped
        from pipeline.sources import bse
        df = bse.parse(read_csv_maybe_zipped((FIX / "bse_udiff.csv").read_bytes()), self.cfg["BSE"])
        self.assertEqual(sorted(df.symbol), ["RELIANCE", "TCS", "TINYCO"])  # debt group F dropped
        tiny = df.set_index("symbol").loc["TINYCO"]
        self.assertAlmostEqual(tiny.close, 2.15)  # duplicate line: kept the more traded one

    def test_unknown_format_is_a_clear_error(self):
        import pandas as pd
        from pipeline.sources import nse
        with self.assertRaisesRegex(ValueError, "Unrecognised file format"):
            nse.parse(pd.DataFrame({"foo": ["1"], "bar": ["2"]}), self.cfg["NSE"])


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["WC_DATA_DIR"] = str(self.tmp / "data")
        import pipeline.store, pipeline.build_site, pipeline.run
        importlib.reload(pipeline.store)
        importlib.reload(pipeline.build_site)
        importlib.reload(pipeline.run)
        pipeline.build_site.SITE_DATA = self.tmp / "site_data"
        self.store, self.build_site, self.run = pipeline.store, pipeline.build_site, pipeline.run

    def tearDown(self):
        shutil.rmtree(self.tmp)
        os.environ.pop("WC_DATA_DIR", None)

    def _fake_fetch(self, fixture, holidays=(), broken=()):
        from pipeline.common import NotPublished, read_csv_maybe_zipped
        from pipeline.sources import SOURCES
        import pandas as pd

        def fetch(day, cfg):
            if day in holidays:
                raise NotPublished(str(day))
            if day in broken:
                raise RuntimeError("HTTP 403")
            df = SOURCES[cfg["source"]].parse(read_csv_maybe_zipped((FIX / fixture).read_bytes()), cfg)
            # make 60 rows and a price that drifts by day so history is visible
            rows = pd.concat([df] * 15, ignore_index=True)
            rows["symbol"] = rows["symbol"] + rows.index.astype(str)
            rows["isin"] = rows["isin"] + rows.index.astype(str)
            bump = 1 + day.toordinal() % 7 / 100
            for c in ["open", "high", "low", "close"]:
                rows[c] = rows[c] * bump
            return rows
        return fetch

    def test_update_skips_holidays_and_records_errors(self):
        cfg = self.run.load_config()["NSE"]
        today = dt.date(2026, 10, 23)
        days = self.run.candidate_days(set(), today, 0)
        self.assertTrue(all(d.weekday() < 5 for d in days))
        holiday, broken = days[1], days[2]
        src = self.run.SOURCES["nse"]
        with mock.patch.object(src, "fetch", self._fake_fetch("nse_udiff.csv.zip", {holiday}, {broken})), \
             mock.patch.object(self.run, "candidate_days", lambda have, t, b: [d for d in days if d not in have]), \
             mock.patch.object(self.run.time, "sleep", lambda s: None):
            ok = self.run.update_exchange("NSE", cfg, 0)
        self.assertTrue(ok)
        stored = self.store.stored_days("NSE")
        self.assertNotIn(holiday, stored)
        self.assertNotIn(broken, stored)
        self.assertEqual(len(stored), len(days) - 2)
        status = self.store.read_status("NSE")
        self.assertEqual(len(status["errors"]), 1)
        self.assertIn("403", status["errors"][0])

    def test_stops_after_repeated_failures(self):
        cfg = self.run.load_config()["BSE"]
        days = [dt.date(2026, 10, d) for d in (12, 13, 14, 15, 16, 19, 20, 21)]
        src = self.run.SOURCES["bse"]
        with mock.patch.object(src, "fetch", self._fake_fetch("bse_udiff.csv", broken=set(days))), \
             mock.patch.object(self.run, "candidate_days", lambda *a: days), \
             mock.patch.object(self.run.time, "sleep", lambda s: None):
            ok = self.run.update_exchange("BSE", cfg, 0)
        self.assertFalse(ok)
        self.assertIn("Stopped after 5", self.store.read_status("BSE")["errors"][-1])

    def test_build_outputs(self):
        cfg = self.run.load_config()
        days = [dt.date(2026, 10, d) for d in (19, 20, 21, 22, 23)]
        for code, fixture in [("NSE", "nse_udiff.csv.zip"), ("BSE", "bse_udiff.csv")]:
            fetch = self._fake_fetch(fixture)
            for d in days:
                self.store.save_day(code, d, fetch(d, cfg[code]))
        self.build_site.build()
        out = self.build_site.SITE_DATA
        index = json.loads((out / "exchanges.json").read_text())
        self.assertEqual([e["code"] for e in index["exchanges"]], ["NSE", "BSE"])
        s = json.loads((out / "NSE" / "summary.json").read_text())
        self.assertEqual(s["as_of"], "2026-10-23")
        f = {k: i for i, k in enumerate(s["fields"])}
        rel = next(r for r in s["rows"] if r[0] == "RELIANCE0")
        self.assertEqual(rel[f["also"]], ["BSE"])                    # same ISIN on BSE
        self.assertEqual(rel[f["days_ago"]], 0)
        self.assertGreaterEqual(rel[f["high_52w"]], rel[f["close"]])
        h = json.loads((out / "NSE" / "hist" / f"{rel[f['bucket']]}.json").read_text())
        self.assertEqual(len(h["series"]["RELIANCE0"]["c"]), 5)


if __name__ == "__main__":
    unittest.main()
