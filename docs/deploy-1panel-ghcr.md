# 1Panel / GHCR 镜像部署说明

这份文档对应当前仓库的**镜像发布型**部署方式：

- GitHub Actions 自动构建并推送镜像到 `GHCR`
- 服务器或 1Panel 直接拉镜像，不再本地 build 源码

## 镜像地址

- 后端：`ghcr.io/yuversex/fdy-tracker-api`
- 前端：`ghcr.io/yuversex/fdy-tracker-web`

默认标签：

- `latest`：`main` 分支最新成功发布
- `sha-*`：某次提交对应镜像
- `v*`：tag 发布时对应版本镜像

## 发布方式

仓库里已经有 GitHub Actions 工作流：

- 文件：`.github/workflows/publish-images.yml`
- 触发：
  - push 到 `main`
  - push `v*` tag
  - 手动触发

## 1Panel 编排怎么用

### 方案 1：路径选择

1. 先把仓库完整拉到服务器，比如 `/opt/fdy-Tracker`
2. 在这个目录下准备 `.env`
3. 在 1Panel 的“容器 -> 编排”里，选择根目录 `docker-compose.ghcr.yml`
4. 启动编排

### 方案 2：编辑器直接粘贴

1. 在服务器准备一个空目录，比如 `/opt/fdy-tracker-ghcr`
2. 在目录里放 `.env`
3. 在 1Panel 的“创建编排”页面直接粘贴 `docker-compose.ghcr.yml` 内容
4. 启动编排

这套方式因为直接拉镜像，所以**不要求服务器上有完整源码**。

## 推荐 `.env`

```env
DEBUG=false
WEB_PORT=8080
GHCR_NAMESPACE=yuversex
IMAGE_TAG=latest

OPENAI_API_KEY=
OPENAI_BASE_URL=
AI_ANALYSIS_MODEL=gpt-5.4
ADMIN_USERNAME=
ADMIN_PASSWORD=
```

`ADMIN_USERNAME` 和 `ADMIN_PASSWORD` 需要你自己显式填写。留空时，管理接口会返回 `503`，管理页不能登录。

如果你后面想固定到某个版本，也可以把：

```env
IMAGE_TAG=latest
```

改成：

```env
IMAGE_TAG=sha-xxxxxxx
```

或：

```env
IMAGE_TAG=v1.1.0
```

## 更新方式

如果 workflow 已经把新镜像推到 GHCR，服务器侧更新就很简单：

```bash
docker compose -f docker-compose.ghcr.yml pull
docker compose -f docker-compose.ghcr.yml up -d
```

在 1Panel 里，对应就是：

- 重新拉取镜像
- 重建 / 重启编排

## 为什么更适合 1Panel

和源码构建型相比，这种方式更适合 1Panel：

- 服务器不用装前端和后端构建环境
- 更新更快
- 回滚更简单
- 编排页面里直接拉镜像就行

## 端口建议

如果你还想用 1Panel 自己的网站、证书和反向代理功能，建议：

```env
WEB_PORT=8080
```

然后让 1Panel 网站反代到：

- `127.0.0.1:8080`

这样不会和 1Panel 自己占用的 `80/443` 冲突。
