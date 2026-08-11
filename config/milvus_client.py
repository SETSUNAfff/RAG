from pymilvus import MilvusClient
from dotenv import load_dotenv
import os

from models.milvus.knowledge_chunks import (
    COLLECTION_NAME,
    DATABASE_NAME,
    EMBEDDING_FIELD,
    INDEX_TYPE,
    METRIC_TYPE,
    schema as collection_schema,
)

load_dotenv(override=True)
MILVUS_HOST = os.getenv('MILVUS_HOST')

client = MilvusClient(host=MILVUS_HOST)

# 连接milvus数据库，创建集合
def create_collection(database_name:str,collection_name:str):
    if database_name not in client.list_databases():
        client.create_database(database_name)
        print(f'[{database_name}]数据库已创建')
    client.use_database(database_name)
    print(f"已切换至[{database_name}]数据库")

    if collection_name not in client.list_collections():
        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name=EMBEDDING_FIELD,
            index_type=INDEX_TYPE,
            metric_type=METRIC_TYPE,
        )
        client.create_collection(
            collection_name=collection_name,
            schema=collection_schema,
            index_params=index_params,
        )
        print(f'[{collection_name}]表已创建')
        show_collections = client.list_collections()
        print(show_collections)
    else:
        print(f'{collection_name}表已存在')

create_collection(DATABASE_NAME, COLLECTION_NAME)
