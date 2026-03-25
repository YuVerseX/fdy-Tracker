# 文档导航

这里放的是项目文档和历史归档。**看当前代码真实状态时，优先看根目录 `README.md` 和 `STATUS.md`。**

## 当前有效文档

- 根目录 `README.md`
  - 项目简介、能力边界、启动方式、目录说明
- 根目录 `STATUS.md`
  - 当前结论、已知限制、下一步优先级
- 根目录 `CONTRIBUTING.md`
  - 约定提交方式、开发流程和最基本协作规则
- 根目录 `CHANGELOG.md`
  - 记录本轮整理和后续显式版本变更
- [江苏人社厅数据源说明](./data-source-jiangsu-hrss.md)
  - 记录当前主数据源的页面结构和抓取思路
- [VPS Docker 部署说明](./deploy-vps-docker.md)
  - 记录单机服务器部署步骤、目录挂载和更新方式
- [1Panel / GHCR 镜像部署说明](./deploy-1panel-ghcr.md)
  - 记录用 GitHub 自动发镜像、1Panel 直接拉镜像的部署方式

## 历史归档

- [归档总览](./archive/README.md)
- 历史规划文档
  - `archive/planning/requirements.md`
  - `archive/planning/technical-solution.md`
  - `archive/planning/mvp-implementation-plan.md`
- 历史整理/验收记录
  - `archive/reports/FEATURE_ACCEPTANCE.md`
  - `archive/reports/PROJECT_STRUCTURE.md`
  - `archive/reports/CLEANUP_REPORT.md`

## 建议阅读顺序

1. 先看根目录 `README.md`
2. 再看根目录 `STATUS.md`
3. 需要看数据源实现时再看 `data-source-jiangsu-hrss.md`
4. 需要了解早期规划或历史记录时再看 `archive/`

## 说明

- `archive/` 里的内容是历史资料，不代表当前实现细节。
- 如果文档和代码冲突，以代码和根目录 `README.md` 为准。
