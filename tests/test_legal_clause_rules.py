from app.services.project_service import ProjectService
from app.services.retrieval.service import RetrievedChunk


def test_convenience_termination_restriction_is_detected_as_weakened():
    service = ProjectService.__new__(ProjectService)
    sections = [
        RetrievedChunk(
            chunk_id="our-1",
            document_id="our",
            document_title="我方采购合同",
            source_type="markdown",
            location="section 1",
            heading="终止条款",
            content="我方有权基于业务调整需要提前书面通知解除合同。",
            score=0.0,
        ),
        RetrievedChunk(
            chunk_id="cp-1",
            document_id="counterparty",
            document_title="对方修改后的采购合同",
            source_type="markdown",
            location="section 1",
            heading="终止条款",
            content="除非供应商发生重大违约，否则我方不得提前解除合同。",
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

    assert "便利终止" in comparison["weakened_clauses"]["对方修改后的采购合同"]


def test_audit_self_assessment_only_is_detected_as_weakened():
    service = ProjectService.__new__(ProjectService)
    sections = [
        RetrievedChunk(
            chunk_id="our-1",
            document_id="our",
            document_title="我方采购合同",
            source_type="markdown",
            location="section 1",
            heading="审计条款",
            content="如供应商处理我方业务数据，我方有权在合理通知后开展审计或要求提供审计证明。",
            score=0.0,
        ),
        RetrievedChunk(
            chunk_id="cp-1",
            document_id="counterparty",
            document_title="对方修改后的采购合同",
            source_type="markdown",
            location="section 1",
            heading="审计条款",
            content="供应商仅提供年度自评报告，不接受客户现场审计或第三方审计。",
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

    assert "审计权" in comparison["weakened_clauses"]["对方修改后的采购合同"]
