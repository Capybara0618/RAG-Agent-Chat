from app.services.project_service import ProjectService
from app.services.retrieval.embeddings import EmbeddingService
from app.services.retrieval.service import RetrievalService


def test_build_default_legal_review_query_is_semantic_and_structured():
    service = ProjectService.__new__(ProjectService)
    service.LEGAL_OUR_CONTRACT_ARTIFACT_TYPES = ("our_procurement_contract",)
    service.LEGAL_COUNTERPARTY_CONTRACT_ARTIFACT_TYPES = ("counterparty_redline_contract",)
    service.LEGAL_CONCERN_DESCRIPTIONS = ProjectService.LEGAL_CONCERN_DESCRIPTIONS
    service.repository = type("Repo", (), {"list_artifacts": lambda self, db, project_id: []})()
    service._artifact_for_vendor = lambda *args, **kwargs: None
    service._legal_artifact_document_title = lambda *args, fallback_title, **kwargs: fallback_title

    comparison = {
        "strict_missing_clauses": {"对方修改后的采购合同": ["审计权", "保密义务"]},
        "weakened_clauses": {"对方修改后的采购合同": ["责任上限", "安全事件通知"]},
        "blocking_clauses": {"对方修改后的采购合同": ["审计权", "责任上限"]},
        "watch_clauses": {"对方修改后的采购合同": ["付款条款"]},
        "clause_evidence": {
            "责任上限": {"对方修改后的采购合同": "责任上限调整为不超过三个月服务费总额。"},
            "安全事件通知": {"对方修改后的采购合同": "发生安全事件后仅承诺尽快通知，不承诺固定时限。"},
        },
    }
    project = type(
        "Project",
        (),
        {
            "id": "p1",
            "title": "客服系统采购",
            "summary": "采购客服 SaaS，进入法务合同审查。",
            "data_scope": "customer_data",
            "budget_amount": 580000,
            "category": "customer-support-saas",
            "business_value": "统一客服流程并降低响应时长。",
        },
    )()
    vendor = type("Vendor", (), {"id": "v1", "vendor_name": "云服科技"})()

    query = service._build_default_legal_review_query(None, project, vendor, contract_comparison=comparison)

    assert "业务场景=" in query
    assert "差异摘要=" in query
    assert "差异描述=" in query
    assert "合同片段=" in query
    assert "审查关注=" in query
    assert "责任上限弱化" in query
    assert "整体赔付范围被明显压缩" in query
    assert "项目会涉及客户服务记录、工单内容或相关业务数据" in query
    assert len(query) < 1400


def test_legal_query_rewrite_prefers_semantic_difference_description():
    retrieval = RetrievalService.__new__(RetrievalService)
    retrieval.embedding_service = EmbeddingService()
    query = (
        "法务合同红线审查\n"
        "项目=客服系统采购\n"
        "供应商=云服科技\n"
        "业务场景=采购客服 SaaS；项目会涉及客户服务记录、工单内容或相关业务数据；预算规模较大，按正式采购和标准红线审查\n"
        "差异摘要=责任上限弱化；审计权缺失；数据处理弱化\n"
        "差异描述=对方版本在整体赔付范围被明显压缩方面做了更宽松的修改；对方版本没有保留我方对供应商的核查与监督能力相关约束；对方版本在数据使用、存放或传输边界被放宽方面做了更宽松的修改\n"
        "合同片段=责任上限调整为不超过三个月服务费总额 | 仅提供年度自评报告，不接受客户现场审计 | 可按运营需要将服务数据传输至关联部署地点\n"
        "检索主题=云服务合同底线、标准模板要求、数据与安全边界\n"
        "审查关注=需要判断这些改动是否突破公司在赔付边界、监督核查和数据控制上的底线\n"
        "输出要求=结合合同差异和制度依据，给出风险原因、引用依据、建议动作\n"
    )

    rewritten = retrieval.rewrite_query(query)
    variants = retrieval.build_query_variants(
        query,
        {"query_variants": ["客服 SaaS 客户数据场景 赔付边界被压缩 监督核查被削弱 数据与安全边界"]},
    )

    assert "整体赔付范围被明显压缩" in rewritten
    assert "核查与监督能力相关约束" in rewritten
    assert "项目会涉及客户服务记录" in rewritten
    assert len(variants) >= 3
