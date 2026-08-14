import asyncio
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from crud.mysql import (
    create_chunk,
    create_conversation,
    create_document,
    create_message,
    delete_chunk,
    delete_conversation,
    delete_document,
    delete_message,
    get_chunk,
    get_conversation,
    get_document,
    get_message,
    list_chunks,
    list_conversations,
    list_documents,
    list_messages,
    update_chunk,
    update_conversation,
    update_document,
    update_message,
)
from schemas.mysql import (
    ChunkCreate,
    ChunkRead,
    ChunkUpdate,
    ConversationCreate,
    ConversationRead,
    ConversationUpdate,
    DocumentCreate,
    DocumentRead,
    DocumentStatus,
    DocumentUpdate,
    MessageCreate,
    MessageRead,
    MessageRole,
    MessageUpdate,
    SourceType,
)


ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
DATABASE_URL = dotenv_values(ENV_PATH)["ASYNC_DATABASE_URL"]


# 每个用例使用独立的 AsyncSession 和连接池，测试结束后统一释放。
@asynccontextmanager
async def db_session():
    engine = create_async_engine(DATABASE_URL)
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    try:
        async with session_factory() as session:
            yield session
    finally:
        await engine.dispose()


# 验证 documents 表：创建、Read schema、更新、按状态筛选、删除，
# 以及不存在记录时 get/update/delete 静默成功。
def test_document_crud() -> None:
    asyncio.run(_document_crud())


async def _document_crud() -> None:
    async with db_session() as db:
        document = None
        try:
            # 创建一条文档，确认主键、默认状态和 Pydantic Read 都能正常使用。
            suffix = uuid.uuid4().hex[:8]
            document = await create_document(
                db,
                DocumentCreate(
                    title=f"测试文档-{suffix}",
                    source_type=SourceType.PDF,
                ),
            )
            assert document.id is not None
            assert document.status == "pending"

            read_document = DocumentRead.model_validate(document)
            assert read_document.id == document.id

            updated = await update_document(
                db,
                document.id,
                DocumentUpdate(status=DocumentStatus.READY),
            )
            assert updated is not None
            assert updated.status == "ready"

            items, total = await list_documents(
                db,
                status=DocumentStatus.READY,
                page=1,
                page_size=10,
            )
            assert total >= 1
            assert any(item.id == document.id for item in items)

            assert (
                await update_document(
                    db,
                    999_999_999,
                    DocumentUpdate(title="不存在"),
                )
                is None
            )

            await delete_document(db, document.id)
            assert await get_document(db, document.id) is None
            document = None
        finally:
            # 即使断言失败，也删除本轮创建的文档，避免污染 rag 库。
            if document is not None:
                await delete_document(db, document.id)


# 验证 chunks 表，并确认 Pydantic 的 metadata 字段与 ORM 的 meta 列能互相转换。
def test_chunk_crud() -> None:
    asyncio.run(_chunk_crud())


async def _chunk_crud() -> None:
    async with db_session() as db:
        document = None
        chunk = None
        try:
            # chunk 依赖 document，因此先创建父表记录，再验证子表 CRUD。
            suffix = uuid.uuid4().hex[:8]
            document = await create_document(
                db,
                DocumentCreate(
                    title=f"Chunk文档-{suffix}",
                    source_type=SourceType.TXT,
                ),
            )
            chunk = await create_chunk(
                db,
                ChunkCreate(
                    document_id=document.id,
                    content="原始内容",
                    metadata={"source": "test"},
                ),
            )
            assert chunk.id is not None
            assert chunk.meta == {"source": "test"}

            read_chunk = ChunkRead.model_validate(chunk)
            assert read_chunk.metadata == {"source": "test"}

            updated = await update_chunk(
                db,
                chunk.id,
                ChunkUpdate(content="更新内容", is_active=False),
            )
            assert updated is not None
            assert updated.content == "更新内容"
            assert updated.is_active is False

            items, total = await list_chunks(
                db,
                document_id=document.id,
                is_active=False,
            )
            assert total == 1
            assert items[0].id == chunk.id

            await delete_chunk(db, chunk.id)
            assert await get_chunk(db, chunk.id) is None
            chunk = None
        finally:
            # 清理顺序先子后父，确保任何失败路径都不会留下测试数据。
            if chunk is not None:
                await delete_chunk(db, chunk.id)
            if document is not None:
                await delete_document(db, document.id)


# 验证 conversations/messages 的关联 CRUD，
# 以及按 user_id、conversation_id 进行列表筛选。
def test_conversation_message_crud() -> None:
    asyncio.run(_conversation_message_crud())


async def _conversation_message_crud() -> None:
    async with db_session() as db:
        conversation = None
        message = None
        try:
            # 先创建会话，再创建属于该会话的消息，验证一对多关系字段。
            suffix = uuid.uuid4().hex[:8]
            conversation = await create_conversation(
                db,
                ConversationCreate(
                    user_id=f"user-{suffix}",
                    title="测试会话",
                ),
            )
            assert conversation.id is not None

            message = await create_message(
                db,
                MessageCreate(
                    conversation_id=conversation.id,
                    role=MessageRole.USER,
                    content="你好",
                    citations=[{"chunk_id": 1}],
                ),
            )
            assert message.id is not None
            assert message.role == "user"

            read_message = MessageRead.model_validate(message)
            assert read_message.citations == [{"chunk_id": 1}]

            updated_message = await update_message(
                db,
                message.id,
                MessageUpdate(content="更新后的消息"),
            )
            assert updated_message is not None
            assert updated_message.content == "更新后的消息"

            updated_conversation = await update_conversation(
                db,
                conversation.id,
                ConversationUpdate(title="新标题"),
            )
            assert updated_conversation is not None
            assert updated_conversation.title == "新标题"

            messages, total = await list_messages(
                db,
                conversation_id=conversation.id,
            )
            assert total == 1
            assert messages[0].id == message.id

            conversations, total = await list_conversations(
                db,
                user_id=conversation.user_id,
            )
            assert total == 1

            await delete_message(db, message.id)
            assert await get_message(db, message.id) is None
            message = None

            await delete_conversation(db, conversation.id)
            assert await get_conversation(db, conversation.id) is None
            conversation = None
        finally:
            # 消息和会话分别清理，避免留下跨用例的关联数据。
            if message is not None:
                await delete_message(db, message.id)
            if conversation is not None:
                await delete_conversation(db, conversation.id)


# 验证外键 ON DELETE CASCADE：删除父表记录后，子表记录也应被删除。
def test_parent_delete_cascades_children() -> None:
    asyncio.run(_parent_delete_cascades_children())


async def _parent_delete_cascades_children() -> None:
    async with db_session() as db:
        document_id = None
        chunk_id = None
        conversation_id = None
        message_id = None
        try:
            # 分别验证 documents -> chunks 和 conversations -> messages 的级联删除。
            suffix = uuid.uuid4().hex[:8]
            document = await create_document(
                db,
                DocumentCreate(
                    title=f"级联文档-{suffix}",
                    source_type=SourceType.HTML,
                ),
            )
            document_id = document.id
            chunk = await create_chunk(
                db,
                ChunkCreate(document_id=document.id, content="级联 chunk"),
            )
            chunk_id = chunk.id
            await delete_document(db, document_id)
            # 删除父记录后刷新会话，避免 ORM 身份映射返回已被级联删除的旧对象。
            db.expire_all()
            assert await get_chunk(db, chunk_id) is None

            conversation = await create_conversation(
                db,
                ConversationCreate(
                    user_id=f"cascade-{suffix}",
                    title="级联会话",
                ),
            )
            conversation_id = conversation.id
            message = await create_message(
                db,
                MessageCreate(
                    conversation_id=conversation.id,
                    role=MessageRole.ASSISTANT,
                    content="级联消息",
                ),
            )
            message_id = message.id
            await delete_conversation(db, conversation_id)
            # 与 documents -> chunks 一样，刷新后再验证 messages 已级联删除。
            db.expire_all()
            assert await get_message(db, message_id) is None
        finally:
            # 级联成功后父记录已删除，这里只兜底清理可能残留的子记录。
            if chunk_id is not None:
                await delete_chunk(db, chunk_id)
            if document_id is not None:
                await delete_document(db, document_id)
            if message_id is not None:
                await delete_message(db, message_id)
            if conversation_id is not None:
                await delete_conversation(db, conversation_id)
