from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


# 列表接口统一使用该分页信封，保证前端分页字段一致。
class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
