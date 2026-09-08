# RAG API

面向企业内部知识库与客服助手场景的 RAG + Agent 问答后端。系统支持文档上传入库、混合检索、rerank、流式问答、引用溯源、多轮会话和离线评测，核心工程组件为 FastAPI、MySQL、Milvus、Redis 与 LangChain Agent。

## 功能特性

- 文档入库：支持 PDF、DOCX、Markdown、HTML、TXT；自动提取正文、清洗文本、递归切分、生成 embedding；MySQL 与 Milvus 使用同一个 `chunk_id` 双写，支持重传更新（版本 +1）、删除和批量删除。
- 混合检索：Milvus 稠密向量（COSINE）+ Milvus 内置 BM25 稀疏检索（jieba 分词），通过 RRF 融合，可选 CrossEncoder rerank；结果按 5 分钟窗口缓存到 Redis，支持按文档范围过滤。
- Agent 问答：LangChain Agent 通过 `knowledge_search` 工具调用检索，LLM 使用 OpenAI 兼容接口（默认 DeepSeek）；SSE 流式推送 `connected`、`status`、`token`、`citations`、`done`、`suggestions`事件；强制引用证据、无证据时拒答，并在生成后清洗答案。
- 多轮会话：会话与消息 CRUD 落库到 MySQL，对话历史先读 Redis 缓存、缺失时从 MySQL 回填，并受 token 预算裁剪。
- 离线评测：从 JSON 导入评测用例，后台运行评测批次，输出 `retrieval_precision`、`retrieval_recall`、`recall_at_20`、`mrr`、`hit`、`rouge_l`、`embedding_sim` 等指标，并按章节与难度聚合。
- 数据对账：`admin/reconcile` 检查 Milvus 与 MySQL 数据一致性，清理孤儿向量，将向量缺失或入库中断的文档标记为失败。
- 部署与可观测：提供 `Dockerfile`、不依赖外部服务的 `/health` 存活探针以及 `/docs` OpenAPI 文档。

## 技术栈

| 组件 | 选型 |
| --- | --- |
| 语言 / 运行时 | Python 3.11+ |
| Web 框架 | FastAPI + Uvicorn |
| 关系数据库 | MySQL 8 + SQLAlchemy 2 (async) + aiomysql |
| 数据库迁移 | Alembic |
| 向量数据库 | Milvus（Dense + Sparse BM25 + RRF） |
| 缓存 | Redis |
| Agent | LangChain Agent + LangChain Chat Models |
| 模型 | SentenceTransformer embedding / rerank，DeepSeek 等 OpenAI 兼容 LLM |

## 架构

```mermaid
flowchart LR
    U[用户] --> C[Chat API SSE]
    C --> A[Agent 编排]
    A --> R[混合检索]
    R --> V[(Milvus)]
    R --> H[(MySQL)]
    R --> RR[Rerank]
    A --> M[LLM API]
    D[文档上传] --> IN[文档解析与入库]
    IN --> V
    IN --> H
    EV[评测集] --> E[离线评测]
    E --> RPT[评测报告]
```

## 项目结构

```text
.
├── alembic/            # Alembic 数据库迁移
├── api/v1/             # FastAPI 路由
├── config/             # MySQL / Redis / Milvus 配置与客户端
├── crud/               # MySQL 与 Milvus 数据访问层
├── models/             # MySQL 与 Milvus 数据模型
├── schemas/            # Pydantic 请求 / 响应模型
├── services/           # 检索、入库、Agent、评测、对账等业务服务
├── tests/              # 单元 / 冒烟测试与评测用例导入脚本
├── .env.example        # 环境变量示例
├── Dockerfile
├── main.py             # FastAPI 入口
├── rag-design.md       # 设计文档
└── requirements.txt
```

## 快速开始

### 环境要求

- Python 3.11 或更高版本
- MySQL 8
- Redis
- Milvus（需要使用支持内置 BM25 Function 和 jieba analyzer 的版本）
- DeepSeek API Key 或其他 OpenAI 兼容 API
- 本地 embedding 与 rerank 模型文件（Milvus schema 固定为 768 维向量，请选用输出 768 维的模型，如 m3e-base 或 bge 系列 base 模型）

### 1. 克隆项目并安装依赖

```bash
git clone https://github.com/SETSUNAfff/RAG.git
cd RAG

python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux / macOS

pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

按注释填写 `.env`：

| 变量 | 说明 |
| --- | --- |
| `ASYNC_DATABASE_URL` | MySQL 异步连接串，例如 `mysql+aiomysql://user:password@localhost:3306/rag` |
| `REDIS_URL` | Redis 地址 |
| `CHAT_HISTORY_TOKEN_BUDGET` | 喂给模型的历史消息 token 预算 |
| `DEEPSEEK_API_KEY` | LLM API Key |
| `DEEPSEEK_BASE_URL` | OpenAI 兼容 API 地址，默认 `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | 模型名，默认 `deepseek-chat` |
| `EMBEDDING_MODEL_NAME` | embedding 模型名（备用字段） |
| `EMBEDDING_MODEL_PATH` | 本地 embedding 模型目录 |
| `RERANK_MODEL_PATH` | 本地 rerank 模型目录 |
| `MILVUS_HOST` | Milvus 地址，可带端口，例如 `127.0.0.1` 或 `127.0.0.1:19530` |
| `RETRIEVAL_FILTER_ENABLED` | 是否启用证据精度过滤，建议先保持 `false` |
| `RETRIEVAL_FILTER_MIN_RATIO` | 保留证据相对最高 rerank 分的最小比例 |
| `RETRIEVAL_MAX_EVIDENCE_PER_CALL` | 单次检索最多返回的证据数 |

### 3. 初始化数据库

```sql
CREATE DATABASE rag CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

```bash
alembic upgrade head
```

Milvus 的 database 与 collection 会在首次上传或检索时自动创建并加载，无需手工初始化。

### 4. 启动服务

```bash
python main.py
```

- 服务地址：`http://localhost:8200`
- API 文档：`http://localhost:8200/docs`
- 健康检查：`http://localhost:8200/health`

可选：导入离线评测用例

```bash
python tests/import_evaluation_cases.py evaluation_cases.json [--replace]
```

### 5. 运行测试

```bash
pytest
```

## Docker 部署

Dockerfile 使用 CPU 版 PyTorch，并暴露 8200 端口：

```bash
docker build -t rag-api .
docker run --rm -p 8200:8200 --env-file .env rag-api
```

注意：本地模型路径在容器内未必存在，构建镜像前需要把 embedding / rerank 模型放入镜像可访问的路径，并同步调整 `.env` 中的模型路径；MySQL、Redis、Milvus 也需要从容器内可达。

## API 概览

| 模块 | 端点 |
| --- | --- |
| 健康检查 | `GET /health` |
| 聊天 | `POST /api/v1/chat`（SSE 流式） |
| 文档 | `GET/POST /api/v1/documents`，`POST /api/v1/documents/upload`，`POST /api/v1/documents/batch-delete`，`GET/PATCH/DELETE /api/v1/documents/{id}`，`POST /api/v1/documents/{id}/reindex`，`GET /api/v1/documents/{id}/chunks`，`GET /api/v1/documents/{id}/content` |
| 会话 | `GET/POST /api/v1/conversations`，`GET/PATCH/DELETE /api/v1/conversations/{id}` |
| 消息 | `GET/POST /api/v1/messages`，`GET/PATCH/DELETE /api/v1/messages/{id}` |
| 配置 | `GET /api/v1/config` |
| 评测 | `GET/POST/PATCH/DELETE /api/v1/evaluations/cases`，`POST /api/v1/evaluations/cases/import`，`POST/GET /api/v1/evaluations/runs`，`GET /api/v1/evaluations/runs/{id}`，`GET /api/v1/evaluations/runs/{id}/results` |
| 管理 | `POST /api/v1/admin/reconcile`，`GET /api/v1/admin/reconcile/{task_id}` |

### 流式聊天

```bash
curl -N http://localhost:8200/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "conversation_id": null,
    "user_id": "anonymous",
    "question": "年假可以累计到明年吗",
    "history": [],
    "source_ids": null
  }'
```

服务端按 `data: {...}` 格式推送事件，事件类型包括：

- `connected`：连接建立，携带 `conversation_id`
- `status`：检索 / 生成等状态
- `token`：增量回答文本
- `citations`：回答引用来源
- `done`：完整回答、引用、`trace_id` 与 `conversation_id`
- `suggestions`：推荐追问
- `error`：错误信息

## 离线评测

评测用例位于 `evaluation_cases.json`，每条用例包含 `question`、`expected_answer` 与期望来源。评测任务通过 `POST /api/v1/evaluations/runs` 触发，在后台逐条执行检索与问答，并输出：

- `retrieval_precision` / `retrieval_recall` / `recall_at_20`
- `mrr` / `hit`
- `rouge_l` / `embedding_sim`

评测报告可按困难度（`difficulty`）和章节（`chapter`）聚合查看。

## 设计文档

更完整的架构决策、数据模型与评测方案见 [rag-design.md](rag-design.md)。
