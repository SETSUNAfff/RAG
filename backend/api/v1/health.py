from fastapi import APIRouter

router = APIRouter()


# 存活探针，不访问数据库或向量库。
@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
