from pymilvus import CollectionSchema, DataType, FieldSchema

DATABASE_NAME = "RAG"
COLLECTION_NAME = "knowledge_chunks"
EMBEDDING_DIMENSION = 768
METRIC_TYPE = "COSINE"
INDEX_TYPE = "AUTOINDEX"

CHUNK_ID_FIELD = "chunk_id"
EMBEDDING_FIELD = "embedding"
DOCUMENT_ID_FIELD = "document_id"
PAGE_NO_FIELD = "page_no"
METADATA_FIELD = "metadata"

schema = CollectionSchema(
    fields=[
        FieldSchema(
            name=CHUNK_ID_FIELD,
            dtype=DataType.INT64,
            is_primary=True,
            auto_id=False,
        ),
        FieldSchema(
            name=EMBEDDING_FIELD,
            dtype=DataType.FLOAT_VECTOR,
            dim=EMBEDDING_DIMENSION,
        ),
        FieldSchema(name=DOCUMENT_ID_FIELD, dtype=DataType.INT64),
        FieldSchema(name=PAGE_NO_FIELD, dtype=DataType.INT64),
        FieldSchema(name=METADATA_FIELD, dtype=DataType.JSON),
    ],
    description="RAG knowledge chunks",
)
