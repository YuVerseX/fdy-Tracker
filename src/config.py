"""应用配置模块"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置"""

    # 应用配置
    APP_NAME: str = "江苏专职辅导员招聘追踪系统"
    DEBUG: bool = True

    # 数据库配置
    DATABASE_URL: str = "sqlite:///./data/fdy_tracker.db"

    # 爬虫配置
    SCRAPER_INTERVAL: int = 7200  # 2小时（秒）
    REQUEST_TIMEOUT: int = 30  # 请求超时（秒）
    REQUEST_DELAY_MIN: float = 1.0  # 最小延迟（秒）
    REQUEST_DELAY_MAX: float = 3.0  # 最大延迟（秒）

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
    )


# 全局配置实例
settings = Settings()
