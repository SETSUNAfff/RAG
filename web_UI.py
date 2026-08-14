import streamlit as st

from services.ingestion import SUPPORTED_FILE_TYPES, extract_text


st.title("知识库更新服务")

uploaded_file = st.file_uploader(
    label="请上传 PDF、Word、Markdown、HTML 或文本文件",
    type=SUPPORTED_FILE_TYPES,
    accept_multiple_files=False,
)

if uploaded_file is not None:
    file_name = uploaded_file.name
    file_type = uploaded_file.type or "未知"
    file_size = uploaded_file.size / 1024
    st.subheader(f"文件名称: {file_name}")
    st.write(f"文件类型: {file_type}，文件大小：{file_size:.2f}KB")

    try:
        text = extract_text(file_name, uploaded_file.getvalue())
        st.text_area("提取文本", text, height=400)
    except Exception as exc:
        st.error(f"文件解析失败：{exc}")
