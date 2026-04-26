from app.services.project_service import ProjectService
from app.services.retrieval.embeddings import EmbeddingService
from app.services.retrieval.service import RetrievalService, RetrievedChunk


def test_uploaded_legal_contract_comparison_detects_weakened_redlines():
    service = ProjectService.__new__(ProjectService)
    sections = [
        RetrievedChunk(
            chunk_id="our-1",
            document_id="our",
            document_title="我方采购合同",
            source_type="markdown",
            location="section 1",
            heading="核心条款",
            content=(
                "责任上限原则上不低于过去十二个月已收取服务费总额。"
                "供应商仅可根据我方书面指示进行数据处理，未经同意不得跨境传输。"
                "安全事件应在二十四小时内通知我方。我方保留审计权。"
            ),
            score=0.0,
        ),
        RetrievedChunk(
            chunk_id="cp-1",
            document_id="counterparty",
            document_title="对方修改后的采购合同",
            source_type="markdown",
            location="section 1",
            heading="核心条款",
            content=(
                "责任上限调整为不超过三个月服务费总额。"
                "供应商可根据运营需要将服务数据传输至其关联部署地点。"
                "安全事件将在合理可行范围内尽快通知，但不承诺固定通知时限。"
            ),
            score=0.0,
        ),
    ]

    comparison = service._compare_uploaded_legal_contracts(
        sections=sections,
        our_document_id="our",
        counterparty_document_id="counterparty",
        our_title="我方采购合同",
        counterparty_title="对方修改后的采购合同",
    )

    weakened = comparison["weakened_clauses"]["对方修改后的采购合同"]
    assert "责任上限" in weakened
    assert "安全事件通知" in weakened
    assert comparison["risk_flags"]


def test_legal_comparison_query_lines_use_contract_differences():
    service = ProjectService.__new__(ProjectService)
    comparison = {
        "weakened_clauses": {"对方修改后的采购合同": ["责任上限"]},
        "strict_missing_clauses": {"对方修改后的采购合同": ["审计权"]},
        "clause_evidence": {
            "责任上限": {
                "对方修改后的采购合同": "责任上限调整为不超过三个月服务费总额。",
            }
        },
    }

    lines = service._legal_comparison_query_lines(comparison)

    joined = "\n".join(lines)
    assert "责任上限" in joined
    assert "审计权" in joined
    assert "企业合同红线" in joined or "法务红线" in joined
