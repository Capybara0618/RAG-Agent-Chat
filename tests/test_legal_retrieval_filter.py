from app.services.retrieval.service import ChunkRecord, RetrievalService


def _record(*, title: str, tags: str, content: str = "合同审查红线") -> ChunkRecord:
    return ChunkRecord(
        chunk_id=f"{title}-chunk",
        document_id=f"{title}-doc",
        document_title=title,
        document_tags=tags,
        source_type="markdown",
        location="sec-1",
        content=content,
        heading=title,
        searchable_text=f"{title} {content} {tags}",
        tokens=["合同", "审查", "红线"],
    )


def test_legal_task_filters_out_uploaded_project_contracts():
    records = [
        _record(title="法务核心-合同审查红线指引.md", tags="baseline,legal"),
        _record(title="[p1] 我方采购合同.md", tags="project_artifact,p1,our_procurement_contract,legal_contract"),
        _record(title="[p1] 对方修改后的采购合同.md", tags="project_artifact,p1,counterparty_redline_contract,legal_contract"),
    ]

    filtered = RetrievalService._filter_accessible_chunks_for_task(
        records,
        task_mode="legal_contract_review",
        document_hints=["法务核心", "合同审查", "红线"],
    )

    assert [item.document_title for item in filtered] == ["法务核心-合同审查红线指引.md"]


def test_non_legal_tasks_keep_original_candidate_pool():
    records = [
        _record(title="法务核心-合同审查红线指引.md", tags="baseline,legal"),
        _record(title="[p1] 我方采购合同.md", tags="project_artifact,p1,our_procurement_contract,legal_contract"),
    ]

    filtered = RetrievalService._filter_accessible_chunks_for_task(
        records,
        task_mode="knowledge_qa",
        document_hints=["法务核心"],
    )

    assert [item.document_title for item in filtered] == [
        "法务核心-合同审查红线指引.md",
        "[p1] 我方采购合同.md",
    ]
