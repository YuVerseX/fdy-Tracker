# 前端说明

这里是项目的 Vue 3 前端，负责招聘列表、详情和管理页。

## 页面

- `/`：招聘列表
- `/post/:id`：招聘详情
- `/admin`：管理页

## 本地开发

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

## 构建

```bash
cd frontend
npm run build
npm run preview
```

## 环境变量

前端支持两个常用变量：

```env
VITE_API_BASE_URL=
VITE_DEV_API_TARGET=http://127.0.0.1:8000
```

- `VITE_API_BASE_URL` 留空时，前端默认走当前域名下的 `/api`
- `VITE_DEV_API_TARGET` 只给 `npm run dev` 的代理使用
- 不需要改源码里的 API 地址；优先通过 `.env` 配置

## 目录

```text
frontend/
├── src/api/         # API 封装
├── src/router/      # 路由
├── src/views/       # 页面
└── src/style.css    # 全局样式
```

## 说明

- `dist/`、运行日志、`node_modules/` 不进仓库。
- 整体项目状态和能力边界请看根目录 `README.md`。
