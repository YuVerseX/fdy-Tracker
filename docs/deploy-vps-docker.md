# VPS Docker 部署说明

这份文档对应当前仓库自带的**单机 VPS 双容器部署**方案：

- `api`：FastAPI 后端
- `web`：Nginx 托管前端静态文件，并反代 `/api`

这是**源码构建型**部署方式，适合：

- 你先追求本地和服务器都能直接 build
- 你愿意通过 `git pull + docker compose up -d --build` 更新

如果你准备用 1Panel 直接拉镜像更新，优先看 `deploy-1panel-ghcr.md`。

## 适用场景

- 你只有一台 VPS
- 先追求能稳定跑起来
- 还没有接入独立数据库、监控、HTTPS

## 1. 服务器准备

确保 VPS 已安装：

- Docker
- Docker Compose Plugin（命令是 `docker compose`）

建议至少：

- 2 核 CPU
- 2 GB 内存

## 2. 拉代码并准备配置

```bash
git clone <你的仓库地址>
cd fdy-Tracker
cp .env.example .env
```

然后按需改 `.env`，至少关注：

- `DEBUG=false`
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `AI_ANALYSIS_MODEL`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `ADMIN_SESSION_SECRET`
- `ADMIN_SESSION_MAX_AGE_SECONDS`
- `ADMIN_SESSION_SECURE`
- `CORS_ALLOWED_ORIGINS`
- `WEB_PORT`

如果 `ADMIN_USERNAME` / `ADMIN_PASSWORD` / `ADMIN_SESSION_SECRET` 任一留空，管理接口会返回 `503`，管理页不能登录。

管理页现在使用页面内会话登录，不再弹浏览器原生 Basic Auth 登录框。

如果你暂时不用 AI，可以把：

```env
AI_ANALYSIS_ENABLED=false
```

## 3. 启动

```bash
docker compose up -d --build
```

启动后默认访问：

- 首页：`http://你的服务器IP/`
- 管理页：`http://你的服务器IP/admin`
- Swagger：`http://你的服务器IP/docs`
- 健康检查：`http://你的服务器IP/api/health`

## 4. 目录说明

- `./data`：SQLite 数据库、附件和解析结果
- `./logs`：运行日志预留目录

这两个目录已经挂载到容器外，重建容器不会丢。

## 5. 常用命令

看日志：

```bash
docker compose logs -f
docker compose logs -f api
docker compose logs -f web
```

重启：

```bash
docker compose restart
```

更新代码后重建：

```bash
git pull
docker compose up -d --build
```

停止：

```bash
docker compose down
```

## 6. 当前边界

这套方案是“能部署、能跑”的基线，不是完整生产方案。当前还没补：

- HTTPS
- 监控告警
- 独立数据库
- 自动部署 / 自动回滚

## 7. 进一步建议

如果你准备长期跑，下一步建议补这几个：

1. 用域名接 `Caddy` 或宿主机 `Nginx`，把 `80/443` 和 HTTPS 收掉。
2. 把 SQLite 升级到 `PostgreSQL`。
3. 加最小监控和备份。
