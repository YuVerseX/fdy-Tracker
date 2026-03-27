# 发布检查清单（稳妥版）

这份清单用于“准备推 GitHub / 打 tag / 部署前”的最后收口。

## 1. 代码与仓库

- [ ] `git status` 里没有误提交的本地文件（`data/`、`logs/`、`.env`、临时脚本）
- [ ] 文档入口一致：`README.md`、`STATUS.md`、`CONTRIBUTING.md`
- [ ] `CHANGELOG.md` 的 `Unreleased` 已更新

## 2. 安全与配置

- [ ] `.env.example` 不含真实密钥，也不保留默认弱口令
- [ ] `docker-compose*.yml` 不写死真实密钥
- [ ] 仓库扫描无明显密钥痕迹（示例命令）：

```bash
rg -n "sk-[A-Za-z0-9]{10,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}" -S .
```

## 3. 质量门禁

- [ ] 后端测试通过：

```bash
python -m unittest discover -s tests -v
```

- [ ] 前端构建通过：

```bash
cd frontend
npm run build
```

## 4. 关键功能冒烟

- [ ] 管理接口提交返回 `202`
- [ ] 任务状态能走 `running -> success/failed`
- [ ] 管理页能看到 `phase / progress / heartbeat_at`
- [ ] 去重补齐任务进度能连续变化（非单点跳变）

## 5. 发布动作

- [ ] 合并到 `main`
- [ ] 如需发版，打 tag（例如 `v1.2.0`）
- [ ] 确认 GHCR 镜像发布成功（`publish-images.yml`）
- [ ] 部署侧执行拉取与重启（1Panel 或 docker compose）
