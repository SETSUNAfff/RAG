"""Rebuild the RAG Milvus collection from MySQL, the source of truth."""

from __future__ import annotations

import argparse
import asyncio
from itertools import groupby

from sqlalchemy import select

from config.milvus_client import (
    COLLECTION_NAME,
    DATABASE_NAME,
    get_milvus_client,
    init_milvus,
)
from config.mysql_engine import async_engine, async_session
from crud.milvus.knowledge_chunks import insert_knowledge_chunks
from models.mysql import Chunk, Document
from schemas.mysql import DocumentStatus
from services.embeddings import get_embedding_model


async def _load_source_rows() -> list[tuple]:
    async with async_session() as db:
        statement = (
            select(
                Chunk.id,
                Chunk.document_id,
                Chunk.content,
                Chunk.page_no,
                Chunk.meta,
            )
            .join(Document, Document.id == Chunk.document_id)
            .where(
                Chunk.is_active.is_(True),
                Document.status == DocumentStatus.READY.value,
            )
            .order_by(Chunk.id.asc())
        )
        return list((await db.execute(statement)).all())


async def rebuild(*, check_only: bool = False, batch_size: int = 100) -> None:
    rows = await _load_source_rows()
    document_count = len({row.document_id for row in rows})
    print(f"MySQL source: {len(rows)} active chunks across {document_count} ready documents")
    if check_only:
        return
    if not rows:
        raise RuntimeError("No ready MySQL chunks found; refusing to replace the collection")

    model = await asyncio.to_thread(get_embedding_model)
    client = get_milvus_client()
    client.use_database(DATABASE_NAME)
    if COLLECTION_NAME in client.list_collections():
        try:
            client.release_collection(collection_name=COLLECTION_NAME)
        except Exception:
            pass
        client.drop_collection(collection_name=COLLECTION_NAME)

    init_milvus()
    inserted = 0
    for document_id, grouped_rows in groupby(rows, key=lambda row: row.document_id):
        document_rows = list(grouped_rows)
        for offset in range(0, len(document_rows), batch_size):
            batch = document_rows[offset:offset + batch_size]
            contents = [row.content for row in batch]
            embeddings = await asyncio.to_thread(model.encode, contents)
            insert_knowledge_chunks(
                chunk_id=[row.id for row in batch],
                document_id=document_id,
                embeddings=embeddings.tolist(),
                content_text=contents,
                page_no=[row.page_no or 0 for row in batch],
                metadata=[row.meta or {} for row in batch],
            )
            inserted += len(batch)
            print(f"Inserted {inserted}/{len(rows)} chunks")

    client.load_collection(collection_name=COLLECTION_NAME, timeout=120)
    stats = client.get_collection_stats(collection_name=COLLECTION_NAME)
    print(f"Milvus rebuild complete: row_count={stats.get('row_count')}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Only inspect MySQL source rows")
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    async def run_and_close() -> None:
        try:
            await rebuild(check_only=args.check, batch_size=args.batch_size)
        finally:
            await async_engine.dispose()

    asyncio.run(run_and_close())


if __name__ == "__main__":
    main()
