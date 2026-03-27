"""FastAPI 应用入口"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from starlette.middleware.sessions import SessionMiddleware
from src.config import settings
from src.api import admin, health, posts
from src.database.bootstrap import initialize_database
from src.scheduler.jobs import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    logger.info("应用启动中...")
    initialize_database()
    start_scheduler()
    yield
    # 关闭时执行
    logger.info("应用关闭中...")
    stop_scheduler()

# 创建 FastAPI 应用
app = FastAPI(
    title=settings.APP_NAME,
    description="江苏省专职辅导员招聘信息追踪系统",
    version="1.1.0",
    debug=settings.DEBUG,
    lifespan=lifespan
)

# Session 中间件配置
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.ADMIN_SESSION_SECRET or "dev-session-secret",
    same_site="lax",
    https_only=settings.ADMIN_SESSION_SECURE,
    max_age=settings.ADMIN_SESSION_MAX_AGE_SECONDS,
)

# CORS 中间件配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGIN_LIST,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(health.router, prefix="/api", tags=["健康检查"])
app.include_router(posts.router, prefix="/api", tags=["招聘信息"])
app.include_router(admin.router, prefix="/api", tags=["后台管理"])


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "欢迎使用江苏专职辅导员招聘追踪系统",
        "docs": "/docs",
        "health": "/api/health"
    }
