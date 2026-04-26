from pathlib import Path
from types import SimpleNamespace

from app.schemas.chat import QueryResponse
from app.services.ingestion.service import IngestionService
from app.services.project_service import ProjectService


def test_persist_upload_sanitizes_windows_unsafe_filename(tmp_path: Path):
    service = IngestionService.__new__(IngestionService)
    service.settings = SimpleNamespace(storage_dir=tmp_path)

    stored_path = service.persist_upload("项目?:合同*.md", b"hello")

    assert Path(stored_path).exists()
    assert Path(stored_path).name.endswith(".md")
    assert "?" not in Path(stored_path).name
    assert "*" not in Path(stored_path).name
    assert ":" not in Path(stored_path).name


def test_non_critical_watch_items_do_not_force_return():
    service = ProjectService.__new__(ProjectService)
    review = QueryResponse(
        session_id="s1",
        answer="已完成初步合同审查。",
        citations=[],
        confidence=0.82,
        trace_id="t1",
        next_action="answer",
        intent="legal_contract_review",
        task_mode="legal_contract_review",
        debug_summary={
            "comparison_view": {
                "blocking_clauses": {},
                "watch_clauses": {"对方修改后的采购合同": ["付款条款", "争议解决与适用法律"]},
                "risk_flags": [],
            }
        },
    )
    project = SimpleNamespace(title="客服系统采购合同审查")
    vendor = SimpleNamespace(vendor_name="云服科技")

    structured = service._build_legal_structured_review(project, vendor, review)

    assert structured.decision_suggestion == "approve"
    assert structured.risk_level == "medium"
    assert structured.recommendation == "needs_follow_up"
