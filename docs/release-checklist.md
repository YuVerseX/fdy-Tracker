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
- [ ] 任务状态覆盖 `queued/pending -> running/processing -> cancel_requested -> success/failed/cancelled`
- [ ] 管理页任务中心展示 canonical `status / stage / live_metrics / final_metrics`
- [ ] AI 岗位任务提交与重试后仍保持 `ai_job_extraction / 智能岗位识别` 展示口径
- [ ] `finalizing` 中间态和 `cancelled` 归档都显式携带 canonical stage，不依赖前端猜测
- [ ] collecting 阶段只显示采集指标，不伪造结果数
- [ ] 运行态每个可操作状态最多一个主动作，终态只保留少量高价值后续动作，`cancel_requested` 不再展示主动作
- [ ] 前台 freshness 仍保持最近一次成功快照语义

## 5. 发布动作

- [ ] 合并到 `main`
- [ ] 如需发版，打 tag（例如 `v1.2.0`）
- [ ] 确认 GHCR 镜像发布成功（`publish-images.yml`）
- [ ] 部署侧执行拉取与重启（1Panel 或 docker compose）
