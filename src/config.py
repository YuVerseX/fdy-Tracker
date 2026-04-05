"""应用配置模块"""
import importlib.util
from pathlib import Path
import secrets
from urllib.parse import urlsplit
from loguru import logger
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEBUG_TRUE_VALUES = {"true", "1", "yes", "on"}
DEBUG_FALSE_VALUES = {"false", "0", "no", "off"}
MIN_ADMIN_SESSION_SECRET_LENGTH = 32
SUPPORTED_OUTBOUND_PROXY_SCHEMES = {"http", "https", "socks5"}
SOCKS_OUTBOUND_PROXY_SCHEMES = {"socks5"}
ADMIN_PLACEHOLDER_VALUES = {
    "",
    "__required__",
    "__required_change_me__",
    "change-me",
    "change-me-admin",
    "change-me-password",
    "change-me-session-secret",
    "your-admin-username",
    "your-admin-password",
    "your-long-random-session-secret",
}
RUNTIME_EPHEMERAL_SESSION_SECRET = secrets.token_urlsafe(32)


class Settings(BaseSettings):
    """应用配置"""

    # 应用配置
    APP_NAME: str = "江苏专职辅导员招聘追踪系统"
    DEBUG: bool = False

    @field_validator("DEBUG", mode="before")
    @classmethod
    def normalize_debug_value(cls, value):
        if isinstance(value, bool):
            return value
        if value is None:
            return False

        normalized = str(value).strip().lower()
        if not normalized:
            return False
        if normalized in DEBUG_TRUE_VALUES:
            return True
        if normalized in DEBUG_FALSE_VALUES:
            return False

        logger.warning("DEBUG 配置值非法，已回退为 False: {}", value)
        return False

    @field_validator("OUTBOUND_PROXY_URL", mode="before")
    @classmethod
    def normalize_outbound_proxy_url(cls, value):
        if value is None:
            return ""
        return str(value).strip()

    # 数据库配置
    DATABASE_URL: str = "sqlite:///./data/fdy_tracker.db"

    # 爬虫配置
    SCRAPER_INTERVAL: int = 7200  # 2小时（秒）
    REQUEST_TIMEOUT: int = 30  # 请求超时（秒）
    REQUEST_DELAY_MIN: float = 1.0  # 最小延迟（秒）
    REQUEST_DELAY_MAX: float = 3.0  # 最大延迟（秒）
    REQUEST_RETRY_COUNT: int = 2  # 临时错误重试次数
    REQUEST_RETRY_BACKOFF_SECONDS: float = 0.25  # 重试退避基线（秒）
    OUTBOUND_PROXY_URL: str = ""

    # 日志配置
    LOG_LEVEL: str = "INFO"

    # AI 分析配置
    AI_ANALYSIS_ENABLED: bool = True
    AI_ANALYSIS_PROVIDER: str = "openai"
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = ""
    AI_ANALYSIS_MODEL: str = "gpt-5-mini"
    AI_PROMPT_VERSION: str = "v1"

    # 管理台鉴权
    ADMIN_USERNAME: str = ""
    ADMIN_PASSWORD: str = ""
    ADMIN_SESSION_SECRET: str = ""
    ADMIN_SESSION_MAX_AGE_SECONDS: int = 28800
    ADMIN_SESSION_SECURE: bool = True
    API_DOCS_ENABLED: bool = False
    CORS_ALLOWED_ORIGINS: str = "http://127.0.0.1:5173,http://localhost:5173"

    def __init__(self, **data):
        super().__init__(**data)
        proxy_meta = self._parse_outbound_proxy_metadata(self.OUTBOUND_PROXY_URL)
        if (
            proxy_meta is not None
            and proxy_meta[0] in SOCKS_OUTBOUND_PROXY_SCHEMES
            and importlib.util.find_spec("socksio") is None
        ):
            raise ValueError(
                "OUTBOUND_PROXY_URL 使用 socks 代理时需要安装 socksio 依赖"
            )

    # 路径配置
    @property
    def BASE_DIR(self) -> Path:
        """项目根目录"""
        return Path(__file__).parent.parent

    @property
    def DATA_DIR(self) -> Path:
        """数据目录"""
        return self.BASE_DIR / "data"

    @property
    def LOGS_DIR(self) -> Path:
        """日志目录"""
        return self.BASE_DIR / "logs"

    @property
    def CORS_ALLOWED_ORIGIN_LIST(self) -> list[str]:
        """解析 CORS 来源配置"""
        origins = [
            item.strip()
            for item in (self.CORS_ALLOWED_ORIGINS or "").split(",")
            if item.strip()
        ]
        return origins or ["http://127.0.0.1:5173", "http://localhost:5173"]

    @staticmethod
    def _parse_outbound_proxy_metadata(proxy_url: str) -> tuple[str, str, int] | None:
        normalized = (proxy_url or "").strip()
        if not normalized:
            return None

        parsed = urlsplit(normalized)
        scheme = (parsed.scheme or "").strip().lower()
        if scheme not in SUPPORTED_OUTBOUND_PROXY_SCHEMES:
            supported = ", ".join(sorted(SUPPORTED_OUTBOUND_PROXY_SCHEMES))
            raise ValueError(
                f"OUTBOUND_PROXY_URL 仅支持 {supported}，当前为: {scheme or '<empty>'}"
            )

        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("OUTBOUND_PROXY_URL 的 port 非法") from exc

        if not parsed.hostname or port is None:
            raise ValueError("OUTBOUND_PROXY_URL 必须包含 hostname 和 port")
        if not (1 <= port <= 65535):
            raise ValueError("OUTBOUND_PROXY_URL 的 port 必须在 1-65535 范围内")

        return scheme, parsed.hostname, port

    @staticmethod
    def _format_outbound_proxy_host(hostname: str) -> str:
        if ":" in hostname and not hostname.startswith("["):
            return f"[{hostname}]"
        return hostname

    @property
    def OUTBOUND_PROXY_ENABLED(self) -> bool:
        return self._parse_outbound_proxy_metadata(self.OUTBOUND_PROXY_URL) is not None

    @property
    def OUTBOUND_PROXY_SCHEME(self) -> str:
        proxy_meta = self._parse_outbound_proxy_metadata(self.OUTBOUND_PROXY_URL)
        if proxy_meta is None:
            return ""
        return proxy_meta[0]

    @property
    def OUTBOUND_PROXY_DISPLAY(self) -> str:
        proxy_meta = self._parse_outbound_proxy_metadata(self.OUTBOUND_PROXY_URL)
        if proxy_meta is None:
            return ""

        _, hostname, port = proxy_meta
        return f"{self._format_outbound_proxy_host(hostname)}:{port}"

    @staticmethod
    def _is_missing_or_placeholder(value: str | None) -> bool:
        normalized = str(value or "").strip().lower()
        return normalized in ADMIN_PLACEHOLDER_VALUES

    @property
    def ADMIN_CREDENTIALS_CONFIGURED(self) -> bool:
        """后台账号密码是否是可用配置。"""
        return not (
            self._is_missing_or_placeholder(self.ADMIN_USERNAME)
            or self._is_missing_or_placeholder(self.ADMIN_PASSWORD)
        )

    @property
    def ADMIN_SESSION_SECRET_CONFIGURED(self) -> bool:
        """后台 session secret 是否是可用配置。"""
        return not self._is_missing_or_placeholder(self.ADMIN_SESSION_SECRET)

    @property
    def ADMIN_SESSION_SECRET_EFFECTIVE(self) -> str:
        """SessionMiddleware 使用的 secret，不再退回硬编码弱默认值。"""
        if self.ADMIN_SESSION_SECRET_CONFIGURED:
            return self.ADMIN_SESSION_SECRET.strip()
        return RUNTIME_EPHEMERAL_SESSION_SECRET

    @property
    def ADMIN_SESSION_SECRET_IS_EPHEMERAL(self) -> bool:
        """未配置时仅使用进程内临时 secret，避免固定弱密钥。"""
        return not self.ADMIN_SESSION_SECRET_CONFIGURED

    @property
    def ADMIN_SESSION_SECRET_STRONG_ENOUGH(self) -> bool:
        """粗粒度检查 secret 强度。"""
        return (
            len((self.ADMIN_SESSION_SECRET or "").strip())
            >= MIN_ADMIN_SESSION_SECRET_LENGTH
        )

    @property
    def STARTUP_VALIDATION_ISSUES(self) -> list[str]:
        """部署态启动前必须满足的硬门禁。"""
        issues: list[str] = []
        if not self.ADMIN_CREDENTIALS_CONFIGURED:
            issues.append("admin_credentials_missing_or_placeholder")
        if not self.ADMIN_SESSION_SECRET_CONFIGURED:
            issues.append("admin_session_secret_missing_or_placeholder")
        elif not self.ADMIN_SESSION_SECRET_STRONG_ENOUGH:
            issues.append(
                f"admin_session_secret_too_short(min_length={MIN_ADMIN_SESSION_SECRET_LENGTH})"
            )
        return issues

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
    )


# 全局配置实例
settings = Settings()
