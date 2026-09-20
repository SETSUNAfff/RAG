from fastapi import APIRouter

router = APIRouter()

_DEFAULT_CONFIG = {
    "brand_name": "超绝智能回答助手",
    "welcome_title": "了解你的所想",
    "welcome_subtitle": "现在开始检索",
    "welcome_questions": [
        "这个产品的退款规则是什么？",
        "基础版和专业版有什么区别？",
        "试用版到期后数据会保留多久？",
    ],
}


@router.get("/config")
async def get_config() -> dict:
    return _DEFAULT_CONFIG
