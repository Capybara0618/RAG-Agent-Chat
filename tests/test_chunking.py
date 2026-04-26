from app.services.ingestion.chunking import semantic_chunk_sections
from app.services.ingestion.connectors import SourceSection


def test_semantic_chunk_sections_splits_long_paragraphs_with_limit():
    long_paragraph = "责任上限条款。" + "供应商责任范围、例外情形、服务费计算口径、间接损失排除等内容。" * 20
    sections = [
        SourceSection(
            heading="责任上限",
            content=long_paragraph,
            location="section 1",
            metadata={},
        )
    ]

    chunks = semantic_chunk_sections(sections, max_chars=450, overlap_chars=80)

    assert len(chunks) >= 2
    assert max(len(chunk["content"]) for chunk in chunks) <= 450
