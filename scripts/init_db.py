"""数据库初始化脚本"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from src.database.bootstrap import initialize_database
from src.config import settings


def init_database():
    """初始化数据库"""
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"数据目录已创建: {settings.DATA_DIR}")
    initialize_database()
    logger.info("数据库表和内置数据源已检查完成；历史维护补齐请通过后台显式触发")
    logger.success("数据库初始化完成！")


if __name__ == "__main__":
    init_database()
