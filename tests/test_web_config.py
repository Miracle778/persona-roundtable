from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from my_agent.web.config import (
    DEFAULT_PROVIDER_TEMPLATES,
    ensure_config,
    load_config,
    mask_secret,
    save_config,
)


class WebConfigTests(unittest.TestCase):
    def test_ensure_config_creates_local_json_with_provider_templates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"

            config = ensure_config(path)

            self.assertTrue(path.exists())
            self.assertEqual(config["default_model"]["provider_id"], "volces-coding")
            provider_ids = {provider["id"] for provider in config["providers"]}
            self.assertEqual(provider_ids, {item["id"] for item in DEFAULT_PROVIDER_TEMPLATES})
            mode = stat.S_IMODE(path.stat().st_mode)
            if os.name != "nt":
                self.assertEqual(mode, 0o600)

    def test_save_and_load_config_round_trips_plain_local_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            config = ensure_config(path)
            config["providers"][0]["api_key"] = "sk-test-secret-1234"

            save_config(config, path)
            loaded = load_config(path)

            self.assertEqual(loaded["providers"][0]["api_key"], "sk-test-secret-1234")
            self.assertEqual(mask_secret("sk-test-secret-1234"), "sk-**********1234")


if __name__ == "__main__":
    unittest.main()
