# RAG_UI

基于 Vue 2 + Element UI 的企业知识库 RAG 前端。

## 功能

- 知识问答：会话管理、历史消息、SSE 流式回答、Markdown 渲染、引用来源。
- 文档管理：上传、列表、状态筛选、标题搜索、详情分片、删除、重新入库。
- 效果评测：真实调用后端接口，当前后端未实现时展示 501 提示。

## 本地运行

后端默认运行在 `http://127.0.0.1:8001`：

```bash
cd G:\素材\work5\RAG
uvicorn main:app --reload --port 8001
```

前端：

```bash
cd G:\素材\work5\RAG_UI
npm install
npm run serve
```

访问 `http://localhost:8080`。开发环境通过 `vue.config.js` 将 `/api` 代理到后端。

## 环境变量

复制 `.env.example` 为 `.env.development` 或直接修改已有文件：

- `VUE_APP_API_BASE=/api/v1`
- `VUE_APP_BACKEND_URL=http://127.0.0.1:8001`
- `VUE_APP_PORT=8080`
