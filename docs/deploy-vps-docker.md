# VPS Docker 部署说明

这份文档对应当前仓库自带的**单机 VPS 双容器部署**方案：

- `api`：FastAPI 后端
- `web`：Nginx 托管前端静态文件，并反代 `/api`

这是**源码构建型**部署方式，适合：

- 你先追求本地和服务器都能直接 build
- 你愿意通过 `git pull + docker compose up -d --build` 更新
- 你能自己补 HTTPS 和最小访问控制，不会把管理入口直接裸露公网

如果你准备用 1Panel 直接拉镜像更新，优先看 `deploy-1panel-ghcr.md`。

## 适用场景

- 你只有一台 VPS
- 先追求能稳定跑起来
- 还没有接入独立数据库和监控，但会在公网入口补 HTTPS 与访问控制

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
- `API_DOCS_ENABLED`
- `CORS_ALLOWED_ORIGINS`
- `WEB_PORT`

`docker compose up` 现在会强制要求你显式填写：

- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `ADMIN_SESSION_SECRET`

任一留空时容器不会启动。
`ADMIN_SESSION_SECRET` 还需要至少 32 个随机字符；过短时后端会拒绝启动。

管理页现在使用页面内会话登录，不再弹浏览器原生 Basic Auth 登录框。

部署默认值建议保持：

```env
ADMIN_SESSION_SECURE=true
API_DOCS_ENABLED=false
```

- `ADMIN_SESSION_SECURE=true`：生产环境必须配合 HTTPS 使用。
- `API_DOCS_ENABLED=false`：默认不从公网入口暴露 `/docs`、`/openapi.json`、`/redoc`。
- 只有在本机或纯内网临时调试 HTTP 时，才建议把 `ADMIN_SESSION_SECURE` 短时设为 `false`。
- 只有在受控网络里短时调试 OpenAPI 时，才建议把 `API_DOCS_ENABLED` 短时设为 `true`。

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
- 健康检查：`http://你的服务器IP/api/health`

额外说明：

- `/admin` 页面仍会对外提供前端入口，但不建议直接裸露公网；至少要在宿主机或上游反向代理层加 HTTPS、IP 白名单、二次鉴权或等效访问控制。
- `/docs`、`/openapi.json`、`/redoc` 默认已在公网入口返回 `404`。
- `/api/health` 现在是 readiness 探针；新部署实例在首轮成功抓取前，顶层 `status` 可能是 `degraded`，但 `ready=true` 仍表示服务已就绪。

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

如果你后面改用 GHCR 镜像部署，不建议把 `latest` 当成稳定部署锚点，优先使用 `v*` 或 `sha-*` 标签。

停止：

```bash
docker compose down
```

## 6. 当前边界

这套方案是“能部署、能跑”的基线，不是完整生产方案。当前还没补：

- 真实 HTTPS 终止与上游访问控制
- 监控告警
- 独立数据库
- 自动部署 / 自动回滚
- 24h 长跑验证与长期高并发下的数据库升级

当前默认还是 SQLite，适合单机轻量部署，不适合作为长期高并发方案。

## 7. 进一步建议

如果你准备长期跑，下一步建议补这几个：

1. 用域名接 `Caddy` 或宿主机 `Nginx`，把 `80/443` 和 HTTPS 收掉。
2. 把 SQLite 升级到 `PostgreSQL`。
3. 加最小监控和备份。
