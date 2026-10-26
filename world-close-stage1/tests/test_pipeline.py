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
        self.assertEqual(self.run.session_day(cfg, at(2026, 10, 23, 3, 0)), dt.date(2026, 10, 22))  # before open
        self.assertEqual(self.run.session_day(cfg, at(2026, 10, 26, 2, 0)), dt.date(2026, 10, 23))  # Monday pre-open

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
             mock.patch("pipeline.yahoo.time.sleep", lambda s: None), \
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


class Stage3Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["WC_DATA_DIR"] = str(self.tmp / "data")
        os.environ.pop("KRX_OPENAPI_KEY", None)
        import pipeline.store, pipeline.build_site, pipeline.run
        importlib.reload(pipeline.store)
        importlib.reload(pipeline.build_site)
        importlib.reload(pipeline.run)
        pipeline.build_site.SITE_DATA = self.tmp / "site_data"
        self.store, self.build_site, self.run = pipeline.store, pipeline.build_site, pipeline.run
        self.cfg = self.run.load_config()

    def tearDown(self):
        shutil.rmtree(self.tmp)
        os.environ.pop("WC_DATA_DIR", None)
        os.environ.pop("KRX_OPENAPI_KEY", None)

    # ---- China / Hong Kong (East Money via AKShare)
    def _em_frame(self, hk=False):
        import pandas as pd
        rows = [
            {"代码": "600519", "名称": "贵州茅台", "最新价": 1450.0, "涨跌额": 12.0, "今开": 1440.0, "最高": 1455.0,
             "最低": 1436.0, "昨收": 1438.0, "成交量": 31000, "成交额": 4.5e9, "总市值": 1.82e12},
            {"代码": "688981", "名称": "中芯国际", "最新价": 95.5, "涨跌额": -1.2, "今开": 96.0, "最高": 97.0,
             "最低": 94.8, "昨收": 96.7, "成交量": 520000, "成交额": 5.0e9, "总市值": 7.6e11},
            {"代码": "600000", "名称": "停牌股", "最新价": float("nan"), "涨跌额": float("nan"), "今开": float("nan"),
             "最高": float("nan"), "最低": float("nan"), "昨收": 9.8, "成交量": 0, "成交额": 0, "总市值": 2.9e11},
        ]
        if hk:
            rows = [{"代码": "00700", "名称": "腾讯控股", "最新价": 620.0, "涨跌额": 5.0, "今开": 615.0, "最高": 625.0,
                     "最低": 612.0, "昨收": 615.0, "成交量": 15000000, "成交额": 9.3e9},
                    {"代码": "08001", "名称": "GEM股", "最新价": 0.25, "涨跌额": 0.0, "今开": 0.25, "最高": 0.26,
                     "最低": 0.24, "昨收": 0.25, "成交量": 100000, "成交额": 25000}]
        return pd.DataFrame(rows)

    def test_eastmoney_china(self):
        from pipeline.sources import eastmoney
        df = eastmoney.parse(self._em_frame(), self.cfg["SSE"]).set_index("symbol")
        self.assertNotIn("600000", df.index)                          # suspended: no price
        self.assertEqual(df.at["600519", "volume"], 3_100_000)        # lots of 100 -> shares
        self.assertEqual(df.at["600519", "prev_close"], 1438.0)
        self.assertEqual(df.at["600519", "series"], "Main Board")
        self.assertEqual(df.at["688981", "series"], "STAR Market")
        self.assertEqual(df.at["600519", "market_cap"], 1.82e12)
        self.assertEqual(eastmoney.to_yahoo_for("sh_a")("600519"), "600519.SS")
        self.assertEqual(eastmoney.to_yahoo_for("sz_a")("000001"), "000001.SZ")

    def test_eastmoney_hong_kong(self):
        from pipeline.sources import eastmoney
        df = eastmoney.parse(self._em_frame(hk=True), self.cfg["HKEX"]).set_index("symbol")
        self.assertEqual(df.at["00700", "volume"], 15_000_000)        # HK volumes are already shares
        self.assertEqual(df.at["08001", "series"], "GEM")
        self.assertTrue(pd_isna(df.at["00700", "market_cap"]))
        self.assertEqual(eastmoney.to_yahoo_for("hk")("00700"), "0700.HK")

    # ---- Taiwan
    def test_twse(self):
        from pipeline.sources import twse
        rows = json.loads((FIX / "twse_stock_day_all.json").read_text())
        df = twse.parse(rows, self.cfg["TWSE"])
        self.assertEqual(df.attrs["session_date"], dt.date(2026, 10, 23))   # ROC 115 = 2026
        d = df.set_index("symbol")
        self.assertNotIn("9999", d.index)
        self.assertAlmostEqual(d.at["2330", "prev_close"], 1035.0)
        self.assertAlmostEqual(d.at["2317", "prev_close"], 215.0)
        self.assertEqual(d.at["0050", "series"], "ETF")
        self.assertEqual(d.at["2330", "trades"], 51234)

    def test_session_date_from_source_wins(self):
        from pipeline.sources import twse
        rows = json.loads((FIX / "twse_stock_day_all.json").read_text())
        rows = rows * 20
        for i, r in enumerate(rows):
            r = rows[i] = dict(r, Code=f"{i:04d}")
        cfg = self.cfg["TWSE"]
        tw = ZoneInfoT("Asia/Taipei")
        # Run on Monday evening, but the source still says Friday (e.g. Monday was a holiday)
        with mock.patch.object(self.run, "local_now", lambda tz: dt.datetime(2026, 10, 26, 19, 0, tzinfo=tw)), \
             mock.patch.object(twse, "fetch", lambda day, c: twse.parse(rows, c)), \
             mock.patch.object(self.run, "refresh_names", lambda code, c: None):   # no network in tests
            self.run.update_exchange("TWSE", cfg, 0)
        self.assertEqual(self.store.stored_days("TWSE"), [dt.date(2026, 10, 23)])

    # ---- Korea
    def test_krx_parse(self):
        from pipeline.sources import krx
        df = krx.parse(json.loads((FIX / "krx_stk_bydd_trd.json").read_text()), self.cfg["KOSPI"]).set_index("symbol")
        self.assertEqual(df.at["005930", "close"], 98500)
        self.assertEqual(df.at["005930", "prev_close"], 97000)
        self.assertEqual(df.at["000660", "prev_close"], 314000)
        self.assertEqual(df.at["005930", "volume"], 15_234_567)
        self.assertEqual(df.at["005930", "market_cap"], 588_000_000_000_000)
        self.assertEqual(df.at["005930", "series"], "Stock")

    def test_krx_empty_day_and_bad_response(self):
        from pipeline.common import NotPublished
        from pipeline.sources import krx
        with self.assertRaises(NotPublished):
            krx.parse({"OutBlock_1": []}, self.cfg["KOSPI"])
        with self.assertRaisesRegex(ValueError, "Unrecognised KRX response"):
            krx.parse({"respMsg": "Unauthorized API Call"}, self.cfg["KOSPI"])

    def _krx_cfg(self):
        return {**self.cfg["KOSPI"], "source": "krx"}

    def test_krx_without_key_needs_setup(self):
        ok = self.run.update_exchange("KOSPI", self._krx_cfg(), 0)
        self.assertFalse(ok)
        errs = self.store.read_status("KOSPI")["errors"]
        self.assertEqual(len(errs), 1)                                # stops at once, no retry storm
        self.assertIn("KRX_OPENAPI_KEY", errs[0])

    def test_krx_key_never_appears_in_errors(self):
        from pipeline.sources import krx
        os.environ["KRX_OPENAPI_KEY"] = "SECRETKEY123"
        def boom(sess, url, **kw):
            raise RuntimeError(f"Download failed after 3 tries: {url} (HTTP 500)")
        with mock.patch.object(krx, "get_bytes", boom), mock.patch.object(krx, "_session", None), \
             mock.patch.object(self.run.time, "sleep", lambda s: None):
            self.run.update_exchange("KOSPI", self._krx_cfg(), 0)
        status = json.dumps(self.store.read_status("KOSPI"))
        self.assertNotIn("SECRETKEY123", status)
        self.assertIn("***", status)

    # ---- Brazil
    def test_b3_daily(self):
        from pipeline.sources import b3
        blob = (FIX / "b3_cotahist_daily.zip").read_bytes()
        with mock.patch.object(b3, "_get", lambda url: blob):
            df = b3.fetch(dt.date(2026, 10, 23), self.cfg["B3"]).set_index("symbol")
        self.assertEqual(sorted(df.index), ["PETR4", "VALE3"])         # option and odd lot dropped
        self.assertAlmostEqual(df.at["PETR4", "close"], 31.40)
        self.assertAlmostEqual(df.at["PETR4", "open"], 30.51)
        self.assertEqual(df.at["PETR4", "volume"], 37_774_500)
        self.assertEqual(df.at["PETR4", "isin"], "BRPETRACNPR6")
        self.assertEqual(df.at["PETR4", "series"], "PN")
        self.assertEqual(df.at["PETR4", "name"], "PETROBRAS")

    def test_b3_range_backfill_and_prev_close(self):
        from pipeline.sources import b3
        annual = (FIX / "b3_cotahist_annual.zip").read_bytes()
        daily = (FIX / "b3_cotahist_daily.zip").read_bytes()
        get = lambda url: annual if "_A" in url else daily
        cfg = self.cfg["B3"]
        with mock.patch.object(b3, "_get", get), mock.patch.object(self.run, "MIN_ROWS", 1), \
             mock.patch.object(self.run.time, "sleep", lambda s: None), \
             mock.patch.object(self.run, "local_now", lambda tz: dt.datetime(2026, 10, 23, 22, 0, tzinfo=ZoneInfoT(tz))):
            self.run.update_exchange("B3", cfg, 5)
        self.assertEqual(self.store.stored_days("B3"), [dt.date(2026, 10, d) for d in (21, 22, 23)])
        d22 = self.store.load_day("B3", dt.date(2026, 10, 22)).set_index("symbol")
        self.assertAlmostEqual(d22.at["PETR4", "prev_close"], 30.0)
        self.assertIn("Backfill", " ".join(self.store.read_status("B3")["notes"]))

    def test_daily_prev_close_filled_from_store(self):
        from pipeline.sources import b3
        daily = (FIX / "b3_cotahist_daily.zip").read_bytes()
        import pandas as pd
        prev = b3._standard(b3.parse_lines([]).reindex(columns=[])) if False else None
        # A stored previous day with PETR4 at 30.6
        with mock.patch.object(b3, "_get", lambda url: daily):
            today = b3.fetch(dt.date(2026, 10, 23), self.cfg["B3"])
        self.store.save_day("B3", dt.date(2026, 10, 22), today.assign(close=30.6))
        filled = self.run.fill_prev_close("B3", dt.date(2026, 10, 23), today).set_index("symbol")
        self.assertAlmostEqual(filled.at["PETR4", "prev_close"], 30.6)

    def test_all_exchanges_build(self):
        self.build_site.build()
        index = json.loads((self.build_site.SITE_DATA / "exchanges.json").read_text())
        codes = [e["code"] for e in index["exchanges"]]
        for code in ["SSE", "SZSE", "HKEX", "TWSE", "KOSPI", "KOSDAQ", "B3"]:
            self.assertIn(code, codes)


def ZoneInfoT(name):
    from zoneinfo import ZoneInfo
    return ZoneInfo(name)


class SinaTests(unittest.TestCase):
    def setUp(self):
        from pipeline.common import load_config
        from pipeline.sources import eastmoney
        self.cfg, self.em = load_config(), eastmoney
        eastmoney._sina_a_cache = None

    def _sina_a(self, lots=False):
        import pandas as pd
        f = 1 / 100 if lots else 1
        return pd.DataFrame([
            {"代码": "sh600519", "名称": "贵州茅台", "最新价": 1450.0, "涨跌额": 12.0, "涨跌幅": 0.83, "买入": 1449.9,
             "卖出": 1450.0, "昨收": 1438.0, "今开": 1440.0, "最高": 1455.0, "最低": 1436.0,
             "成交量": 3100000 * f, "成交额": 4.495e9, "时间戳": "15:00:00"},
            {"代码": "sz000001", "名称": "平安银行", "最新价": 11.2, "涨跌额": 0.1, "涨跌幅": 0.9, "买入": 11.19,
             "卖出": 11.2, "昨收": 11.1, "今开": 11.1, "最高": 11.3, "最低": 11.05,
             "成交量": 90000000 * f, "成交额": 1.008e9, "时间戳": "15:00:00"},
            {"代码": "sz300750", "名称": "宁德时代", "最新价": 260.0, "涨跌额": -2.0, "涨跌幅": -0.76, "买入": 259.9,
             "卖出": 260.0, "昨收": 262.0, "今开": 262.0, "最高": 263.0, "最低": 258.0,
             "成交量": 20000000 * f, "成交额": 5.2e9, "时间戳": "15:00:00"},
            {"代码": "bj830799", "名称": "北交所股", "最新价": 20.0, "涨跌额": 0.0, "涨跌幅": 0.0, "买入": 20.0,
             "卖出": 20.0, "昨收": 20.0, "今开": 20.0, "最高": 20.0, "最低": 20.0,
             "成交量": 1000 * f, "成交额": 20000, "时间戳": "15:00:00"},
        ])

    def test_sina_a_shares_split_by_exchange_and_cached(self):
        calls = []
        fake = mock.Mock(stock_zh_a_spot=lambda: calls.append(1) or self._sina_a())
        with mock.patch.dict(sys.modules, {"akshare": fake}):
            sh = self.em.fetch(dt.date(2026, 10, 23), self.cfg["SSE"]).set_index("symbol")
            sz = self.em.fetch(dt.date(2026, 10, 23), self.cfg["SZSE"]).set_index("symbol")
        self.assertEqual(list(sh.index), ["600519"])
        self.assertEqual(sorted(sz.index), ["000001", "300750"])          # Beijing listing excluded
        self.assertEqual(sz.at["300750", "series"], "ChiNext")
        self.assertEqual(sh.at["600519", "volume"], 3_100_000)            # already shares: unchanged
        self.assertEqual(sh.attrs["provider"], "sina")
        self.assertEqual(len(calls), 1)                                    # one download for both exchanges

    def test_volume_in_lots_is_detected(self):
        fake = mock.Mock(stock_zh_a_spot=lambda: self._sina_a(lots=True))
        with mock.patch.dict(sys.modules, {"akshare": fake}):
            sh = self.em.fetch(dt.date(2026, 10, 23), self.cfg["SSE"]).set_index("symbol")
        self.assertEqual(sh.at["600519", "volume"], 3_100_000)

    def test_sina_hong_kong_english_names_and_date(self):
        import pandas as pd
        hk = pd.DataFrame([
            {"日期时间": "2026/10/23 16:08:10", "代码": "00700", "中文名称": "腾讯控股", "英文名称": "TENCENT",
             "交易类型": "EQTY", "最新价": 620.0, "涨跌额": 5.0, "涨跌幅": 0.81, "昨收": 615.0, "今开": 615.0,
             "最高": 625.0, "最低": 612.0, "成交量": 15000000, "成交额": 9.3e9, "买一": 619.5, "卖一": 620.0},
            {"日期时间": "2026/10/23 16:08:10", "代码": "08001", "中文名称": "创业板股", "英文名称": "GEM CO",
             "交易类型": "EQTY", "最新价": 0.25, "涨跌额": 0.0, "涨跌幅": 0.0, "昨收": 0.25, "今开": 0.25,
             "最高": 0.26, "最低": 0.24, "成交量": 100000, "成交额": 25000, "买一": 0.24, "卖一": 0.25},
        ])
        fake = mock.Mock(stock_hk_spot=lambda: hk)
        with mock.patch.dict(sys.modules, {"akshare": fake}):
            df = self.em.fetch(dt.date(2026, 10, 26), self.cfg["HKEX"])
        self.assertEqual(df.attrs["session_date"], dt.date(2026, 10, 23))
        d = df.set_index("symbol")
        self.assertEqual(d.at["00700", "name"], "TENCENT")
        self.assertEqual(d.at["08001", "series"], "GEM")

    def test_falls_back_to_east_money(self):
        import pandas as pd
        def sina_blocked():
            raise ConnectionError("Remote end closed connection without response")
        em = pd.DataFrame([{"代码": "600519", "名称": "贵州茅台", "最新价": 1450.0, "今开": 1440.0, "最高": 1455.0,
                            "最低": 1436.0, "昨收": 1438.0, "成交量": 31000, "成交额": 4.495e9, "总市值": 1.82e12}])
        fake = mock.Mock(stock_zh_a_spot=sina_blocked, stock_sh_a_spot_em=lambda: em)
        with mock.patch.dict(sys.modules, {"akshare": fake}):
            df = self.em.fetch(dt.date(2026, 10, 23), self.cfg["SSE"])
        self.assertEqual(df.attrs["provider"], "eastmoney")
        self.assertEqual(df.iloc[0]["market_cap"], 1.82e12)

    def test_all_providers_failing_is_one_clear_error(self):
        def blocked():
            raise ConnectionError("Remote end closed connection")
        fake = mock.Mock(stock_zh_a_spot=blocked, stock_sh_a_spot_em=blocked)
        with mock.patch.dict(sys.modules, {"akshare": fake}):
            with self.assertRaisesRegex(RuntimeError, "all providers failed; sina: .* eastmoney: "):
                self.em.fetch(dt.date(2026, 10, 23), self.cfg["SSE"])


class YahooScreenAndNamesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["WC_DATA_DIR"] = str(self.tmp / "data")
        import pipeline.store, pipeline.build_site, pipeline.run, pipeline.names
        for m in (pipeline.store, pipeline.names, pipeline.build_site, pipeline.run):
            importlib.reload(m)
        pipeline.build_site.SITE_DATA = self.tmp / "site_data"
        self.store, self.build_site, self.run, self.names = pipeline.store, pipeline.build_site, pipeline.run, pipeline.names
        self.cfg = self.run.load_config()

    def tearDown(self):
        shutil.rmtree(self.tmp)
        os.environ.pop("WC_DATA_DIR", None)

    @staticmethod
    def _korea_quotes(n=60):
        # 2026-10-23 15:30 KST = 06:30 UTC
        t = int(dt.datetime(2026, 10, 23, 6, 30, tzinfo=dt.timezone.utc).timestamp())
        base = [
            {"symbol": "005930.KS", "shortName": "SamsungElec", "longName": "Samsung Electronics Co., Ltd.",
             "regularMarketPrice": 98500.0, "regularMarketPreviousClose": 97000.0, "regularMarketOpen": 97200.0,
             "regularMarketDayHigh": 99000.0, "regularMarketDayLow": 96800.0, "regularMarketVolume": 15234567,
             "marketCap": 588e12, "regularMarketTime": t},
            {"symbol": "000660.KS", "shortName": "SK hynix", "regularMarketPrice": 310000.0,
             "regularMarketPreviousClose": 314000.0, "regularMarketVolume": 3000000, "marketCap": 225.7e12,
             "regularMarketTime": t},
        ]
        extra = [{"symbol": f"{100000 + i}.KS", "longName": f"Company {i} Co., Ltd.", "regularMarketPrice": 1000.0 + i,
                  "regularMarketPreviousClose": 1000.0, "regularMarketVolume": 1000 + i, "regularMarketTime": t}
                 for i in range(n)]
        return base + extra

    def test_parse_korea(self):
        from pipeline.sources import yahoo_screen
        df = yahoo_screen.parse(self._korea_quotes(), self.cfg["KOSPI"])
        self.assertEqual(df.attrs["session_date"], dt.date(2026, 10, 23))
        d = df.set_index("symbol")
        self.assertEqual(d.at["005930", "name"], "Samsung Electronics Co., Ltd.")
        self.assertEqual(d.at["000660", "name"], "SK hynix")                    # falls back to shortName
        self.assertEqual(d.at["005930", "close"], 98500)
        self.assertEqual(d.at["005930", "prev_close"], 97000)
        self.assertEqual(d.at["005930", "market_cap"], 588e12)
        self.assertEqual(d.at["005930", "value"], round(98500 * 15234567))

    def test_screen_all_pages_through_everything(self):
        from pipeline.sources import yahoo_screen
        everything = [{"symbol": f"{i:06d}.KS"} for i in range(600)]
        calls = []
        def screen(query, offset=0, size=250, **kw):
            calls.append(offset)
            return {"quotes": everything[offset:offset + size], "total": len(everything)}
        fake = mock.Mock(screen=screen, EquityQuery=lambda *a: ("eq", a), ETFQuery=lambda *a: ("etf", a))
        with mock.patch.dict(sys.modules, {"yfinance": fake}), mock.patch.object(yahoo_screen.time, "sleep", lambda s: None):
            got = yahoo_screen.screen_all("KSC")
        self.assertEqual(len(got), 600)
        self.assertEqual(calls, [0, 250, 500])

    def test_korea_update_and_backfill_end_to_end(self):
        from pipeline.sources import yahoo_screen
        quotes = self._korea_quotes()
        cfg = self.cfg["KOSPI"]
        seoul = ZoneInfoT("Asia/Seoul")
        backfilled = []
        def fake_backfill(latest, start, end, c=None):
            backfilled.append(len(latest))
            return {}, len(latest), []
        with mock.patch.object(yahoo_screen, "screen_all", lambda ex, qt="EQUITY": quotes), \
             mock.patch.object(yahoo_screen, "backfill", fake_backfill), \
             mock.patch.object(self.run, "local_now", lambda tz: dt.datetime(2026, 10, 26, 2, 0, tzinfo=seoul)):
            self.assertTrue(self.run.update_exchange("KOSPI", cfg, 370))
        self.assertEqual(self.store.stored_days("KOSPI"), [dt.date(2026, 10, 23)])
        self.assertEqual(backfilled, [62])

    def test_backfill_skipped_when_history_exists(self):
        from pipeline.sources import yahoo_screen
        quotes = self._korea_quotes()
        cfg = self.cfg["KOSPI"]
        day0 = yahoo_screen.parse(quotes, cfg)
        for d in pd_bdays("2025-10-23", "2026-10-22"):
            self.store.save_day("KOSPI", d, day0)
        called = []
        with mock.patch.object(yahoo_screen, "screen_all", lambda ex, qt="EQUITY": quotes), \
             mock.patch.object(yahoo_screen, "backfill", lambda *a: called.append(1) or ({}, 0, [])), \
             mock.patch.object(self.run, "local_now", lambda tz: dt.datetime(2026, 10, 26, 2, 0, tzinfo=ZoneInfoT(tz))):
            self.run.update_exchange("KOSPI", cfg, 370)
        self.assertEqual(called, [])
        self.assertIn("Backfill skipped", " ".join(self.store.read_status("KOSPI")["notes"]))

    def test_english_names_refresh_and_display(self):
        import pandas as pd
        from pipeline.sources import yahoo_screen
        cfg = self.cfg["SSE"]
        day = pd.DataFrame([{"symbol": "600519", "name": "贵州茅台", "isin": "", "series": "Main Board", "close": 1450.0,
                             "prev_close": 1438.0, "volume": 3100000, "value": 4.5e9},
                            {"symbol": "600000", "name": "浦发银行", "isin": "", "series": "Main Board", "close": 9.53,
                             "prev_close": 9.5, "volume": 75592632, "value": 7.2e8}])
        from pipeline.common import STANDARD_COLUMNS
        self.store.save_day("SSE", dt.date(2026, 10, 23), day.reindex(columns=STANDARD_COLUMNS))
        quotes = [{"symbol": "600519.SS", "longName": "Kweichow  Moutai Co., Ltd."}]   # 600000 has no English name
        with mock.patch.object(yahoo_screen, "screen_all", lambda ex, qt="EQUITY": quotes):
            self.run.refresh_names("SSE", cfg)
        self.assertEqual(self.names.load("SSE"), {"600519": "Kweichow Moutai Co., Ltd."})   # spaces tidied
        self.assertIn("English names: 1 of 2", " ".join(self.store.read_status("SSE")["notes"]))
        self.build_site.build()
        s = json.loads((self.build_site.SITE_DATA / "SSE" / "summary.json").read_text())
        f = {k: i for i, k in enumerate(s["fields"])}
        rows = {r[0]: r for r in s["rows"]}
        self.assertEqual(rows["600519"][f["name"]], "Kweichow Moutai Co., Ltd.")
        self.assertEqual(rows["600519"][f["local_name"]], "贵州茅台")
        self.assertEqual(rows["600000"][f["name"]], "浦发银行")                 # no English: original kept
        self.assertIsNone(rows["600000"][f["local_name"]])

    def test_names_only_refresh_when_due(self):
        today = dt.date(2026, 10, 26)
        self.assertTrue(self.names.needs_refresh("SSE", ["600519"], today))       # nothing saved yet
        p = self.names.path("SSE"); p.parent.mkdir(parents=True)
        p.write_text(json.dumps({"updated": "2026-10-24", "names": {"600519": "Kweichow Moutai"}}))
        self.assertFalse(self.names.needs_refresh("SSE", ["600519"], today))      # fresh, complete
        self.assertTrue(self.names.needs_refresh("SSE", ["600519", "600000"], today))   # 50% missing
        self.assertTrue(self.names.needs_refresh("SSE", ["600519"], dt.date(2026, 11, 5)))  # a week old

    def test_names_failure_does_not_break_update(self):
        from pipeline.sources import yahoo_screen
        import pandas as pd
        from pipeline.common import STANDARD_COLUMNS
        self.store.save_day("SSE", dt.date(2026, 10, 23), pd.DataFrame([{"symbol": "600519", "name": "贵州茅台",
                            "close": 1.0}]).reindex(columns=STANDARD_COLUMNS))
        def boom(*a, **k):
            raise ConnectionError("Yahoo down")
        with mock.patch.object(yahoo_screen, "screen_all", boom):
            self.run.refresh_names("SSE", self.cfg["SSE"])
        self.assertIn("couldn't refresh", " ".join(self.store.read_status("SSE")["notes"]))


def pd_bdays(a, b):
    import pandas as pd
    return [d.date() for d in pd.bdate_range(a, b)]


class TaiwanNamesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["WC_DATA_DIR"] = str(self.tmp / "data")
        import pipeline.store, pipeline.names, pipeline.run
        for m in (pipeline.store, pipeline.names, pipeline.run):
            importlib.reload(m)
        self.names, self.run = pipeline.names, pipeline.run

    def tearDown(self):
        shutil.rmtree(self.tmp)
        os.environ.pop("WC_DATA_DIR", None)

    def test_twse_company_info_then_yahoo(self):
        from pipeline.sources import yahoo_screen
        twse_rows = [{"出表日期": "1151023", "公司代號": "2330", "公司名稱": "台灣積體電路製造股份有限公司", "公司簡稱": "台積電",
                      "英文簡稱": "TSMC"},
                     {"公司代號": "2317", "公司簡稱": "鴻海", "英文簡稱": "Hon  Hai"},
                     {"公司代號": "9999", "公司簡稱": "無英文", "英文簡稱": ""}]
        yahoo = [{"symbol": "2330.TW", "longName": "Taiwan Semiconductor Manufacturing Company Limited"},
                 {"symbol": "0050.TW", "longName": "Yuanta Taiwan Top 50 ETF"}]
        cfg = self.run.load_config()["TWSE"]
        with mock.patch.object(self.names, "get_bytes", create=True), \
             mock.patch("pipeline.common.get_bytes", lambda sess, url, **kw: json.dumps(twse_rows).encode()), \
             mock.patch.object(yahoo_screen, "screen_all", lambda ex, qt="EQUITY": yahoo if qt == "EQUITY" else []):
            note = self.names.refresh("TWSE", cfg, ["2330", "2317", "9999", "0050"], dt.date(2026, 10, 26))
        names = self.names.load("TWSE")
        self.assertEqual(names["2330"], "Taiwan Semiconductor Manufacturing Company Limited")   # Yahoo's fuller name wins
        self.assertEqual(names["2317"], "Hon Hai")                                               # TWSE fills the gap
        self.assertEqual(names["0050"], "Yuanta Taiwan Top 50 ETF")
        self.assertNotIn("9999", names)
        self.assertEqual(note, "English names: 3 of 4 stocks.")


class KoreaVolumeTests(unittest.TestCase):
    """Yahoo's screener reports volume 0 for Korean stocks; the daily history has the real number."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["WC_DATA_DIR"] = str(self.tmp / "data")
        import pipeline.store, pipeline.run
        for m in (pipeline.store, pipeline.run):
            importlib.reload(m)
        self.store, self.run = pipeline.store, pipeline.run
        self.cfg = self.run.load_config()["KOSPI"]

    def tearDown(self):
        shutil.rmtree(self.tmp)
        os.environ.pop("WC_DATA_DIR", None)

    def _quotes(self):
        t = int(dt.datetime(2026, 10, 23, 6, 30, tzinfo=dt.timezone.utc).timestamp())
        q = [{"symbol": "005930.KS", "longName": "Samsung Electronics Co., Ltd.", "regularMarketPrice": 215500.0,
              "regularMarketPreviousClose": 214500.0, "regularMarketVolume": 0, "regularMarketTime": t}]
        q += [{"symbol": f"{100000 + i}.KS", "longName": f"Co {i}", "regularMarketPrice": 1000.0,
               "regularMarketPreviousClose": 990.0, "regularMarketVolume": 0, "regularMarketTime": t} for i in range(60)]
        return q

    def _history(self, has_day=True):
        import pandas as pd
        from pipeline.common import STANDARD_COLUMNS
        def fake(latest, start, end, to_yahoo, **kw):
            if not has_day:
                return {}, 0, []
            rows = [{"symbol": s, "close": 215500.0 if s == "005930" else 1000.0, "open": 213000.0,
                     "high": 216000.0, "low": 212500.0, "volume": 11469322 if s == "005930" else 5000}
                    for s in latest["symbol"]]
            return {end: pd.DataFrame(rows).reindex(columns=STANDARD_COLUMNS)}, len(rows), []
        return fake

    def test_zero_volume_is_unknown_not_zero(self):
        from pipeline.sources import yahoo_screen
        df = yahoo_screen.parse(self._quotes(), self.cfg)
        self.assertTrue(df["volume"].isna().all())
        self.assertTrue(yahoo_screen.missing_volume(df))

    def test_fetch_fills_volume_from_history(self):
        from pipeline.sources import yahoo_screen
        with mock.patch.object(yahoo_screen, "screen_all", lambda ex, qt="EQUITY": self._quotes()), \
             mock.patch("pipeline.yahoo.backfill", self._history()):
            df = yahoo_screen.fetch(dt.date(2026, 10, 23), self.cfg)
        d = df.set_index("symbol")
        self.assertEqual(d.at["005930", "volume"], 11469322)
        self.assertEqual(d.at["005930", "value"], round(215500 * 11469322))
        self.assertEqual(d.at["005930", "open"], 213000.0)
        self.assertEqual(df.attrs["session_date"], dt.date(2026, 10, 23))        # attrs survive the fill

    def test_history_without_that_day_leaves_volume_blank(self):
        from pipeline.sources import yahoo_screen
        with mock.patch.object(yahoo_screen, "screen_all", lambda ex, qt="EQUITY": self._quotes()), \
             mock.patch("pipeline.yahoo.backfill", self._history(has_day=False)):
            df = yahoo_screen.fetch(dt.date(2026, 10, 23), self.cfg)
        self.assertTrue(df["volume"].isna().all())                               # blank, never a false 0

    def test_repair_fixes_a_day_saved_with_zero_volume(self):
        from pipeline.sources import yahoo_screen
        import pandas as pd
        day = dt.date(2026, 10, 23)
        bad = yahoo_screen.parse(self._quotes(), self.cfg)
        bad["volume"] = 0.0                                                       # as stored by the old code
        self.store.save_day("KOSPI", day, bad)
        with mock.patch.object(yahoo_screen, "screen_all", lambda ex, qt="EQUITY": self._quotes()), \
             mock.patch("pipeline.yahoo.backfill", self._history()), \
             mock.patch.object(self.run, "local_now", lambda tz: dt.datetime(2026, 10, 25, 9, 0, tzinfo=ZoneInfoT(tz))):
            self.run.update_exchange("KOSPI", self.cfg, 0)
        fixed = self.store.load_day("KOSPI", day).set_index("symbol")
        self.assertEqual(fixed.at["005930", "volume"], 11469322)
        self.assertIn("Volume filled in for 2026-10-23", " ".join(self.store.read_status("KOSPI")["notes"]))


class WeekendTests(unittest.TestCase):
    def test_saudi_weekend_is_friday_and_saturday(self):
        import pipeline.run as run
        from zoneinfo import ZoneInfo
        cfg = {"weekend": [4, 5], "open_time": "09:30", "close_time": "15:00"}
        riyadh = ZoneInfo("Asia/Riyadh")
        at = lambda d, h: dt.datetime(2026, 10, d, h, 0, tzinfo=riyadh)
        self.assertEqual(run.session_day(cfg, at(25, 20)), dt.date(2026, 10, 25))   # Sunday evening: a trading day
        self.assertEqual(run.session_day(cfg, at(23, 12)), dt.date(2026, 10, 22))   # Friday: Thursday's session
        self.assertEqual(run.session_day(cfg, at(24, 12)), dt.date(2026, 10, 22))   # Saturday: Thursday's session
        self.assertEqual(run.session_day(cfg, at(25, 8)), dt.date(2026, 10, 22))    # Sunday before open: Thursday
        self.assertIsNone(run.session_day(cfg, at(26, 12)))                         # Monday, market open
        # Everyone else is unchanged
        self.assertEqual(run.session_day({"close_time": "16:00"}, at(25, 20)), dt.date(2026, 10, 23))


class Stage4Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["WC_DATA_DIR"] = str(self.tmp / "data")
        import pipeline.store, pipeline.build_site, pipeline.run
        for m in (pipeline.store, pipeline.build_site, pipeline.run):
            importlib.reload(m)
        pipeline.build_site.SITE_DATA = self.tmp / "site_data"
        self.store, self.build_site, self.run = pipeline.store, pipeline.build_site, pipeline.run
        self.cfg = self.run.load_config()

    def tearDown(self):
        shutil.rmtree(self.tmp)
        os.environ.pop("WC_DATA_DIR", None)

    def test_every_yahoo_code_is_valid(self):
        from yfinance.const import EQUITY_SCREENER_EQ_MAP
        valid = set().union(*EQUITY_SCREENER_EQ_MAP["exchange"].values())
        for code, c in self.cfg.items():
            if c["source"] == "yahoo_screen":
                codes = c["yahoo_exchange"] if isinstance(c["yahoo_exchange"], list) else [c["yahoo_exchange"]]
                for y in codes:
                    self.assertIn(y, valid, f"{code}: unknown Yahoo exchange code {y}")
                for y in (c.get("venues") or {}):
                    self.assertIn(y, codes, f"{code}: venue {y} isn't queried")

    def test_every_exchange_is_complete(self):
        from zoneinfo import ZoneInfo
        for code, c in self.cfg.items():
            for key in ("name", "short", "country", "city", "region", "currency", "timezone", "source"):
                self.assertTrue(c.get(key), f"{code} is missing {key}")
            ZoneInfo(c["timezone"])
            self.assertIn(c["region"], ["Asia-Pacific", "Europe", "Middle East & Africa", "Americas"])

    def _euronext_quotes(self):
        t = int(dt.datetime(2026, 10, 23, 15, 40, tzinfo=dt.timezone.utc).timestamp())
        q = [
            {"symbol": "MC.PA", "longName": "LVMH Moët Hennessy Louis Vuitton", "exchange": "PAR", "currency": "EUR",
             "regularMarketPrice": 640.0, "regularMarketPreviousClose": 630.0, "regularMarketVolume": 500000,
             "marketCap": 3.2e11, "regularMarketTime": t},
            {"symbol": "ASML.AS", "longName": "ASML Holding N.V.", "exchange": "AMS", "currency": "EUR",
             "regularMarketPrice": 900.0, "regularMarketPreviousClose": 890.0, "regularMarketVolume": 800000,
             "regularMarketTime": t},
            {"symbol": "EQNR.OL", "longName": "Equinor ASA", "exchange": "OSL", "currency": "NOK",
             "regularMarketPrice": 260.0, "regularMarketPreviousClose": 258.0, "regularMarketVolume": 4000000,
             "regularMarketTime": t},
        ]
        q += [{"symbol": f"X{i}.PA", "longName": f"Co {i}", "exchange": "PAR", "currency": "EUR", "regularMarketPrice": 10.0,
               "regularMarketPreviousClose": 10.0, "regularMarketVolume": 100, "regularMarketTime": t} for i in range(60)]
        return q

    def test_multi_venue_exchange(self):
        from pipeline.sources import yahoo_screen
        cfg = self.cfg["EURONEXT"]
        df = yahoo_screen.parse(self._euronext_quotes(), cfg).set_index("symbol")
        self.assertIn("MC.PA", df.index)                                # Yahoo's full symbol kept
        self.assertEqual(df.at["ASML.AS", "series"], "Amsterdam")
        self.assertEqual(df.at["EQNR.OL", "series"], "Oslo")
        self.assertEqual(df.at["EQNR.OL", "currency"], "NOK")           # Oslo trades in kroner
        self.assertEqual(yahoo_screen.to_yahoo_for(cfg)("MC.PA"), "MC.PA")
        self.assertEqual(yahoo_screen.to_yahoo_for(self.cfg["KOSPI"])("005930"), "005930.KS")   # Korea unchanged

    def test_query_uses_all_venues(self):
        from pipeline.sources import yahoo_screen
        seen = []
        def screen(query, **kw):
            seen.append(query)
            return {"quotes": [], "total": 0}
        fake = mock.Mock(screen=screen, EquityQuery=lambda op, args: (op, args), ETFQuery=None)
        with mock.patch.dict(sys.modules, {"yfinance": fake}):
            yahoo_screen.screen_all(self.cfg["EURONEXT"]["yahoo_exchange"])
            yahoo_screen.screen_all("JPX")
        self.assertEqual(seen[0], ("is-in", ["exchange", "AMS", "BRU", "ISE", "LIS", "MIL", "OSL", "PAR"]))
        self.assertEqual(seen[1], ("eq", ["exchange", "JPX"]))

    def test_build_keeps_currency_only_where_it_differs(self):
        from pipeline.sources import yahoo_screen
        df = yahoo_screen.parse(self._euronext_quotes(), self.cfg["EURONEXT"])
        self.store.save_day("EURONEXT", dt.date(2026, 10, 23), df)
        self.build_site.build()
        s = json.loads((self.build_site.SITE_DATA / "EURONEXT" / "summary.json").read_text())
        f = {k: i for i, k in enumerate(s["fields"])}
        rows = {r[0]: r for r in s["rows"]}
        self.assertEqual(rows["EQNR.OL"][f["currency"]], "NOK")
        self.assertIsNone(rows["MC.PA"][f["currency"]])                  # same as the exchange: left out

    def test_old_day_files_without_currency_still_load(self):
        import pandas as pd
        path = self.store.day_file("LSE", dt.date(2026, 10, 23)); path.parent.mkdir(parents=True)
        pd.DataFrame([{"symbol": "SHEL.L", "name": "Shell", "close": 2650.0}]).to_csv(path, index=False, compression="gzip")
        self.assertEqual(self.store.load_day("LSE", dt.date(2026, 10, 23)).iloc[0]["currency"], "")


class MarketOpenBackfillTests(unittest.TestCase):
    """First run of an exchange while its market is open: backfill must still happen."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["WC_DATA_DIR"] = str(self.tmp / "data")
        import pipeline.store, pipeline.run
        for m in (pipeline.store, pipeline.run):
            importlib.reload(m)
        self.store, self.run = pipeline.store, pipeline.run
        self.cfg = self.run.load_config()["TSE"]

    def tearDown(self):
        shutil.rmtree(self.tmp)
        os.environ.pop("WC_DATA_DIR", None)

    def _quotes(self):
        t = int(dt.datetime(2026, 10, 26, 5, 0, tzinfo=dt.timezone.utc).timestamp())   # Monday, mid-session
        return [{"symbol": f"{1300 + i}.T", "longName": f"Company {i}", "currency": "JPY", "regularMarketPrice": 1000.0 + i,
                 "regularMarketPreviousClose": 1000.0, "regularMarketVolume": 0, "regularMarketTime": t} for i in range(60)]

    def test_backfill_runs_while_market_is_open(self):
        import pandas as pd
        from pipeline.common import STANDARD_COLUMNS
        from pipeline.sources import yahoo_screen
        calls = {}
        def fake_backfill(latest, start, end, cfg=None):
            calls["end"], calls["n"] = end, len(latest)
            days = {d.date(): latest.assign(close=900.0) for d in pd.bdate_range(start, end)}
            return days, len(latest), []
        tokyo = ZoneInfoT("Asia/Tokyo")
        with mock.patch.object(yahoo_screen, "screen_all", lambda ex, qt="EQUITY": self._quotes()), \
             mock.patch.object(yahoo_screen, "backfill", fake_backfill), \
             mock.patch("pipeline.yahoo.backfill", side_effect=AssertionError("no volume fill for a listing")), \
             mock.patch.object(self.run, "local_now", lambda tz: dt.datetime(2026, 10, 26, 14, 0, tzinfo=tokyo)):
            ok = self.run.update_exchange("TSE", self.cfg, 370)
        self.assertTrue(ok)
        self.assertEqual(calls["end"], dt.date(2026, 10, 23))                    # history up to Friday
        self.assertEqual(calls["n"], 60)
        days = self.store.stored_days("TSE")
        self.assertNotIn(dt.date(2026, 10, 26), days)                            # Monday's unfinished session not saved
        self.assertEqual(days[-1], dt.date(2026, 10, 23))
        self.assertGreater(len(days), 250)
        status = self.store.read_status("TSE")
        self.assertEqual(status["errors"], [])
        self.assertIn("Took the list of 60 stocks", " ".join(status["notes"]))

    def test_listing_failure_is_reported_not_crashed(self):
        from pipeline.sources import yahoo_screen
        def down(*a, **k):
            raise ConnectionError("Yahoo down")
        with mock.patch.object(yahoo_screen, "screen_all", down), \
             mock.patch.object(self.run, "local_now", lambda tz: dt.datetime(2026, 10, 26, 14, 0, tzinfo=ZoneInfoT(tz))):
            self.run.update_exchange("TSE", self.cfg, 370)
        self.assertIn("couldn't get the list of stocks", " ".join(self.store.read_status("TSE")["errors"]))


class YahooRetryTests(unittest.TestCase):
    def _run(self, failures, error="HTTP Error 401: "):
        from pipeline.sources import yahoo_screen
        calls, waits = [], []
        def screen(query, offset=0, size=250, **kw):
            calls.append(offset)
            if len(calls) <= failures:
                raise Exception(error)
            return {"quotes": [{"symbol": "A.T"}], "total": 1}
        fake = mock.Mock(screen=screen, EquityQuery=lambda *a: a)
        with mock.patch.dict(sys.modules, {"yfinance": fake}), \
             mock.patch.object(yahoo_screen.time, "sleep", lambda s: waits.append(s)):
            return yahoo_screen.screen_all("JPX"), calls, waits

    def test_waits_out_a_rate_limit(self):
        quotes, calls, waits = self._run(failures=2)
        self.assertEqual(len(quotes), 1)
        self.assertEqual(waits[:2], [60, 180])

    def test_gives_up_after_three_retries(self):
        with self.assertRaisesRegex(Exception, "401"):
            self._run(failures=10)

    def test_other_errors_are_not_retried(self):
        with self.assertRaisesRegex(Exception, "Invalid"):
            self._run(failures=1, error="Invalid EQ value")


class DeadListingTests(unittest.TestCase):
    def test_listings_without_recent_trades_are_dropped(self):
        from pipeline.run import load_config
        from pipeline.sources import yahoo_screen
        now = int(dt.datetime(2026, 10, 26, 16, 40, tzinfo=dt.timezone.utc).timestamp())
        live = [{"symbol": f"L{i}.PA", "longName": f"Live {i}", "exchange": "PAR", "regularMarketPrice": 10.0,
                 "regularMarketPreviousClose": 10.0, "regularMarketVolume": 100, "regularMarketTime": now - i * 60}
                for i in range(60)]
        quiet = [{"symbol": "Q.PA", "longName": "Quiet but alive", "exchange": "PAR", "regularMarketPrice": 2.0,
                  "regularMarketVolume": 5, "regularMarketTime": now - 20 * 86400}]           # 20 days ago: kept
        dead = [{"symbol": f"D{i}.MI", "longName": f"Delisted {i}", "exchange": "MIL", "regularMarketPrice": 1.0,
                 "regularMarketTime": now - (400 + i) * 86400} for i in range(500)]          # over a year: dropped
        df = yahoo_screen.parse(live + quiet + dead, load_config()["EURONEXT"])
        self.assertEqual(len(df), 61)
        self.assertIn("Q.PA", set(df.symbol))
        self.assertEqual(df.attrs["dead_dropped"], 500)
        self.assertEqual(df.attrs["session_date"], dt.date(2026, 10, 26))

    def test_penny_prices_keep_four_decimals(self):
        from pipeline.build_site import _num
        self.assertEqual(_num(0.347999989), 0.348)
        self.assertEqual(_num(1.6799999475), 1.68)
        self.assertEqual(_num(12345.678), 12345.68)
        self.assertEqual(_num(-0.5, 3), -0.5)


class PruneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["WC_DATA_DIR"] = str(self.tmp / "data")
        import pipeline.store, pipeline.run
        for m in (pipeline.store, pipeline.run):
            importlib.reload(m)
        self.store, self.run = pipeline.store, pipeline.run

    def tearDown(self):
        shutil.rmtree(self.tmp)
        os.environ.pop("WC_DATA_DIR", None)

    def test_prune_keeps_recent_days_only(self):
        import pandas as pd
        from pipeline.common import STANDARD_COLUMNS
        df = pd.DataFrame([{"symbol": "A", "close": 1.0}]).reindex(columns=STANDARD_COLUMNS)
        today = dt.date.today()
        days = [today - dt.timedelta(days=n) for n in (1, 100, 399, 401, 700)]
        for d in days:
            self.store.save_day("NSE", d, df)
        self.store.write_status("NSE", days_stored=5, last_trading_day=days[0].isoformat())
        args = mock.Mock(keep_days=400)
        self.run.cmd_prune(args)
        self.assertEqual(self.store.stored_days("NSE"), sorted(days[:3]))
        self.assertEqual(self.store.read_status("NSE")["days_stored"], 3)
        self.assertTrue(self.store.read_status("NSE")["last_trading_day"])        # rest of status kept


class ForeignListingTests(unittest.TestCase):
    """Real examples from Mexico's exchange data."""

    def _mask(self, rows, other_names=(), us=()):
        import pandas as pd
        from pipeline.foreign import foreign_listings, normalise
        df = pd.DataFrame(rows, columns=["symbol", "name"])
        return dict(zip(df.symbol, foreign_listings(df, {normalise(n) for n in other_names}, set(us))))

    def test_mexican_companies_are_kept(self):
        m = self._mask([("GMEXICOB.MX", "Grupo México, S.A.B. de C.V."), ("FMTY14.MX", "Fibra Mty, S.A.P.I. de C.V."),
                        ("FIHO12.MX", "FibraHotel"), ("BBAJIOO.MX", "Banco del Bajío, S.A., Institución de Banca Múltiple"),
                        ("NAFTRACISHRS.MX", "iShares NAFTRAC"), ("NEXT25.MX", "Nearshoring Experts & Technology, S.C."),
                        ("AERO.MX", "Grupo Aeroméxico, S.A.B. de C.V.")], us={"AERO"})
        self.assertFalse(any(m.values()), m)        # Aeroméxico kept even though AERO is also a US ticker

    def test_foreign_shares_are_dropped(self):
        m = self._mask([("XOM.MX", "ExxonMobil Holdings Corporation"), ("MELIN.MX", "MercadoLibre, Inc."),
                        ("1913N.MX", "Prada S.p.A."), ("AA1.MX", "Alcoa Corporation"),
                        ("ANB.MX", "Anheuser-Busch InBev SA/NV"), ("KKRC.MX", "KKR & Co. Inc."),
                        ("BRKB.MX", "Berkshire Hathaway Inc.")],
                       other_names={"Anheuser-Busch InBev SA/NV"}, us={"XOM", "AA"})
        self.assertTrue(all(m.values()), m)

    def test_build_applies_the_filter_and_note(self):
        import pandas as pd
        tmp = Path(tempfile.mkdtemp())
        os.environ["WC_DATA_DIR"] = str(tmp / "data")
        try:
            import pipeline.store, pipeline.build_site
            importlib.reload(pipeline.store); importlib.reload(pipeline.build_site)
            pipeline.build_site.SITE_DATA = tmp / "site"
            from pipeline.common import STANDARD_COLUMNS
            rows = [("WALMEX.MX", "Wal-Mart de México, S.A.B. de C.V."), ("BA.MX", "The Boeing Company"),
                    ("CEMEXCPO.MX", "CEMEX, S.A.B. de C.V."), ("STLAN.MX", "Stellantis N.V.")]
            df = pd.DataFrame([{"symbol": s, "name": n, "close": 10.0, "prev_close": 9.0} for s, n in rows]).reindex(columns=STANDARD_COLUMNS)
            pipeline.store.save_day("BMV", dt.date(2026, 10, 23), df)
            pipeline.build_site.build()
            s = json.loads((tmp / "site" / "BMV" / "summary.json").read_text())
            self.assertEqual(sorted(r[0] for r in s["rows"]), ["CEMEXCPO.MX", "WALMEX.MX"])
            idx = json.loads((tmp / "site" / "exchanges.json").read_text())
            self.assertIn("SIC", next(e for e in idx["exchanges"] if e["code"] == "BMV")["note"])
        finally:
            shutil.rmtree(tmp); os.environ.pop("WC_DATA_DIR", None)
