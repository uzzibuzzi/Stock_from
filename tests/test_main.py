"""Smoke tests for main.py: CSV persistence and chart output.

These tests mock yfinance downloads so they can run without network access.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import main as main_module  # noqa: E402


def _fake_download(*_args, **_kwargs) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    return pd.DataFrame(
        {
            "Open": [10.0, 11.0, 12.0, 13.0, 14.0],
            "High": [10.5, 11.5, 12.5, 13.5, 14.5],
            "Low": [9.5, 10.5, 11.5, 12.5, 13.5],
            "Close": [10.2, 11.2, 12.2, 13.2, 14.2],
            "Adj Close": [10.2, 11.2, 12.2, 13.2, 14.2],
            "Volume": [1000, 1100, 1200, 1300, 1400],
        },
        index=dates,
    )


class MainSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.save_dir = self.tmp_dir / "save"
        self.pics_dir = self.tmp_dir / "pics"
        self.patched_save = patch.object(main_module, "SAVE_DIR", self.save_dir)
        self.patched_pics = patch.object(main_module, "PICS_DIR", self.pics_dir)
        self.patched_save.start()
        self.patched_pics.start()

    def tearDown(self) -> None:
        self.patched_save.stop()
        self.patched_pics.stop()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    @patch.object(main_module.yf, "download", side_effect=_fake_download)
    def test_process_ticker_creates_csv_and_chart(self, _mock_download) -> None:
        today = main_module.date(2024, 1, 10)
        run_folder = main_module.ensure_directories(today)

        main_module.process_ticker("FAKE", run_folder, today)

        csv_path = self.save_dir / "FAKE.csv"
        self.assertTrue(csv_path.exists(), "expected CSV file to be created")

        saved = pd.read_csv(csv_path)
        self.assertEqual(len(saved), 5)

        image_path = run_folder / f"FAKE_{today}.png"
        self.assertTrue(image_path.exists(), "expected chart PNG to be created")
        self.assertGreater(image_path.stat().st_size, 0)

    @patch.object(main_module.yf, "download", side_effect=_fake_download)
    def test_second_run_does_not_duplicate_rows(self, _mock_download) -> None:
        today = main_module.date(2024, 1, 10)
        run_folder = main_module.ensure_directories(today)

        main_module.process_ticker("FAKE", run_folder, today)
        main_module.process_ticker("FAKE", run_folder, today)

        csv_path = self.save_dir / "FAKE.csv"
        saved = pd.read_csv(csv_path)
        self.assertEqual(len(saved), 5, "rows should not duplicate on re-run")
        self.assertEqual(saved["Date"].nunique(), 5)


if __name__ == "__main__":
    unittest.main()
