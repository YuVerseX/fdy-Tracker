# 文档导航

这里放的是当前对外文档。**看当前代码真实状态时，优先看根目录 `README.md` 和 `STATUS.md`。**

## 当前有效文档

- 根目录 `README.md`
  - 项目简介、能力边界、启动方式、目录说明
- 根目录 `STATUS.md`
  - 当前结论、已知限制、下一步优先级
- 根目录 `CONTRIBUTING.md`
  - 约定提交方式、开发流程和最基本协作规则
- 根目录 `SECURITY.md`
  - 安全问题上报和密钥管理基线
- 根目录 `CHANGELOG.md`
  - 记录本轮整理和后续显式版本变更
- [发布检查清单](./release-checklist.md)
  - 推送 GitHub / 打 tag / 部署前的收口检查
- [测试分层策略](./test-strategy.md)
  - 记录核心回归、AI 专项回归和完整回归的执行口径
- [江苏人社厅数据源说明](./data-source-jiangsu-hrss.md)
  - 记录当前主数据源的页面结构和抓取思路
- [VPS Docker 部署说明](./deploy-vps-docker.md)
  - 记录单机服务器部署步骤、目录挂载和更新方式
- [1Panel / GHCR 镜像部署说明](./deploy-1panel-ghcr.md)
  - 记录用 GitHub 自动发镜像、1Panel 直接拉镜像的部署方式

## 建议阅读顺序

1. 先看根目录 `README.md`
2. 再看根目录 `STATUS.md`
3. 需要看数据源实现时再看 `data-source-jiangsu-hrss.md`

## 说明

- `docs/archive/` 已默认加入 `.gitignore`，不进入公开仓库。
- 如果文档和代码冲突，以代码和根目录 `README.md` 为准。
