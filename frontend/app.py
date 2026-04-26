from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any

import httpx
import streamlit as st


API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
PROJECT_ROOT = Path(__file__).resolve().parents[1]

ROLE_OPTIONS = {
    "guest": "访客",
    "employee": "员工",
    "admin": "管理员",
}

INTENT_LABELS = {
    "qa": "知识问答",
    "compare": "对比分析",
    "workflow": "流程生成",
    "support": "支持问询",
    "knowledge_qa": "知识问答",
    "procurement_fit_review": "供应商匹配度审查",
    "legal_contract_review": "合同审查",
}

ACTION_LABELS = {
    "answer": "直接回答",
    "clarify": "需要澄清",
    "refuse": "拒绝回答",
}

SOURCE_TYPE_LABELS = {
    "markdown": "Markdown 文档",
    "text": "纯文本",
    "pdf": "PDF 文档",
    "docx": "Word 文档",
    "faq_csv": "FAQ 表格",
    "html": "网页内容",
}

TRACE_NODE_LABELS = {
    "Intent Router": "任务模式选择",
    "Retrieval Planner": "检索规划",
    "Tool Executor": "检索执行",
    "Answer Composer": "答案生成",
    "Citation Verifier": "引用校验",
    "意图路由": "任务模式选择",
    "检索规划": "检索规划",
    "检索执行": "检索执行",
    "答案生成": "答案生成",
    "引用校验": "引用校验",
}

BUILTIN_CN_DEMO_FILES = [
    ("data/demo_cn_employee_handbook.md", "employee,admin", "人力,入职,权限"),
    ("data/demo_cn_security_policy.md", "employee,admin", "安全,远程,权限"),
    ("data/demo_cn_customer_support_sop.md", "employee,admin", "客服,SOP,工单"),
    ("data/demo_cn_incident_playbook.md", "employee,admin", "运维,故障,应急"),
    ("data/demo_cn_finance_policy.md", "employee,admin", "财务,报销,差旅"),
    ("data/demo_cn_faq.csv", "guest,employee,admin", "FAQ,常见问题"),
]

SAMPLE_QUESTIONS = [
    "新员工在获取生产权限前需要完成哪些事项？",
    "对比入职要求和远程访问要求，有哪些差异？",
    "故障响应流程的第一步是什么？",
    "报销差旅费需要哪些材料？",
    "如果我想申请客户系统的临时访问权限，需要做什么？",
    "客服工单升级到产研团队之前需要补齐哪些信息？",
]


def api_get(path: str) -> Any:
    with httpx.Client(base_url=API_BASE_URL, timeout=20.0, trust_env=False) as client:
        response = client.get(path)
        response.raise_for_status()
        return response.json()


def api_post(
    path: str,
    json_payload: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
) -> Any:
    with httpx.Client(base_url=API_BASE_URL, timeout=40.0, trust_env=False) as client:
        response = client.post(path, json=json_payload, files=files, data=data)
        response.raise_for_status()
        return response.json()


def init_state() -> None:
    st.session_state.setdefault("session_id", None)
    st.session_state.setdefault("trace_id", "")


def translate_intent(value: str) -> str:
    return INTENT_LABELS.get(value, value)


def translate_action(value: str) -> str:
    return ACTION_LABELS.get(value, value)


def translate_source_type(value: str) -> str:
    return SOURCE_TYPE_LABELS.get(value, value)


def translate_trace_node(value: str) -> str:
    return TRACE_NODE_LABELS.get(value, value)


def load_builtin_cn_demo() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for relative_path, allowed_roles, tags in BUILTIN_CN_DEMO_FILES:
        file_path = PROJECT_ROOT / relative_path
        if not file_path.exists():
            results.append({"title": file_path.name, "status": "missing"})
            continue
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        files = {"file": (file_path.name, file_path.read_bytes(), content_type)}
        data = {"allowed_roles": allowed_roles, "tags": tags}
        response = api_post("/knowledge/upload", files=files, data=data)
        results.append(
            {
                "title": response["source"]["title"],
                "status": "duplicate" if response.get("duplicate") else "indexed",
                "chunk_count": response["chunk_count"],
            }
        )
    return results


def render_question_guide() -> None:
    with st.sidebar.expander("推荐体验问题", expanded=True):
        st.markdown("\n".join(f"- {question}" for question in SAMPLE_QUESTIONS))


def render_chat_page() -> None:
    st.subheader("智能问答")
    st.caption("向知识库提问，系统会先检索证据，再生成带引用的回答。")

    role_value = st.selectbox(
        "当前身份",
        list(ROLE_OPTIONS.keys()),
        index=1,
        format_func=lambda item: ROLE_OPTIONS[item],
    )
    query = st.text_area(
        "请输入问题",
        height=120,
        placeholder="例如：对比入职要求和远程访问要求，有哪些差异？",
    )

    if st.button("开始提问", use_container_width=True):
        if not query.strip():
            st.warning("请先输入一个问题。")
        else:
            response = api_post(
                "/chat/query",
                json_payload={
                    "query": query,
                    "session_id": st.session_state.session_id,
                    "user_role": role_value,
                    "top_k": 5,
                },
            )
            st.session_state.session_id = response["session_id"]
            st.session_state.trace_id = response["trace_id"]
            st.success(
                f"任务类型：{translate_intent(response['intent'])} | "
                f"系统动作：{translate_action(response['next_action'])} | "
                f"置信度：{response['confidence']}"
            )
            st.markdown("### 回答")
            st.write(response["answer"])
            st.markdown("### 引用证据")
            for citation in response["citations"]:
                st.markdown(
                    f"- **{citation['document_title']}** "
                    f"({citation['location']}) 相关度={citation['score']}"
                )
                st.caption(citation["snippet"])

    if st.session_state.session_id:
        session = api_get(f"/chat/sessions/{st.session_state.session_id}")
        st.markdown("### 会话记录")
        for message in session["messages"]:
            label = "用户" if message["role"] == "user" else "助手"
            st.markdown(f"**{label}：** {message['content']}")


def render_knowledge_page() -> None:
    st.subheader("知识库管理")
    st.caption("上传文档后，系统会自动解析、切块、生成检索索引。")

    if st.button("一键导入内置中文演示数据", use_container_width=True):
        with st.spinner("正在导入内置演示数据..."):
            results = load_builtin_cn_demo()
        indexed = [item for item in results if item["status"] == "indexed"]
        duplicated = [item for item in results if item["status"] == "duplicate"]
        missing = [item for item in results if item["status"] == "missing"]
        st.success(
            f"已完成导入：新增 {len(indexed)} 份，"
            f"重复 {len(duplicated)} 份，缺失 {len(missing)} 份。"
        )
        if indexed:
            st.markdown("### 本次新增")
            for item in indexed:
                st.markdown(f"- **{item['title']}** | 切片 {item['chunk_count']} 个")
        if duplicated:
            st.markdown("### 已存在")
            for item in duplicated:
                st.markdown(f"- **{item['title']}**")

    uploaded = st.file_uploader("上传文档", type=["md", "txt", "pdf", "docx", "csv"])
    remote_url = st.text_input("或者输入网页链接")
    allowed_roles = st.text_input("允许访问的角色", value="guest,employee,admin")
    tags = st.text_input("标签", value="手册,制度,流程")

    if st.button("导入知识源", use_container_width=True):
        if uploaded is None and not remote_url.strip():
            st.warning("请上传文件，或者填写一个网页链接。")
        else:
            files = None
            data = {"allowed_roles": allowed_roles, "tags": tags, "remote_url": remote_url or None}
            if uploaded is not None:
                files = {"file": (uploaded.name, uploaded.getvalue(), uploaded.type or "application/octet-stream")}
            response = api_post("/knowledge/upload", files=files, data=data)
            if response.get("duplicate"):
                st.info(f"知识源已存在：{response['source']['title']}")
            else:
                st.success(f"已完成索引：{response['source']['title']}，共生成 {response['chunk_count']} 个片段。")

    if st.button("重建全部索引", use_container_width=True):
        response = api_post("/knowledge/reindex", json_payload={"document_ids": []})
        st.info(
            f"已重建 {response['reindexed']} 份，"
            f"失败 {response['failed']} 份，"
            f"跳过 {response['skipped']} 份。"
        )

    sources = api_get("/knowledge/sources")
    st.markdown("### 当前知识源")
    for source in sources:
        st.markdown(
            f"- **{source['title']}** | {translate_source_type(source['source_type'])} | "
            f"角色={', '.join(ROLE_OPTIONS.get(role, role) for role in source['allowed_roles'])} | "
            f"标签={', '.join(source['tags'])}"
        )


def render_trace_page() -> None:
    st.subheader("执行轨迹")
    st.caption("每次问答都会记录任务模式、检索规划、答案生成和引用校验的过程。")

    trace_id = st.text_input("Trace ID", value=st.session_state.trace_id)
    if st.button("加载轨迹", use_container_width=True):
        if not trace_id.strip():
            st.warning("请先输入 Trace ID。")
        else:
            trace = api_get(f"/trace/{trace_id}")
            st.json(
                {
                    "问题": trace["query"],
                    "任务类型": translate_intent(trace["intent"]),
                    "系统动作": translate_action(trace["next_action"]),
                    "置信度": trace["confidence"],
                }
            )
            for step in trace["steps"]:
                status_label = "成功" if step["success"] else "失败"
                st.markdown(
                    f"**{translate_trace_node(step['node_name'])}** | "
                    f"{step['latency_ms']}ms | "
                    f"状态={status_label}"
                )
                st.caption(f"输入摘要：{step['input_summary']}")
                st.caption(f"输出摘要：{step['output_summary']}")


def render_eval_page() -> None:
    st.subheader("评测中心")
    st.caption("用默认评测题集验证召回命中率、引用覆盖率和安全性。")

    if st.button("运行评测", use_container_width=True):
        result = api_post("/eval/run", json_payload={"case_ids": []})
        st.success(f"评测任务 {result['id']} 已完成，共跑了 {result['result_count']} 道题。")
        st.json(result["metrics"])
        if result["failure_examples"]:
            st.markdown("### 失败样例")
            for item in result["failure_examples"]:
                st.json(item)


def main() -> None:
    st.set_page_config(page_title="KnowledgeOps Copilot", layout="wide")
    init_state()
    st.title("KnowledgeOps Copilot")
    st.caption("一个可审计的 RAG + Agent 企业知识助手演示系统。")

    render_question_guide()
    page = st.sidebar.radio(
        "页面导航",
        ["智能问答", "知识库管理", "执行轨迹", "评测中心"],
    )
    st.sidebar.markdown(f"后端地址：`{API_BASE_URL}`")

    if page == "智能问答":
        render_chat_page()
    elif page == "知识库管理":
        render_knowledge_page()
    elif page == "执行轨迹":
        render_trace_page()
    else:
        render_eval_page()


if __name__ == "__main__":
    main()
