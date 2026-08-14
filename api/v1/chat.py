from fastapi import APIRouter, HTTPException, status

# 对话接口占位，后续由 services/agent.py 接 RAG 链路。
router = APIRouter(prefix="/chat")


@router.post("", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def chat() -> None:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Chat endpoint is not implemented yet",
    )
