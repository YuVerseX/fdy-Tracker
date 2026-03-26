# Changelog

本文件记录仓库层面的重要变化，不追求补齐所有历史细节。

## [Unreleased]

- 管理任务改为 `202` 异步提交，后台执行并记录 `running -> success/failed` 状态流转
- 管理任务记录新增 `phase`、`progress`、`heartbeat_at`，管理页支持进度条、卡住提示与任务重试
- 重复治理一期完成：软去重字段、去重摘要、历史补齐任务、默认隐藏重复记录
- 去重补齐进度细化：候选比对阶段可持续更新任务进度
- 新增 `SECURITY.md` 安全策略说明
- 新增 `docs/release-checklist.md` 发布检查清单
- 补 GitHub Actions `CI` 工作流（后端 unittest + 前端 build）
- 文档入口重写，统一以根目录 `README.md` 和 `STATUS.md` 为准
- 补充 `LICENSE`、`CONTRIBUTING.md`、`CHANGELOG.md`
- 历史规划和历史整理记录迁入 `docs/archive/`
- 收口日志与临时文件忽略规则，仓库默认不保留运行日志
- 补齐单机 VPS 的 Docker 双容器部署基线，前端默认走同域名 `/api` 反代
- 补 GitHub Actions 自动发布 GHCR 镜像，新增 1Panel / GHCR 镜像部署编排

## [1.1.0] - 2026-03-25

- 打通江苏人社厅抓取、解析、入库、API、前端、管理台主链路
- 补齐附件下载与解析、岗位级抽取、岗位统计摘要
- 接入 AI 分析能力，并保留规则分析回退
- 完成列表页、详情页、管理页和基础回归测试
