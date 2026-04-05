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

    def test_settings_should_parse_http_outbound_proxy_metadata(self):
        with patch.dict(
            os.environ,
            {"OUTBOUND_PROXY_URL": "http://proxy.example.com:8080"},
            clear=True,
        ):
            settings = Settings(_env_file=None)

        self.assertTrue(settings.OUTBOUND_PROXY_ENABLED)
        self.assertEqual(settings.OUTBOUND_PROXY_SCHEME, "http")
        self.assertEqual(
            settings.OUTBOUND_PROXY_DISPLAY,
            "proxy.example.com:8080",
        )

    def test_settings_should_parse_https_outbound_proxy_metadata(self):
        with patch.dict(
            os.environ,
            {"OUTBOUND_PROXY_URL": "https://proxy.example.com:8443"},
            clear=True,
        ):
            settings = Settings(_env_file=None)

        self.assertTrue(settings.OUTBOUND_PROXY_ENABLED)
        self.assertEqual(settings.OUTBOUND_PROXY_SCHEME, "https")
        self.assertEqual(
            settings.OUTBOUND_PROXY_DISPLAY,
            "proxy.example.com:8443",
        )

    def test_settings_should_accept_socks5_outbound_proxy_when_dependency_available(self):
        with patch.dict(
            os.environ,
            {"OUTBOUND_PROXY_URL": "socks5://proxy.example.com:1080"},
            clear=True,
        ), patch("importlib.util.find_spec", return_value=object()):
            settings = Settings(_env_file=None)

        self.assertTrue(settings.OUTBOUND_PROXY_ENABLED)
        self.assertEqual(settings.OUTBOUND_PROXY_SCHEME, "socks5")
        self.assertEqual(
            settings.OUTBOUND_PROXY_DISPLAY,
            "proxy.example.com:1080",
        )

    def test_settings_should_not_leak_credentials_in_outbound_proxy_display(self):
        with patch.dict(
            os.environ,
            {"OUTBOUND_PROXY_URL": "http://user:secret@proxy.example.com:8080"},
            clear=True,
        ):
            settings = Settings(_env_file=None)

        self.assertEqual(settings.OUTBOUND_PROXY_SCHEME, "http")
        self.assertEqual(settings.OUTBOUND_PROXY_DISPLAY, "proxy.example.com:8080")
        self.assertNotIn("user", settings.OUTBOUND_PROXY_DISPLAY)
        self.assertNotIn("secret", settings.OUTBOUND_PROXY_DISPLAY)
        self.assertNotIn("@", settings.OUTBOUND_PROXY_DISPLAY)

    def test_settings_should_raise_value_error_for_unsupported_outbound_proxy_scheme(self):
        with patch.dict(
            os.environ,
            {"OUTBOUND_PROXY_URL": "ftp://proxy.example.com:2121"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "OUTBOUND_PROXY_URL 仅支持"):
                Settings(_env_file=None)

    def test_settings_should_raise_value_error_when_socks_proxy_without_socksio(self):
        with patch.dict(
            os.environ,
            {"OUTBOUND_PROXY_URL": "socks5://proxy.example.com:1080"},
            clear=True,
        ), patch("importlib.util.find_spec", return_value=None):
            with self.assertRaisesRegex(
                ValueError,
                "OUTBOUND_PROXY_URL 使用 socks 代理时需要安装 socksio 依赖",
            ):
                Settings(_env_file=None)

    def test_settings_should_raise_value_error_for_socks5h_proxy_scheme(self):
        with patch.dict(
            os.environ,
            {"OUTBOUND_PROXY_URL": "socks5h://proxy.example.com:1080"},
            clear=True,
        ), patch("importlib.util.find_spec", return_value=object()):
            with self.assertRaisesRegex(ValueError, "OUTBOUND_PROXY_URL 仅支持"):
                Settings(_env_file=None)

    def test_settings_should_raise_value_error_when_outbound_proxy_missing_port(self):
        with patch.dict(
            os.environ,
            {"OUTBOUND_PROXY_URL": "http://proxy.example.com"},
            clear=True,
        ):
            with self.assertRaisesRegex(
                ValueError,
                "OUTBOUND_PROXY_URL 必须包含 hostname 和 port",
            ):
                Settings(_env_file=None)

    def test_settings_should_raise_value_error_when_outbound_proxy_port_invalid(self):
        with patch.dict(
            os.environ,
            {"OUTBOUND_PROXY_URL": "http://proxy.example.com:abc"},
            clear=True,
        ):
            with self.assertRaisesRegex(
                ValueError,
                "OUTBOUND_PROXY_URL 的 port 非法",
            ):
                Settings(_env_file=None)

    def test_settings_should_raise_value_error_when_outbound_proxy_port_is_zero(self):
        with patch.dict(
            os.environ,
            {"OUTBOUND_PROXY_URL": "http://proxy.example.com:0"},
            clear=True,
        ):
            with self.assertRaisesRegex(
                ValueError,
                "OUTBOUND_PROXY_URL 的 port 必须在 1-65535 范围内",
            ):
                Settings(_env_file=None)

    def test_settings_should_raise_value_error_when_outbound_proxy_hostname_missing(self):
        with patch.dict(
            os.environ,
            {"OUTBOUND_PROXY_URL": "http://:8080"},
            clear=True,
        ):
            with self.assertRaisesRegex(
                ValueError,
                "OUTBOUND_PROXY_URL 必须包含 hostname 和 port",
            ):
                Settings(_env_file=None)


if __name__ == "__main__":
    unittest.main()
