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

    def test_settings_should_default_to_hardened_runtime_flags_when_env_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)

        self.assertFalse(settings.DEBUG)
        self.assertTrue(settings.ADMIN_SESSION_SECURE)
        self.assertFalse(settings.API_DOCS_ENABLED)

    def test_settings_should_report_startup_issue_for_short_admin_secret(self):
        with patch.dict(
            os.environ,
            {
                "ADMIN_USERNAME": "admin",
                "ADMIN_PASSWORD": "secret-pass",
                "ADMIN_SESSION_SECRET": "short-secret",
            },
            clear=True,
        ):
            settings = Settings(_env_file=None)

        self.assertIn(
            "admin_session_secret_too_short(min_length=32)",
            settings.STARTUP_VALIDATION_ISSUES,
        )


if __name__ == "__main__":
    unittest.main()
