# 贡献说明

欢迎提交 Issue 和 PR。这个仓库现在还在持续迭代，提交前先把问题描述清楚，能省很多来回沟通。

## 本地启动

### 后端

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python scripts/init_db.py
python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

### 前端

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

## 提交前至少做这些检查

### 后端（核心回归，提交前必跑）

```bash
python -m unittest -v tests.test_api tests.test_admin_api tests.test_admin_task_service tests.test_scraper_service tests.test_attachment_service tests.test_duplicate_service tests.test_post_job_service tests.test_scheduler_jobs tests.test_parser tests.test_filter_service
```

### 后端（完整回归，发版/部署前必跑）

```bash
python -m unittest discover -s tests -v
```

### 前端

```bash
cd frontend
npm run build
```

### 密钥与配置检查

```bash
rg -n "sk-[A-Za-z0-9]{10,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}" -S .
```

并确认：

- `.env` 没有被跟踪
- `.env.example` 只保留空模板
- 文档里没有真实密钥

## 提交建议

- 尽量做小步提交，不要一口气塞太多不相关改动
- 改接口、筛选逻辑、解析逻辑时，尽量补对应测试
- 改前端交互时，最好附截图或录屏
- 文档改动请同步更新 `README.md` 或 `STATUS.md`
- 发版前按 `docs/release-checklist.md` 走一遍

## 不要提交这些内容

- `data/` 里的本地数据库和附件数据
- `logs/`、`frontend/logs/` 里的运行日志
- 根目录和前端目录下的临时日志文件
- `frontend/dist/`、`node_modules/`、缓存目录
- 本地 `.env`

## 提 Issue 时建议带上

- 复现步骤
- 实际结果
- 预期结果
- 运行环境
- 相关日志或截图

## 提 PR 时建议带上

- 改了什么
- 为什么要改
- 怎么验证
- 还有哪些已知风险

## CI 说明

仓库已配置基础 CI：

- 后端：`python -m unittest discover -s tests -v`
- 前端：`npm run build`

PR 建议等 CI 通过再合并。
AI 逻辑有改动时，建议额外执行：

- `python -m unittest -v tests.test_ai_analysis_service tests.test_ai_insight_service`
