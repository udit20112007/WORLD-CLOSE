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
             mock.patch.object(twse, "fetch", lambda day, c: twse.parse(rows, c)):
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

    def test_krx_without_key_needs_setup(self):
        ok = self.run.update_exchange("KOSPI", self.cfg["KOSPI"], 0)
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
            self.run.update_exchange("KOSPI", self.cfg["KOSPI"], 0)
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
