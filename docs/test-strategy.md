# 测试策略（分层执行）

## 结论

- 现有测试先全部保留，不删。
- 当前这批测试覆盖了抓取、解析、筛选、去重、任务调度、管理接口和 AI 分析，删掉会直接降低回归兜底能力。
- 先通过“分层执行”解决“测试多、跑得慢”的问题，再决定是否归档。

## 分层

### 1) 核心回归（PR 必跑）

覆盖主链路和高风险逻辑，建议每次改代码都跑：

- `tests.test_api`
- `tests.test_admin_api`
- `tests.test_admin_task_service`
- `tests.test_scraper_service`
- `tests.test_attachment_service`
- `tests.test_duplicate_service`
- `tests.test_post_job_service`
- `tests.test_scheduler_jobs`
- `tests.test_parser`
- `tests.test_filter_service`

命令：

```bash
python -m unittest -v tests.test_api tests.test_admin_api tests.test_admin_task_service tests.test_scraper_service tests.test_attachment_service tests.test_duplicate_service tests.test_post_job_service tests.test_scheduler_jobs tests.test_parser tests.test_filter_service
```

### 2) AI 专项回归（改 AI 逻辑时必跑）

- `tests.test_ai_analysis_service`
- `tests.test_ai_insight_service`

命令：

```bash
python -m unittest -v tests.test_ai_analysis_service tests.test_ai_insight_service
```

### 3) 完整回归（发版/部署前必跑）

命令：

```bash
python -m unittest discover -s tests -v
```

## 可归档判断（先不执行）

只有同时满足下面条件，才考虑归档或合并测试：

1. 连续 2 个版本没有覆盖到任何线上问题。
2. 与其它测试有明显重复，且删掉后关键路径覆盖不下降。
3. 执行耗时明显偏高，并且有更小粒度替代测试。

## 执行节奏建议

1. 日常开发：跑“核心回归”。
2. 改 AI 逻辑：加跑“AI 专项回归”。
3. 合并主干、打 tag、部署前：跑“完整回归”+ 前端构建。
