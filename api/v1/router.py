from fastapi import APIRouter

# 统一汇总 v1 路由，main.py 只需挂载这一个聚合路由。
from api.v1 import (
    admin,
    chat,
    config,
    conversations,
    documents,
    evaluations,
    health,
    messages,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["健康检查模块"])
api_router.include_router(admin.router, tags=["管理模块"])
api_router.include_router(config.router, tags=["配置模块"])
api_router.include_router(documents.router, tags=["文档模块"])
api_router.include_router(conversations.router, tags=["会话模块"])
api_router.include_router(messages.router, tags=["消息模块"])
api_router.include_router(chat.router, tags=["聊天模块"])
api_router.include_router(evaluations.router, tags=["评估模块"])
