import logging
import os

from dotenv import load_dotenv
from pymilvus import MilvusClient

from models.milvus.knowledge_chunks import (
    COLLECTION_NAME,
    DATABASE_NAME,
    EMBEDDING_FIELD,
    INDEX_TYPE,
    METRIC_TYPE,
    SPARSE_EMBEDDING_FIELD,
    SPARSE_INDEX_TYPE,
    SPARSE_METRIC_TYPE,
    schema as collection_schema,
)

load_dotenv(override=True)
MILVUS_DEFAULT_PORT = 19530


def _parse_milvus_address(address: str) -> tuple[str, int]:
    if ":" in address:
        host, _, port = address.rpartition(":")
        if port.isdigit():
            return host, int(port)
    return address, MILVUS_DEFAULT_PORT


MILVUS_HOST, MILVUS_PORT = _parse_milvus_address(
    os.getenv("MILVUS_HOST", "127.0.0.1")
)
logger = logging.getLogger(__name__)

# Milvus 客户端使用惰性单例，导入模块时不会连接外部服务。
_client: MilvusClient | None = None


def get_milvus_client() -> MilvusClient:
    # 首次使用时创建客户端，后续复用同一个实例。
    global _client
    if _client is None:
        _client = MilvusClient(host=MILVUS_HOST, port=MILVUS_PORT)
    return _client


def init_milvus() -> None:
    """Create the RAG database and collection when they are missing."""
    client = get_milvus_client()
    if DATABASE_NAME not in client.list_databases():
        client.create_database(DATABASE_NAME)
        logger.info("Created Milvus database %s", DATABASE_NAME)
    client.use_database(DATABASE_NAME)

    if COLLECTION_NAME not in client.list_collections():
        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name=EMBEDDING_FIELD,
            index_type=INDEX_TYPE,
            metric_type=METRIC_TYPE,
        )
        index_params.add_index(
            field_name=SPARSE_EMBEDDING_FIELD,
            index_type=SPARSE_INDEX_TYPE,
            metric_type=SPARSE_METRIC_TYPE,
        )
        client.create_collection(
            collection_name=COLLECTION_NAME,
            schema=collection_schema,
            index_params=index_params,
        )
        logger.info("Created Milvus collection %s", COLLECTION_NAME)
    else:
        logger.info("Milvus collection %s already exists", COLLECTION_NAME)

    # Milvus 集合必须显式加载后才能搜索，否则会报 channel not available。
    client.load_collection(collection_name=COLLECTION_NAME, timeout=120)
