from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.v1.router import api_router
from config.mysql_engine import async_engine


# FastAPI 入口：负责创建 app、注册中间件，并挂载 /api/v1 路由。
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 退出时释放 MySQL 异步连接池；Milvus 首次使用时才惰性初始化。
    yield
    await async_engine.dispose()


# 应用实例与基础元信息，OpenAPI 文档默认在 /docs。
app = FastAPI(
    title="RAG API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 暂时全放开，方便本地 Streamlit/前端联调。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 所有业务接口统一挂在 /api/v1 下。
app.include_router(api_router, prefix="/api/v1")


# 根路径只用于快速确认服务身份，不承担业务逻辑。
@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    return {"service": "RAG API", "docs": "/docs"}


# 存活探针0不依赖 MySQL/Milvus，便于负载均衡和容器编排检查。
@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8200)
