# Security Policy

## 支持范围

当前仓库维护的默认分支为 `main`。安全问题默认按 `main` 最新代码评估。

## 报告方式

如果你发现了安全问题（例如密钥泄露、未鉴权敏感接口、依赖高危漏洞），请不要先公开发 Issue。

建议方式：

1. 在 GitHub 使用私密安全报告（Security Advisories）提交。
2. 如果当前仓库未开启私密报告，再通过维护者约定的私下渠道联系。

## 本项目的安全基线

- 不提交任何真实密钥、令牌、密码到仓库。
- 本地运行配置只放在 `.env`，`.env` 已在 `.gitignore` 里忽略。
- 部署时必须显式设置非空 `ADMIN_USERNAME`、`ADMIN_PASSWORD`、`ADMIN_SESSION_SECRET`，且 session secret 至少 32 个随机字符。
- 公网部署默认要求 `ADMIN_SESSION_SECURE=true`，只允许在本地纯 HTTP 调试时临时改为 `false`。
- `API_DOCS_ENABLED` 部署默认应保持 `false`；如果需要临时查看 OpenAPI，请只在受控网络中短时开启。
- `/admin` 不应直接裸露公网，至少应放在 HTTPS 反向代理后，并加 IP 白名单、额外鉴权或等效访问控制。
- `/docs`、`/openapi.json`、`/redoc` 不应通过前端公网入口暴露。
- 提交前至少检查以下文件是否含真实凭据：
  - `.env.example`
  - `docker-compose*.yml`
  - `docs/*.md`
  - `.github/workflows/*.yml`

## 如果误提交了密钥

请立即执行：

1. 在服务提供方立刻轮换密钥（不要等仓库修复）。
2. 删除仓库中的明文凭据并提交修复。
3. 评估是否需要清理 Git 历史并通知使用者更新。

注意：只删除工作区文件不足以消除泄露风险，先轮换密钥是第一优先级。
