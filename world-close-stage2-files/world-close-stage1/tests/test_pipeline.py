"""Run with:  python -m unittest discover tests"""
import datetime as dt
import importlib
import json
import os
import shutil
import sys
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
        self.assertEqual([e["code"] for e in index["exchanges"] if e["available"]], ["NSE", "BSE"])
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


class USTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["WC_DATA_DIR"] = str(self.tmp / "data")
        import pipeline.store, pipeline.build_site, pipeline.run
        importlib.reload(pipeline.store)
        importlib.reload(pipeline.build_site)
        importlib.reload(pipeline.run)
        pipeline.build_site.SITE_DATA = self.tmp / "site_data"
        self.store, self.build_site, self.run = pipeline.store, pipeline.build_site, pipeline.run
        self.cfg = self.run.load_config()
        self.payload = json.loads((FIX / "nasdaq_screener.json").read_text())

    def tearDown(self):
        shutil.rmtree(self.tmp)
        os.environ.pop("WC_DATA_DIR", None)

    def test_parse_screener(self):
        from pipeline.sources import nasdaq
        df = nasdaq.parse(self.payload, self.cfg["NASDAQ"]).set_index("symbol")
        self.assertNotIn("NOPRICE", df.index)                       # no price: dropped
        self.assertAlmostEqual(df.at["AAPL", "close"], 262.24)
        self.assertAlmostEqual(df.at["AAPL", "prev_close"], 259.13)  # last minus net change
        self.assertAlmostEqual(df.at["MSFT", "prev_close"], 524.40)
        self.assertEqual(df.at["AAPL", "market_cap"], 3_891_232_000_000)
        self.assertEqual(df.at["AAPL", "sector"], "Technology")
        self.assertTrue(pd_isna(df.at["XYZU", "market_cap"]))       # 0.00 means unknown
        self.assertEqual(df.at["ABCDW", "series"], "Warrant")
        self.assertEqual(df.at["XYZU", "series"], "Unit")
        self.assertEqual(df.at["BAC^K", "series"], "Preferred")
        self.assertEqual(df.at["TSM", "series"], "ADR")
        self.assertEqual(df.at["AAPL", "series"], "Common")
        self.assertEqual(nasdaq.to_yahoo("BRK/B"), "BRK-B")
        self.assertEqual(nasdaq.to_yahoo("BAC^K"), "BAC-PK")

    def test_bad_response_is_clear(self):
        from pipeline.sources import nasdaq
        with self.assertRaisesRegex(ValueError, "Unrecognised screener response"):
            nasdaq.parse({"data": None, "status": {"rCode": 400}}, self.cfg["NYSE"])

    def test_session_day(self):
        from zoneinfo import ZoneInfo
        ny, cfg = ZoneInfo("America/New_York"), self.cfg["NYSE"]
        at = lambda y, m, d, h, mi: dt.datetime(y, m, d, h, mi, tzinfo=ny)
        self.assertIsNone(self.run.session_day(cfg, at(2026, 10, 23, 11, 0)))       # market open
        self.assertIsNone(self.run.session_day(cfg, at(2026, 10, 23, 16, 10)))      # just closed
        self.assertEqual(self.run.session_day(cfg, at(2026, 10, 23, 19, 0)), dt.date(2026, 10, 23))
        self.assertEqual(self.run.session_day(cfg, at(2026, 10, 25, 9, 0)), dt.date(2026, 10, 23))  # Sunday

    def _run_latest(self, when, payload=None):
        from pipeline.sources import nasdaq
        cfg = self.cfg["NASDAQ"]
        with mock.patch.object(self.run, "local_now", lambda tz: when), \
             mock.patch.object(nasdaq, "fetch", lambda day, c: nasdaq.parse(payload or self._bigger(), c)):
            return self.run.update_exchange("NASDAQ", cfg, 0)

    def _bigger(self, bump=0.0):
        p = json.loads(json.dumps(self.payload))
        base = p["data"]["rows"][0]
        p["data"]["rows"] += [{**base, "symbol": f"S{i:03d}", "lastsale": f"${10 + i + bump:.2f}",
                               "volume": str(1000 + i + int(bump * 100))} for i in range(60)]
        return p

    def test_latest_only_saves_then_detects_holiday(self):
        from zoneinfo import ZoneInfo
        ny = ZoneInfo("America/New_York")
        self.assertTrue(self._run_latest(dt.datetime(2026, 10, 22, 19, 0, tzinfo=ny), self._bigger(0)))
        self.assertEqual(self.store.stored_days("NASDAQ"), [dt.date(2026, 10, 22)])
        # Next day the screener still shows the same session (a holiday): nothing saved
        self._run_latest(dt.datetime(2026, 10, 23, 19, 0, tzinfo=ny), self._bigger(0))
        self.assertEqual(self.store.stored_days("NASDAQ"), [dt.date(2026, 10, 22)])
        self.assertIn("holiday", " ".join(self.store.read_status("NASDAQ")["notes"]))
        # A real new session is saved
        self._run_latest(dt.datetime(2026, 10, 26, 19, 0, tzinfo=ny), self._bigger(0.5))
        self.assertEqual(self.store.stored_days("NASDAQ")[-1], dt.date(2026, 10, 26))
        # During market hours nothing is saved
        self._run_latest(dt.datetime(2026, 10, 27, 11, 0, tzinfo=ny), self._bigger(1.0))
        self.assertNotIn(dt.date(2026, 10, 27), self.store.stored_days("NASDAQ"))

    def test_backfill_merges_without_overwriting(self):
        import pandas as pd
        from pipeline.sources import nasdaq
        from zoneinfo import ZoneInfo
        self._run_latest(dt.datetime(2026, 10, 23, 19, 0, tzinfo=ny_tz()), self._bigger(0))
        latest = self.store.load_day("NASDAQ", dt.date(2026, 10, 23))
        # An existing earlier day that already has AAPL
        self.store.save_day("NASDAQ", dt.date(2026, 10, 21), latest[latest.symbol == "AAPL"].assign(close=111.0))

        days_idx = pd.bdate_range("2026-10-19", "2026-10-22")
        def fake_download(tickers, **kw):
            import numpy as np
            cols, data = [], []
            for t in tickers:
                if t == "ABCDW":
                    raise AssertionError("warrants should not be requested")
                for f in ["Open", "High", "Low", "Close", "Adj Close", "Volume"]:
                    cols.append((t, f)); data.append(np.linspace(50, 53, len(days_idx)))
            return pd.DataFrame(np.array(data).T, index=days_idx, columns=pd.MultiIndex.from_tuples(cols))
        fake_yf = mock.Mock(download=fake_download)
        cfg = self.cfg["NASDAQ"]
        with mock.patch.dict(sys.modules, {"yfinance": fake_yf}), \
             mock.patch.object(nasdaq.time, "sleep", lambda s: None), \
             mock.patch.object(self.run, "local_now", lambda tz: dt.datetime(2026, 10, 23, 19, 0, tzinfo=ny_tz())):
            self.run.update_latest_only("NASDAQ", cfg, nasdaq, 7)
        stored = self.store.stored_days("NASDAQ")
        self.assertEqual(stored, [dt.date(2026, 10, d) for d in (19, 20, 21, 22, 23)])
        d21 = self.store.load_day("NASDAQ", dt.date(2026, 10, 21)).set_index("symbol")
        self.assertEqual(d21.at["AAPL", "close"], 111.0)              # existing row kept
        self.assertIn("MSFT", d21.index)                               # missing stock added
        self.assertIn("BRK/B", d21.index)                              # mapped back from BRK-B
        self.assertIn("Backfill", " ".join(self.store.read_status("NASDAQ")["notes"]))

    def test_india_files_without_new_columns_still_load(self):
        import pandas as pd
        path = self.store.day_file("NSE", dt.date(2026, 10, 23))
        path.parent.mkdir(parents=True)
        pd.DataFrame([{"symbol": "INFY", "name": "Infosys", "isin": "INE009A01021", "series": "EQ", "open": 1, "high": 2,
                       "low": 1, "close": 1.5, "prev_close": 1.4, "volume": 10, "value": 15, "trades": 1}]
                     ).to_csv(path, index=False, compression="gzip")
        df = self.store.load_days("NSE", dt.date(2026, 1, 1))
        self.assertEqual(df.iloc[0]["sector"], "")
        self.build_site.build()
        s = json.loads((self.build_site.SITE_DATA / "NSE" / "summary.json").read_text())
        self.assertIn("market_cap", s["fields"])


def pd_isna(v):
    import pandas as pd
    return pd.isna(v)


def ny_tz():
    from zoneinfo import ZoneInfo
    return ZoneInfo("America/New_York")
