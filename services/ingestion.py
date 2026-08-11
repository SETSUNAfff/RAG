"""文档解析与知识库入库服务。"""

from __future__ import annotations

import os
import re
from io import BytesIO
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from docx import Document
from pypdf import PdfReader


SUPPORTED_FILE_TYPES = ["pdf", "docx", "md", "markdown", "html", "htm", "txt"]
SUPPORTED_EXTENSIONS = {f".{extension}" for extension in SUPPORTED_FILE_TYPES}
_TEXT_ENCODINGS = ("utf-8-sig", "gb18030", "utf-16", "latin-1")


def _decode_text(data: bytes) -> str:
    for encoding in _TEXT_ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_text_from_file(file_name: str, data: bytes) -> str:
    """根据文件扩展名从上传文件字节流中提取可检索文本。"""
    extension = Path(file_name).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"不支持的文件类型：{extension or '(无扩展名)'}，"
            f"支持：{', '.join(SUPPORTED_FILE_TYPES)}"
        )

    if extension == ".pdf":
        reader = PdfReader(BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n\n".join(pages)
        if not text.strip():
            raise ValueError("PDF 未提取到文本，请确认文件不是扫描件")
    elif extension == ".docx":
        document = Document(BytesIO(data))
        parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        for table in document.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                if any(cells):
                    parts.append(" | ".join(cells))
        text = "\n".join(parts)
    elif extension in {".html", ".htm"}:
        soup = BeautifulSoup(data, "lxml")
        text = soup.get_text("\n", strip=True)
    else:
        text = _decode_text(data)

    return _normalize_text(text)


def split_text(text: str, chunk_size: int = 500, chunk_overlap: int = 0) -> list[str]:
    """把长文本按语义边界切分，供 embedding 和 Milvus 入库使用。"""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["===========", "\n\n", "\n", "。", "！", "?", " ", ""],
    )
    return splitter.split_text(text)


def ingest_uploaded_file(
    file_name: str,
    data: bytes,
    document_id: int,
    page_no: int = 0,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """解析上传文件并写入 Milvus，返回向量入库结果。"""
    from dotenv import load_dotenv
    from sentence_transformers import SentenceTransformer

    from crud.milvus.knowledge_chunks import replace_document_chunks

    load_dotenv(override=True)
    model_path = os.getenv("EMBEDDING_MODEL_PATH") or os.getenv("EMBEDDING_MODEL_NAME")
    if not model_path:
        raise ValueError("缺少 EMBEDDING_MODEL_PATH 或 EMBEDDING_MODEL_NAME 配置")
    embedding_model = SentenceTransformer(model_path)

    text = extract_text_from_file(file_name, data)
    chunks = split_text(text)
    if not chunks:
        raise ValueError("文件未提取到有效文本")

    embeddings = embedding_model.encode(chunks)
    extension = Path(file_name).suffix.lower().lstrip(".")
    chunk_ids = [
        document_id * 1_000_000_000 + index
        for index in range(1, len(chunks) + 1)
    ]
    page_nos = [page_no] * len(chunks)
    chunk_metadata = [
        {**(metadata or {}), "file_name": file_name, "source_type": extension}
        for _ in chunks
    ]

    return replace_document_chunks(
        chunk_id=chunk_ids,
        document_id=document_id,
        embeddings=embeddings.tolist(),
        page_no=page_nos,
        metadata=chunk_metadata,
    )


def main() -> None:
    """保留原有命令行入口：默认入库项目根目录下的 knowledge.txt。"""
    from dotenv import load_dotenv
    from sentence_transformers import SentenceTransformer

    from crud.milvus.knowledge_chunks import replace_document_chunks

    load_dotenv(override=True)
    model_path = os.getenv("EMBEDDING_MODEL_PATH") or os.getenv("EMBEDDING_MODEL_NAME")
    if not model_path:
        raise ValueError("缺少 EMBEDDING_MODEL_PATH 或 EMBEDDING_MODEL_NAME 配置")

    text_path = Path(__file__).resolve().parent.parent / "knowledge.txt"
    text = extract_text_from_file(text_path.name, text_path.read_bytes())
    chunks = split_text(text)
    embeddings = SentenceTransformer(model_path).encode(chunks)
    chunk_ids = [1_000_000_000 + index for index in range(1, len(chunks) + 1)]
    page_nos = [0] * len(chunks)
    metadata = [{"file_name": text_path.name, "source_type": "txt"} for _ in chunks]

    result = replace_document_chunks(
        chunk_id=chunk_ids,
        document_id=1,
        embeddings=embeddings.tolist(),
        page_no=page_nos,
        metadata=metadata,
    )
    print(result)


if __name__ == "__main__":
    main()


