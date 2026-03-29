import os
import unittest
from unittest.mock import patch

from src.config import Settings


class SettingsTestCase(unittest.TestCase):
    def test_settings_should_fallback_false_for_invalid_debug_text(self):
        with patch("src.config.logger.warning", create=True) as mocked_warning, patch.dict(
            os.environ,
            {"DEBUG": "release"},
            clear=False,
        ):
            settings = Settings(_env_file=None)

        self.assertFalse(settings.DEBUG)
        mocked_warning.assert_called_once()

    def test_settings_should_accept_standard_truthy_and_falsey_debug_values(self):
        with patch.dict(os.environ, {"DEBUG": "on"}, clear=False):
            self.assertTrue(Settings(_env_file=None).DEBUG)

        with patch.dict(os.environ, {"DEBUG": "off"}, clear=False):
            self.assertFalse(Settings(_env_file=None).DEBUG)


if __name__ == "__main__":
    unittest.main()
