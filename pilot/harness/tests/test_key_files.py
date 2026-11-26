"""Key lookup from dotenv files listed in keys.local.json: value found, never exposed in errors."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from harness import providers


class KeyFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.envfile = d / ".env.local"
        self.envfile.write_text('OTHER=1\nexport TEST_PILOT_KEY="sk-secret-123"\n', encoding="utf-8")
        self.listing = d / "keys.local.json"
        self.listing.write_text(json.dumps({"key_files": [str(self.envfile)]}), encoding="utf-8")
        self.patch = mock.patch.object(providers, "KEYS_LOCAL", self.listing)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_reads_named_key_only(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TEST_PILOT_KEY", None)
            self.assertEqual(providers._env_key("TEST_PILOT_KEY"), "sk-secret-123")
            self.assertEqual(providers.key_available("TEST_PILOT_KEY"), "key file")

    def test_environment_wins(self):
        with mock.patch.dict(os.environ, {"TEST_PILOT_KEY": "from-env"}):
            self.assertEqual(providers._env_key("TEST_PILOT_KEY"), "from-env")
            self.assertEqual(providers.key_available("TEST_PILOT_KEY"), "env")

    def test_missing_key_error_has_no_file_contents(self):
        os.environ.pop("NOT_THERE_KEY", None)
        with self.assertRaises(providers.ProviderError) as cm:
            providers._env_key("NOT_THERE_KEY")
        self.assertNotIn("sk-secret", str(cm.exception))
        self.assertEqual(providers.key_available("NOT_THERE_KEY"), "")


if __name__ == "__main__":
    unittest.main()
