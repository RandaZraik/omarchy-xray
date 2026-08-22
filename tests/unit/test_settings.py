from __future__ import annotations

import json
from pathlib import Path
import stat
import tempfile
import unittest

from xray.config import (
    SETTINGS_SPEC,
    normalize_settings,
    settings_contract,
    settings_defaults,
)
from xray.system.settings import MAX_SETTINGS_BYTES, SessionSettings, SettingsRepository


class SettingsTests(unittest.TestCase):
    def test_session_settings_exposes_a_copy_and_typed_runtime_values(self) -> None:
        source = {
            "refreshSeconds": 2,
            "historySeconds": 300,
            "capturePreview": True,
        }
        settings = SessionSettings(source)
        source["historySeconds"] = 1

        self.assertEqual(settings.history_seconds, 300)
        self.assertTrue(settings.capture_preview)
        exported = settings.as_dict()
        exported["capturePreview"] = False
        self.assertTrue(settings.capture_preview)

    def test_contract_has_unique_keys_and_valid_defaults(self) -> None:
        contract = settings_contract()
        keys = [row["key"] for row in contract]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(contract), len(SETTINGS_SPEC))
        self.assertEqual(normalize_settings(settings_defaults()), settings_defaults())
        for row in contract:
            if row["type"] == "choice":
                self.assertIn(
                    row["default"], [option["value"] for option in row["options"]]
                )

    def test_normalization_rejects_unknown_values_and_boolean_numbers(self) -> None:
        defaults = settings_defaults()
        self.assertEqual(
            normalize_settings({"refreshSeconds": 99, "historySeconds": -1}), defaults
        )
        self.assertEqual(
            normalize_settings({"refreshSeconds": True})["refreshSeconds"],
            defaults["refreshSeconds"],
        )
        self.assertFalse(
            normalize_settings({"capturePreview": False})["capturePreview"]
        )
        for malformed in ([], {}, [2], {"value": 2}):
            with self.subTest(malformed=malformed):
                self.assertEqual(
                    normalize_settings({"refreshSeconds": malformed})["refreshSeconds"],
                    defaults["refreshSeconds"],
                )

    def test_repository_round_trip_is_private_and_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "settings.json"
            repository = SettingsRepository(path)
            saved = repository.save(
                {"refreshSeconds": 5, "historySeconds": 60, "capturePreview": False}
            )
            self.assertEqual(repository.load(), saved)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
            self.assertEqual(list(path.parent.glob(".settings.json.*.tmp")), [])

    def test_repository_falls_back_for_malformed_or_oversized_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("not json", encoding="utf-8")
            repository = SettingsRepository(path)
            self.assertEqual(repository.load(), settings_defaults())
            path.write_text(
                json.dumps({"padding": "x" * MAX_SETTINGS_BYTES}), encoding="utf-8"
            )
            self.assertEqual(repository.load(), settings_defaults())
            path.write_text(json.dumps({"refreshSeconds": []}), encoding="utf-8")
            self.assertEqual(repository.load(), settings_defaults())


if __name__ == "__main__":
    unittest.main()
