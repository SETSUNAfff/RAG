from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from config.mysql_engine import get_db
from pydantic import BaseModel
from crud.milvus import delete_document_chunks
from crud.mysql.bm25 import invalidate_bm25_index
from services.cache import invalidate_search_cache
from crud.mysql import (
    create_document,
    delete_document,
    get_document,
    get_document_full_content,
    list_chunks,
    list_documents,
    update_document,
)
from schemas.common import Page
from schemas.mysql import (
    ChunkRead,
    DocumentCreate,
    DocumentRead,
    DocumentStatus,
    DocumentUpdate,
    SourceType,
)
from services.ingestion import SUPPORTED_EXTENSIONS, ingest_uploaded_file

# 文档 CRUD 路由；删除文档时先清 Milvus 向量，再删 MySQL，避免残留脏数据。
router = APIRouter(prefix="/documents")


class BatchDeleteRequest(BaseModel):
    ids: list[int]


def _source_type_from_file_name(file_name: str) -> SourceType:
    extension = Path(file_name).suffix.lower().lstrip(".")
    try:
        return SourceType(extension)
    except ValueError:
        return SourceType.OTHER


@router.get("", response_model=Page[DocumentRead])
async def read_documents(
    db: AsyncSession = Depends(get_db),
    document_status: DocumentStatus | None = Query(default=None, alias="status"),
    source_type: SourceType | None = Query(default=None),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[DocumentRead]:
    items, total = await list_documents(
        db,
        status=document_status,
        source_type=source_type,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def create_new_document(
    data: DocumentCreate,
    db: AsyncSession = Depends(get_db),
) -> DocumentRead:
    return await create_document(db, data)

# 文档入库的主入口，一次上传同时写 MySQL 和 Milvus。
@router.post("/upload", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> DocumentRead:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    extension = Path(file.filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {extension}",
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    document = await create_document(
        db,
        DocumentCreate(
            title=file.filename,
            source_type=_source_type_from_file_name(file.filename),
        ),
    )
    # 同步上传milvus
    try:
        await ingest_uploaded_file(db, file.filename, data, document.id)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    updated = await get_document(db, document.id)
    if updated is None:
        raise HTTPException(
            status_code=500,
            detail="Document disappeared after ingestion",
        )
    return updated


@router.get("/{document_id}/chunks", response_model=Page[ChunkRead])
async def read_document_chunks(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[ChunkRead]:
    # chunks 列表只通过 /documents/{id}/chunks 暴露。
    if await get_document(db, document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found")
    items, total = await list_chunks(
        db,
        document_id=document_id,
        page=page,
        page_size=page_size,
    )
    return Page(items=items, total=total, page=page, page_size=page_size)

# 文档重新上传，先删除milvus中的chunks，再删除mysql中两个表，最后重新上传
@router.post("/{document_id}/reindex", response_model=DocumentRead)
async def reindex_document(
    document_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> DocumentRead:
    if await get_document(db, document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    extension = Path(file.filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {extension}",
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        await ingest_uploaded_file(
            db,
            file.filename,
            data,
            document_id,
            replace_existing=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    document = await get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.get("/{document_id}", response_model=DocumentRead)
async def read_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
) -> DocumentRead:
    document = await get_document(db, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.patch("/{document_id}", response_model=DocumentRead)
async def update_existing_document(
    document_id: int,
    data: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
) -> DocumentRead:
    document = await update_document(db, document_id, data)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_existing_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
) -> Response:
    # 先清理 Milvus 向量；MySQL 侧删除文档时会连带删除 chunks。
    if await get_document(db, document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        delete_document_chunks(document_id)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Milvus cleanup failed: {exc}",
        ) from exc
    await delete_document(db, document_id)
    invalidate_bm25_index()
    # 删除文档后清空 Redis 检索缓存，避免返回已删除内容的检索结果。
    await invalidate_search_cache()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/batch-delete", status_code=status.HTTP_204_NO_CONTENT)
async def batch_delete_documents(
    data: BatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
) -> Response:
    for document_id in data.ids:
        if await get_document(db, document_id) is None:
            continue
        try:
            delete_document_chunks(document_id)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Milvus cleanup failed for document {document_id}: {exc}",
            ) from exc
        await delete_document(db, document_id)
    invalidate_bm25_index()
    await invalidate_search_cache()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{document_id}/content")
async def read_document_content(
    document_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    if await get_document(db, document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found")
    content = await get_document_full_content(db, document_id)
    return {"id": document_id, "content": content}
