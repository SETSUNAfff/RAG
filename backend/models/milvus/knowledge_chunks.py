from pymilvus import CollectionSchema, DataType, FieldSchema, Function, FunctionType

DATABASE_NAME = "RAG"
COLLECTION_NAME = "knowledge_chunks"
EMBEDDING_DIMENSION = 768
METRIC_TYPE = "COSINE"
INDEX_TYPE = "AUTOINDEX"
SPARSE_INDEX_TYPE = "SPARSE_INVERTED_INDEX"
SPARSE_METRIC_TYPE = "BM25"

CHUNK_ID_FIELD = "chunk_id"
EMBEDDING_FIELD = "embedding"
DOCUMENT_ID_FIELD = "document_id"
PAGE_NO_FIELD = "page_no"
METADATA_FIELD = "metadata"
CONTENT_TEXT_FIELD = "content_text"
SPARSE_EMBEDDING_FIELD = "sparse_embedding"

# chunk 默认 500 字，中文 UTF-8 每字 3 字节；预留充足余量。
CONTENT_TEXT_MAX_LENGTH = 4096
METADATA_MAX_LENGTH = 8192


bm25_function = Function(
    name="bm25",
    function_type=FunctionType.BM25,
    input_field_names=[CONTENT_TEXT_FIELD],
    output_field_names=[SPARSE_EMBEDDING_FIELD],
)


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
        # Store metadata as serialized JSON text. Milvus 3.0.0 local storage
        # can fail to reload JSON shredding statistics on Windows bind mounts.
        FieldSchema(
            name=METADATA_FIELD,
            dtype=DataType.VARCHAR,
            max_length=METADATA_MAX_LENGTH,
        ),
        FieldSchema(
            name=CONTENT_TEXT_FIELD,
            dtype=DataType.VARCHAR,
            max_length=CONTENT_TEXT_MAX_LENGTH,
            enable_analyzer=True,
            analyzer_params={"tokenizer": "jieba"},
        ),
        FieldSchema(name=SPARSE_EMBEDDING_FIELD, dtype=DataType.SPARSE_FLOAT_VECTOR),
    ],
    description="RAG knowledge chunks",
    functions=[bm25_function],
)
