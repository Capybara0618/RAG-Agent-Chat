import React, { useEffect, useMemo, useRef, useState } from "https://esm.sh/react@18.3.1";

import { apiGet, apiPatch, apiPost } from "./api.js";
import { PROJECT_REVIEW_PRESETS, PROJECT_STAGE_ORDER, displayLabel, stageText, toneOf } from "./config.js";

function formatCurrency(amount, currency) {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: currency || "CNY",
    maximumFractionDigits: 0,
  }).format(amount || 0);
}

function groupByStage(projects) {
  return PROJECT_STAGE_ORDER.map((stage) => ({ stage, items: projects.filter((item) => item.current_stage === stage) }));
}

function ReviewSummaryCard({ html, title, review }) {
  if (!review) {
    return html`<div className="empty-box">当前还没有结构化审查结论。</div>`;
  }

  return html`
    <div className="stack-list">
      <div className="info-box">
        <strong>${title}</strong>
        <p className="muted">${review.summary}</p>
        <div className="button-row">
          <span className="status-badge ${toneOf(review.recommendation)}">${displayLabel(review.recommendation)}</span>
          <span className="status-badge neutral">${review.conclusion}</span>
        </div>
      </div>

      ${review.check_items?.length
        ? html`
            <div className="stack-list">
              ${review.check_items.map((item) => html`
                <div className="activity-item" key=${`${item.label}-${item.status}`}>
                  <div className="activity-main">
                    <strong>${item.label}</strong>
                    <div className="subtle">${item.detail}</div>
                  </div>
                  <div className="activity-meta">
                    <span className="status-badge ${toneOf(item.status)}">${displayLabel(item.status)}</span>
                  </div>
                </div>
              `)}
            </div>
          `
        : null}

      ${review.risk_flags?.length
        ? html`
            <div className="info-box">
              <strong>结构化风险点</strong>
              <div className="stack-list">
                ${review.risk_flags.map((item) => html`<div className="inline-alert warn" key=${item}>${item}</div>`)}
              </div>
            </div>
          `
        : null}

      ${review.open_questions?.length
        ? html`
            <div className="info-box">
              <strong>待补问题</strong>
              <div className="stack-list">
                ${review.open_questions.map((item) => html`<div key=${item}>${item}</div>`)}
              </div>
            </div>
          `
        : null}

      ${review.evidence?.length
        ? html`
            <div className="info-box">
              <strong>证据引用</strong>
              <div className="stack-list">
                ${review.evidence.map((item) => html`
                  <div className="activity-item" key=${`${item.document_title}-${item.location}`}>
                    <div className="activity-main">
                      <strong>${item.document_title}</strong>
                      <div className="subtle">${item.location}</div>
                      <div className="subtle">${item.snippet}</div>
                    </div>
                  </div>
                `)}
              </div>
            </div>
          `
        : null}
    </div>
  `;
}

export function ProjectsPage({
  html,
  projects,
  currentUser,
  refreshAll,
  onTraceCreated,
  onNavigate,
  setDraftQuestion,
  assistantTask,
  setAssistantTask,
  setAssistantResult,
}) {
  const [selectedProjectId, setSelectedProjectId] = useState(projects[0]?.id || "");
  const [projectDetail, setProjectDetail] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [error, setError] = useState("");
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [reviewQuery, setReviewQuery] = useState("");
  const [activeVendorId, setActiveVendorId] = useState("");
  const [businessDialog, setBusinessDialog] = useState("");
  const [businessFocus, setBusinessFocus] = useState("review");
  const [businessFormErrors, setBusinessFormErrors] = useState({});
  const [vendorFormErrors, setVendorFormErrors] = useState({});
  const [businessCreatingNew, setBusinessCreatingNew] = useState(false);
  const [managerDialogOpen, setManagerDialogOpen] = useState(false);
  const [procurementDialogOpen, setProcurementDialogOpen] = useState(false);
  const [vendorMaterialFiles, setVendorMaterialFiles] = useState([]);
  const [vendorMaterialExtraction, setVendorMaterialExtraction] = useState(null);
  const [extractingVendorMaterials, setExtractingVendorMaterials] = useState(false);
  const [createForm, setCreateForm] = useState({
    title: "",
    requester_name: "",
    department: "",
    vendor_name: "",
    category: "software",
    budget_amount: 0,
    currency: "CNY",
    summary: "",
    business_value: "",
    target_go_live_date: "",
    data_scope: "none",
  });
  const [draftForm, setDraftForm] = useState(createForm);
  const [vendorForm, setVendorForm] = useState({
    vendor_name: "",
    source_platform: "",
    source_url: "",
    profile_summary: "",
    procurement_notes: "",
  });
  const selectedProjectIdRef = useRef(selectedProjectId);

  useEffect(() => {
    selectedProjectIdRef.current = selectedProjectId;
  }, [selectedProjectId]);

  useEffect(() => {
    if (selectedProjectId || !projects[0]?.id) return;
    if (currentUser.role === "business" && businessCreatingNew) return;
    setSelectedProjectId(projects[0].id);
  }, [projects, selectedProjectId, currentUser.role, businessCreatingNew]);

  useEffect(() => {
    if (currentUser.role !== "procurement") return;
    if (assistantTask?.kind !== "procurement_vendor_review") return;
    if (!assistantTask.projectId || assistantTask.projectId === selectedProjectId) return;
    setSelectedProjectId(assistantTask.projectId);
  }, [assistantTask?.kind, assistantTask?.projectId, currentUser.role, selectedProjectId]);

  useEffect(() => {
    if (selectedProjectId) loadProject(selectedProjectId);
  }, [selectedProjectId]);

  useEffect(() => {
    if (!projectDetail) return;
    setReviewQuery(PROJECT_REVIEW_PRESETS[projectDetail.current_stage] || "");
    setVendorFormErrors({});
    if (projectDetail.draft_editable) {
      setDraftForm({
        title: projectDetail.title || "",
        requester_name: projectDetail.requester_name || "",
        department: projectDetail.department || "",
        vendor_name: projectDetail.vendor_name || "",
        category: projectDetail.category || "",
        budget_amount: projectDetail.budget_amount || 0,
        currency: projectDetail.currency || "CNY",
        summary: projectDetail.summary || "",
        business_value: projectDetail.business_value || "",
        target_go_live_date: projectDetail.target_go_live_date || "",
        data_scope: projectDetail.data_scope || "none",
      });
    }
    if (projectDetail.vendors?.length) {
      setActiveVendorId((current) => current && projectDetail.vendors.some((item) => item.id === current) ? current : projectDetail.vendors[0].id);
    } else {
      setActiveVendorId("");
    }
    if (currentUser.role === "procurement") {
      setVendorMaterialFiles([]);
      setVendorMaterialExtraction(null);
    }
  }, [projectDetail?.id, projectDetail?.current_stage, projectDetail?.updated_at]);

  useEffect(() => {
    if (currentUser.role !== "procurement") return;
    if (assistantTask?.kind !== "procurement_vendor_review") return;
    if (!projectDetail || assistantTask.projectId !== projectDetail.id) return;
    setVendorForm({
      vendor_name: assistantTask.vendorDraft?.vendor_name || "",
      source_platform: assistantTask.vendorDraft?.source_platform || "",
      source_url: assistantTask.vendorDraft?.source_url || "",
      profile_summary: assistantTask.vendorDraft?.profile_summary || "",
      procurement_notes: assistantTask.vendorDraft?.procurement_notes || "",
    });
    if (assistantTask.linkedVendorId) setActiveVendorId(assistantTask.linkedVendorId);
  }, [assistantTask, currentUser.role, projectDetail?.id]);

  const currentTasks = useMemo(
    () => projectDetail?.tasks?.filter((item) => item.stage === projectDetail.current_stage) || [],
    [projectDetail],
  );
  const currentArtifacts = useMemo(() => {
    if (!projectDetail) return [];
    return (projectDetail.artifacts || []).filter((item) => {
      if (item.stage !== projectDetail.current_stage) return false;
      if (projectDetail.current_stage !== "legal_review") return true;
      return !item.linked_vendor_id || item.linked_vendor_id === projectDetail.selected_vendor_id;
    });
  }, [projectDetail]);
  const vendors = useMemo(() => projectDetail?.vendors || [], [projectDetail]);
  const activeVendor = useMemo(() => vendors.find((item) => item.id === activeVendorId) || vendors[0] || null, [vendors, activeVendorId]);

  async function loadProject(projectId) {
    try {
      setLoadingDetail(true);
      setError("");
      const [detail, timelineItems] = await Promise.all([apiGet(`/projects/${projectId}`), apiGet(`/projects/${projectId}/timeline`)]);
      if (selectedProjectIdRef.current !== projectId) return;
      setProjectDetail(detail);
      setTimeline(timelineItems);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingDetail(false);
    }
  }

  async function createProject(event, sourceForm = createForm) {
    event?.preventDefault?.();
    try {
      setBusinessCreatingNew(false);
      const created = await apiPost("/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...sourceForm, budget_amount: Number(sourceForm.budget_amount || 0) }),
      });
      setCreateForm({
        title: "",
        requester_name: "",
        department: "",
        vendor_name: "",
        category: "software",
        budget_amount: 0,
        currency: "CNY",
        summary: "",
        business_value: "",
        target_go_live_date: "",
        data_scope: "none",
      });
      await refreshAll();
      setSelectedProjectId(created.id);
      return created;
    } catch (err) {
      setError(err.message);
      return null;
    }
  }

  async function createBusinessProject(event) {
    const created = await createProject(event);
    if (created) {
      setBusinessFocus("review");
      setBusinessDialog("");
    }
  }

  async function createDemoProject() {
    try {
      const created = await apiPost("/projects/demo", { method: "POST", headers: { "Content-Type": "application/json" } });
      await refreshAll();
      setSelectedProjectId(created.id);
    } catch (err) {
      setError(err.message);
    }
  }

  async function saveDraftProject(event) {
    event.preventDefault();
    if (!projectDetail) return;
    try {
      await apiPatch(`/projects/${projectDetail.id}`, {
        ...draftForm,
        budget_amount: Number(draftForm.budget_amount || 0),
      });
      await refreshAll({ silent: true });
      await loadProject(projectDetail.id);
    } catch (err) {
      setError(err.message);
    }
  }

  async function markTaskDone(taskId) {
    try {
      await apiPatch(`/projects/${projectDetail.id}/tasks/${taskId}`, { status: "done" });
      await refreshAll({ silent: true });
      await loadProject(projectDetail.id);
    } catch (err) {
      setError(err.message);
    }
  }

  async function markArtifactProvided(artifactId) {
    try {
      await apiPatch(`/projects/${projectDetail.id}/artifacts/${artifactId}`, { status: "provided" });
      await refreshAll({ silent: true });
      await loadProject(projectDetail.id);
    } catch (err) {
      setError(err.message);
    }
  }

  async function runAction(path, body = {}) {
    try {
      await apiPost(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      await refreshAll({ silent: true });
      await loadProject(projectDetail.id);
    } catch (err) {
      setError(err.message);
    }
  }

  async function createVendor(event) {
    event.preventDefault();
    const errors = vendorFormErrorsFor(vendorForm);
    setVendorFormErrors(errors);
    if (Object.values(errors).some(Boolean)) {
      window.alert("供应商信息格式错误，请根据红色标记重新填写。");
      return;
    }
    try {
      const created = await apiPost(`/projects/${projectDetail.id}/vendors`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(vendorForm),
      });
      setVendorForm({ vendor_name: "", source_platform: "", source_url: "", profile_summary: "", procurement_notes: "" });
      setVendorFormErrors({});
      setVendorMaterialFiles([]);
      setVendorMaterialExtraction(null);
      if (setAssistantTask) setAssistantTask(null);
      if (setAssistantResult) setAssistantResult(null);
      setActiveVendorId(created.id);
      await refreshAll({ silent: true });
      await loadProject(projectDetail.id);
    } catch (err) {
      setError(err.message);
    }
  }

  function openProcurementAssistant() {
    const draftVendor = activeVendor || {};
    const mergedVendor = {
      vendor_name: vendorForm.vendor_name || draftVendor.vendor_name || "",
      source_platform: vendorForm.source_platform || draftVendor.source_platform || "",
      source_url: vendorForm.source_url || draftVendor.source_url || "",
      profile_summary: vendorForm.profile_summary || draftVendor.profile_summary || "",
      procurement_notes: vendorForm.procurement_notes || draftVendor.procurement_notes || "",
    };
    const errors = vendorFormErrorsFor(mergedVendor);
    setVendorFormErrors(errors);
    if (Object.values(errors).some(Boolean)) {
      window.alert("请先补齐供应商基础信息，再启动 Agent 审查。");
      return;
    }
    if (setAssistantTask) {
      setAssistantTask({
        kind: "procurement_vendor_review",
        projectId: projectDetail?.id || "",
        linkedVendorId: draftVendor.id || "",
        projectTitle: projectDetail?.title || "",
        vendorDraft: mergedVendor,
      });
    }
    if (setAssistantResult) setAssistantResult(null);
    if (setDraftQuestion) setDraftQuestion("");
    if (onNavigate) onNavigate("assistant");
  }

  async function extractVendorMaterials() {
    if (!projectDetail?.id) return;
    if (!vendorMaterialFiles.length) {
      window.alert("请先上传至少一份供应商材料。");
      return;
    }
    try {
      setExtractingVendorMaterials(true);
      setError("");
      const formData = new FormData();
      vendorMaterialFiles.forEach((file) => formData.append("files", file));
      const payload = await apiPost(`/projects/${projectDetail.id}/procurement-agent-extract`, {
        method: "POST",
        body: formData,
      });
      setVendorMaterialExtraction(payload);
      setVendorForm({
        vendor_name: payload.vendor_draft.vendor_name || "",
        source_platform: payload.vendor_draft.source_platform || "",
        source_url: payload.vendor_draft.source_url || "",
        profile_summary: payload.vendor_draft.profile_summary || "",
        procurement_notes: payload.vendor_draft.procurement_notes || "",
      });
      setVendorFormErrors({});
    } catch (err) {
      setError(err.message);
    } finally {
      setExtractingVendorMaterials(false);
    }
  }

  async function reviewVendor() {
    if (!activeVendor) return;
    try {
      const result = await apiPost(`/projects/${projectDetail.id}/vendors/${activeVendor.id}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: reviewQuery, user_role: currentUser.role, top_k: 6 }),
      });
      setProjectDetail(result.project);
      onTraceCreated(result.review.trace_id);
      setTimeline(await apiGet(`/projects/${projectDetail.id}/timeline`));
      await refreshAll({ silent: true });
    } catch (err) {
      setError(err.message);
    }
  }

  async function reviewLegal() {
    try {
      const result = await apiPost(`/projects/${projectDetail.id}/legal/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: reviewQuery, user_role: currentUser.role, top_k: 6 }),
      });
      setProjectDetail(result.project);
      onTraceCreated(result.review.trace_id);
      setTimeline(await apiGet(`/projects/${projectDetail.id}/timeline`));
      await refreshAll({ silent: true });
    } catch (err) {
      setError(err.message);
    }
  }

  function renderStageActions() {
    if (!projectDetail) return null;
    const actions = new Set(projectDetail.allowed_actions || []);
    if (projectDetail.status === "cancelled") {
      return html`<span className="status-badge danger">项目已取消</span>`;
    }
    if (projectDetail.current_stage === "business_draft") {
      return html`
        ${actions.has("submit") ? html`<button className="btn secondary" onClick=${() => runAction(`/projects/${projectDetail.id}/submit`, { reason: "" })}>提交到上级审批</button>` : null}
        ${actions.has("cancel") ? html`<button className="btn ghost" onClick=${() => runAction(`/projects/${projectDetail.id}/cancel`, { reason: "业务部门撤销采购申请。" })}>撤销申请</button>` : null}
      `;
    }
    if (projectDetail.current_stage === "manager_review") {
      return html`
        ${actions.has("manager_approve") ? html`<button className="btn primary" onClick=${() => runAction(`/projects/${projectDetail.id}/manager-decision`, { decision: "approve", reason: "" })}>审批通过</button>` : null}
        ${actions.has("manager_return") ? html`<button className="btn ghost" onClick=${() => runAction(`/projects/${projectDetail.id}/manager-decision`, { decision: "return", reason: "资料不完整，退回补充。" })}>退回草稿</button>` : null}
        ${actions.has("withdraw") ? html`<button className="btn ghost" onClick=${() => runAction(`/projects/${projectDetail.id}/withdraw`, { reason: "申请人主动撤回修改。" })}>业务撤回</button>` : null}
        ${actions.has("cancel") ? html`<button className="btn ghost" onClick=${() => runAction(`/projects/${projectDetail.id}/cancel`, { reason: "上级审批决定取消项目。" })}>取消项目</button>` : null}
      `;
    }
    if (projectDetail.current_stage === "procurement_sourcing") {
      return activeVendor
        ? html`
            ${actions.has("review_vendor") ? html`<button className="btn primary" onClick=${reviewVendor}>AI 准入评审</button>` : null}
            ${actions.has("select_vendor") ? html`<button className="btn secondary" onClick=${() => runAction(`/projects/${projectDetail.id}/vendors/${activeVendor.id}/select`, { reason: "采购选择该供应商进入法务审查。" })}>选中进入法务</button>` : null}
            ${actions.has("cancel") ? html`<button className="btn ghost" onClick=${() => runAction(`/projects/${projectDetail.id}/cancel`, { reason: "采购阶段取消项目。" })}>取消项目</button>` : null}
          `
        : html`<span className="muted">先添加候选供应商。</span>`;
    }
    if (projectDetail.current_stage === "legal_review") {
      return html`
        ${actions.has("review_legal") ? html`<button className="btn primary" onClick=${reviewLegal}>AI 合同审查</button>` : null}
        ${actions.has("legal_approve") ? html`<button className="btn secondary" onClick=${() => runAction(`/projects/${projectDetail.id}/legal-decision`, { decision: "approve", reason: "法务审查通过。" })}>法务通过</button>` : null}
        ${actions.has("return_to_procurement") ? html`<button className="btn ghost" onClick=${() => runAction(`/projects/${projectDetail.id}/return-to-procurement`, { reason: "合同条款不合规，退回采购更换供应商。" })}>退回采购</button>` : null}
        ${actions.has("cancel") ? html`<button className="btn ghost" onClick=${() => runAction(`/projects/${projectDetail.id}/cancel`, { reason: "法务阶段取消项目。" })}>取消项目</button>` : null}
      `;
    }
    if (projectDetail.current_stage === "final_approval") {
      return html`
        ${actions.has("final_approve") ? html`<button className="btn primary" onClick=${() => runAction(`/projects/${projectDetail.id}/final-approve`, { reason: "终审通过。" })}>终审通过</button>` : null}
        ${actions.has("final_return_legal") ? html`<button className="btn ghost" onClick=${() => runAction(`/projects/${projectDetail.id}/final-return`, { target_stage: "legal_review", reason: "终审要求法务补充核验。" })}>退回法务</button>` : null}
        ${actions.has("final_return_procurement") ? html`<button className="btn ghost" onClick=${() => runAction(`/projects/${projectDetail.id}/final-return`, { target_stage: "procurement_sourcing", reason: "终审要求采购重新评估供应商。" })}>退回采购</button>` : null}
        ${actions.has("cancel") ? html`<button className="btn ghost" onClick=${() => runAction(`/projects/${projectDetail.id}/cancel`, { reason: "终审取消项目。" })}>取消项目</button>` : null}
      `;
    }
    if (projectDetail.current_stage === "signing") {
      return html`
        ${actions.has("sign") ? html`<button className="btn primary" onClick=${() => runAction(`/projects/${projectDetail.id}/sign`, { reason: "签署完成并归档。" })}>完成签署归档</button>` : null}
        ${actions.has("cancel") ? html`<button className="btn ghost" onClick=${() => runAction(`/projects/${projectDetail.id}/cancel`, { reason: "签署前取消项目。" })}>取消项目</button>` : null}
      `;
    }
    return html`<span className="status-badge success">流程已完成</span>`;
  }

  function renderBusinessActions() {
    if (!projectDetail) return null;
    const actions = new Set(projectDetail.allowed_actions || []);
    return html`
      ${actions.has("submit") ? html`<button className="btn primary" type="button" onClick=${() => runAction(`/projects/${projectDetail.id}/submit`, { reason: "" })}>提交到上级审批</button>` : null}
      ${actions.has("withdraw") ? html`<button className="btn secondary" type="button" onClick=${() => runAction(`/projects/${projectDetail.id}/withdraw`, { reason: "申请人主动撤回修改。" })}>撤回修改</button>` : null}
      ${actions.has("cancel") ? html`<button className="btn ghost" type="button" onClick=${() => runAction(`/projects/${projectDetail.id}/cancel`, { reason: "业务部门撤销采购申请。" })}>撤销申请</button>` : null}
    `;
  }

  function renderBusinessWorkspace() {
    const currentStageIndex = projectDetail ? Math.max(PROJECT_STAGE_ORDER.indexOf(projectDetail.current_stage), 0) : 0;

    return html`
      <div>
        <div className="topbar">
          <div>
            <h2>业务申请工作台</h2>
            <p>业务部门只负责填写采购申请表、根据系统提醒补齐信息并人工确认提交，不再进行大模型审查。</p>
          </div>
        </div>
        ${error ? html`<div className="error" style=${{ marginBottom: "18px" }}>${error}</div>` : null}

        <section className="section-block">
          <div className="panel business-workbench">
            <div className="section-title-row">
              <div>
                <h3>${projectDetail?.title || "请选择或新建业务申请"}</h3>
                <div className="subtle">
                  ${projectDetail
                    ? `当前状态：${stageText(projectDetail.current_stage)} / ${formatCurrency(projectDetail.budget_amount, projectDetail.currency)}`
                    : "先通过业务申请弹窗暂存采购申请表，再进入业务审核。"}
                </div>
              </div>
              ${projectDetail
                ? html`
                    <div className="button-row">
                      <span className="status-badge ${toneOf(projectDetail.status)}">${displayLabel(projectDetail.status)}</span>
                      <span className="status-badge neutral">${stageText(projectDetail.current_stage)}</span>
                    </div>
                  `
                : null}
            </div>

            <div className="business-progress-rail">
              ${PROJECT_STAGE_ORDER.map((stage, index) => {
                const nodeTone = index < currentStageIndex ? "done" : index === currentStageIndex ? "active" : "pending";
                return html`
                  <div className="business-progress-step" key=${stage}>
                    <div className=${`business-progress-node ${nodeTone}`}>
                      <span className="business-progress-dot">${index + 1}</span>
                      <span className="business-progress-name">${stageText(stage)}</span>
                    </div>
                    ${index < PROJECT_STAGE_ORDER.length - 1 ? html`<div className=${`business-progress-link ${index < currentStageIndex ? "active" : ""}`}></div>` : null}
                  </div>
                `;
              })}
            </div>

            <div className="business-entry-row">
              <button className=${businessFocus === "apply" ? "btn primary" : "btn secondary"} type="button" onClick=${() => {
                setBusinessFocus("apply");
                setBusinessDialog("apply");
              }}>业务申请</button>
              <button className=${businessFocus === "history" ? "btn primary" : "btn secondary"} type="button" onClick=${() => {
                setBusinessFocus("history");
                setBusinessDialog("history");
              }}>历史项目列表</button>
              <button className=${businessFocus === "review" ? "btn primary" : "btn secondary"} type="button" onClick=${() => {
                setBusinessFocus("review");
                if (!selectedProjectId && projects[0]?.id) {
                  setSelectedProjectId(projects[0].id);
                }
              }}>业务审核</button>
            </div>
          </div>
        </section>

        ${loadingDetail && selectedProjectId
          ? html`<div className="center-panel" style=${{ minHeight: "220px" }}><div className="loading-ring"></div></div>`
          : html`
              <div className="projects-layout wide business-review-grid">
                <section className="panel">
                  <div className="section-title-row">
                    <h3>业务审核</h3>
                    <div className="button-row">${renderBusinessActions()}</div>
                  </div>

                  ${projectDetail
                    ? html`
                        <div className="info-box business-manual-note">
                          <strong>人工审核说明</strong>
                          <div className="subtle">系统只负责检查采购申请表是否完整，并自动勾选要点。确认无误后由业务人工提交给上级审批。</div>
                        </div>

                        ${projectDetail.draft_editable
                          ? html`
                              <form className="stack-list" onSubmit=${saveDraftProject}>
                                <input className="field" placeholder="项目名称" value=${draftForm.title} onInput=${(e) => setDraftForm({ ...draftForm, title: e.target.value })} />
                                <div className="split-fields">
                                  <input className="field" placeholder="发起人" value=${draftForm.requester_name} onInput=${(e) => setDraftForm({ ...draftForm, requester_name: e.target.value })} />
                                  <input className="field" placeholder="所属部门" value=${draftForm.department} onInput=${(e) => setDraftForm({ ...draftForm, department: e.target.value })} />
                                </div>
                                <div className="split-fields">
                                  <input className="field" placeholder="意向供应商" value=${draftForm.vendor_name} onInput=${(e) => setDraftForm({ ...draftForm, vendor_name: e.target.value })} />
                                  <input className="field" placeholder="采购类别" value=${draftForm.category} onInput=${(e) => setDraftForm({ ...draftForm, category: e.target.value })} />
                                </div>
                                <div className="split-fields">
                                  <input className="field" type="number" placeholder="预算金额" value=${draftForm.budget_amount} onInput=${(e) => setDraftForm({ ...draftForm, budget_amount: e.target.value })} />
                                  <input className="field" placeholder="币种" value=${draftForm.currency} onInput=${(e) => setDraftForm({ ...draftForm, currency: e.target.value })} />
                                </div>
                                <div className="split-fields">
                                  <input className="field" type="date" value=${draftForm.target_go_live_date} onInput=${(e) => setDraftForm({ ...draftForm, target_go_live_date: e.target.value })} />
                                  <input className="field" placeholder="数据范围" value=${draftForm.data_scope} onInput=${(e) => setDraftForm({ ...draftForm, data_scope: e.target.value })} />
                                </div>
                                <textarea className="field textarea-medium" placeholder="项目背景与采购目的" value=${draftForm.summary} onInput=${(e) => setDraftForm({ ...draftForm, summary: e.target.value })}></textarea>
                                <textarea className="field textarea-medium" placeholder="预期收益 / 业务价值" value=${draftForm.business_value} onInput=${(e) => setDraftForm({ ...draftForm, business_value: e.target.value })}></textarea>
                                <div className="button-row"><button className="btn secondary" type="submit">暂存采购申请表</button></div>
                              </form>
                            `
                          : html`
                              <div className="business-readonly-grid">
                                <div className="mini-metric"><span className="mini-label">项目名称</span><strong>${projectDetail.title || "-"}</strong></div>
                                <div className="mini-metric"><span className="mini-label">发起人</span><strong>${projectDetail.requester_name || "-"}</strong></div>
                                <div className="mini-metric"><span className="mini-label">所属部门</span><strong>${projectDetail.department || "-"}</strong></div>
                                <div className="mini-metric"><span className="mini-label">意向供应商</span><strong>${projectDetail.vendor_name || "-"}</strong></div>
                                <div className="mini-metric"><span className="mini-label">预算</span><strong>${formatCurrency(projectDetail.budget_amount, projectDetail.currency)}</strong></div>
                                <div className="mini-metric"><span className="mini-label">上线时间</span><strong>${projectDetail.target_go_live_date || "-"}</strong></div>
                              </div>
                              <div className="info-box">
                                <strong>采购目的</strong>
                                <div className="subtle">${projectDetail.summary || "未填写"}</div>
                              </div>
                              <div className="info-box">
                                <strong>业务价值</strong>
                                <div className="subtle">${projectDetail.business_value || "未填写"}</div>
                              </div>
                            `}
                      `
                    : html`<div className="empty-box">当前还没有业务申请。点击上方“业务申请”先暂存一张采购申请表。</div>`}
                </section>

                <section className="panel">
                  <div className="section-title-row"><h3>审核提醒</h3></div>
                  ${projectDetail
                    ? html`
                        <div className=${projectDetail.application_form_ready ? "project-blocker-banner success" : "project-blocker-banner"}>
                          <strong>${projectDetail.application_form_ready ? "采购申请表已满足提交条件" : "采购申请表还有待补齐项"}</strong>
                          <div className="subtle">${projectDetail.application_form_summary}</div>
                        </div>

                        <div className="section-title-row" style=${{ marginTop: "20px" }}><h4>需求要点勾选</h4></div>
                        ${projectDetail.application_checks?.length
                          ? html`
                              <div className="stack-list">
                                ${projectDetail.application_checks.map((item) => html`
                                  <div className="activity-item" key=${item.key}>
                                    <div className="activity-main">
                                      <strong>${item.label}</strong>
                                      <div className="subtle">${item.detail}</div>
                                    </div>
                                    <div className="activity-meta">
                                      <span className="status-badge ${toneOf(item.checked ? "pass" : "pending")}">${displayLabel(item.checked ? "pass" : "pending")}</span>
                                    </div>
                                  </div>
                                `)}
                              </div>
                            `
                          : html`<div className="empty-box">当前还没有校验项。</div>`}

                        <div className="section-title-row" style=${{ marginTop: "20px" }}><h4>阻塞提醒</h4></div>
                        ${projectDetail.blocker_summary.length
                          ? html`<div className="stack-list">${projectDetail.blocker_summary.map((item) => html`<div className="inline-alert warn" key=${item}>${item}</div>`)}</div>`
                          : html`<div className="empty-box compact">当前没有阻塞项，可以继续由业务人工确认是否提交。</div>`}
                      `
                    : html`<div className="empty-box">选择一个项目后，这里会显示业务审核提醒。</div>`}
                </section>
              </div>
            `}

        ${businessDialog === "apply"
          ? html`
              <div className="business-modal-mask" onClick=${() => setBusinessDialog("")}>
                <div className="business-modal-panel" onClick=${(event) => event.stopPropagation()}>
                  <div className="section-title-row">
                    <h3>业务申请</h3>
                    <button className="btn ghost small" type="button" onClick=${() => { setBusinessDialog(""); setBusinessFocus("review"); }}>关闭</button>
                  </div>
                  <form className="stack-list" onSubmit=${createBusinessProject}>
                    <input className="field" placeholder="项目名称" value=${createForm.title} onInput=${(e) => setCreateForm({ ...createForm, title: e.target.value })} />
                    <div className="split-fields">
                      <input className="field" placeholder="发起人" value=${createForm.requester_name} onInput=${(e) => setCreateForm({ ...createForm, requester_name: e.target.value })} />
                      <input className="field" placeholder="所属部门" value=${createForm.department} onInput=${(e) => setCreateForm({ ...createForm, department: e.target.value })} />
                    </div>
                    <div className="split-fields">
                      <input className="field" placeholder="意向供应商" value=${createForm.vendor_name} onInput=${(e) => setCreateForm({ ...createForm, vendor_name: e.target.value })} />
                      <input className="field" placeholder="采购类别" value=${createForm.category} onInput=${(e) => setCreateForm({ ...createForm, category: e.target.value })} />
                    </div>
                    <div className="split-fields">
                      <input className="field" type="number" placeholder="预算金额" value=${createForm.budget_amount} onInput=${(e) => setCreateForm({ ...createForm, budget_amount: e.target.value })} />
                      <input className="field" placeholder="币种" value=${createForm.currency} onInput=${(e) => setCreateForm({ ...createForm, currency: e.target.value })} />
                    </div>
                    <div className="split-fields">
                      <input className="field" type="date" value=${createForm.target_go_live_date} onInput=${(e) => setCreateForm({ ...createForm, target_go_live_date: e.target.value })} />
                      <input className="field" placeholder="数据范围" value=${createForm.data_scope} onInput=${(e) => setCreateForm({ ...createForm, data_scope: e.target.value })} />
                    </div>
                    <textarea className="field textarea-medium" placeholder="项目背景与采购目的" value=${createForm.summary} onInput=${(e) => setCreateForm({ ...createForm, summary: e.target.value })}></textarea>
                    <textarea className="field textarea-medium" placeholder="预期收益 / 业务价值" value=${createForm.business_value} onInput=${(e) => setCreateForm({ ...createForm, business_value: e.target.value })}></textarea>
                    <div className="button-row"><button className="btn primary" type="submit">暂存采购申请表</button></div>
                  </form>
                </div>
              </div>
            `
          : null}

        ${businessDialog === "history"
          ? html`
              <div className="business-modal-mask" onClick=${() => setBusinessDialog("")}>
                <div className="business-modal-panel history-panel" onClick=${(event) => event.stopPropagation()}>
                  <div className="section-title-row">
                    <h3>历史项目列表</h3>
                    <button className="btn ghost small" type="button" onClick=${() => { setBusinessDialog(""); setBusinessFocus("review"); }}>关闭</button>
                  </div>
                  ${projects.length
                    ? html`
                        <div className="stack-list">
                          ${projects.map((item) => html`
                            <button key=${item.id} className=${selectedProjectId === item.id ? "project-list-item active" : "project-list-item"} onClick=${() => { setSelectedProjectId(item.id); setBusinessDialog(""); setBusinessFocus("review"); }}>
                              <div className="activity-main">
                                <strong>${item.title}</strong>
                                <div className="subtle">${stageText(item.current_stage)} / ${formatCurrency(item.budget_amount, item.currency)}</div>
                              </div>
                              <div className="activity-meta"><span className="status-badge ${toneOf(item.status)}">${displayLabel(item.status)}</span></div>
                            </button>
                          `)}
                        </div>
                      `
                    : html`<div className="empty-box">暂时还没有历史项目。</div>`}
                </div>
              </div>
            `
          : null}
      </div>
    `;
  }

  function businessFormForView() {
    if (!projectDetail) return createForm;
    return {
      title: projectDetail.title || "",
      requester_name: projectDetail.requester_name || "",
      department: projectDetail.department || "",
      vendor_name: projectDetail.vendor_name || "",
      category: projectDetail.category || "",
      budget_amount: projectDetail.budget_amount || 0,
      currency: projectDetail.currency || "CNY",
      summary: projectDetail.summary || "",
      business_value: projectDetail.business_value || "",
      target_go_live_date: projectDetail.target_go_live_date || "",
      data_scope: projectDetail.data_scope || "none",
    };
  }

  function businessFormErrorsFor(form) {
    const errors = {};
    if (!form.title?.trim()) errors.title = "项目名称不能为空。";
    if (!form.requester_name?.trim()) errors.requester_name = "请填写发起人。";
    if (!form.department?.trim()) errors.department = "请填写所属部门。";
    if (!form.category?.trim()) errors.category = "请填写采购类别。";
    if (!Number(form.budget_amount || 0) || Number(form.budget_amount || 0) <= 0) errors.budget_amount = "预算金额必须大于 0。";
    if (!form.currency?.trim()) errors.currency = "请填写币种。";
    if (!form.target_go_live_date?.trim()) errors.target_go_live_date = "请选择期望上线时间。";
    if (!form.data_scope?.trim()) errors.data_scope = "请选择数据范围。";
    if ((form.summary || "").trim().length < 10) errors.summary = "采购目的至少填写 10 个字。";
    if ((form.business_value || "").trim().length < 6) errors.business_value = "业务价值至少填写 6 个字。";
    return errors;
  }

  function vendorFormErrorsFor(form) {
    const errors = {};
    if (!form.vendor_name?.trim()) errors.vendor_name = "请填写供应商名称。";
    if (!form.source_platform?.trim()) errors.source_platform = "请填写来源平台。";
    if (form.source_url?.trim()) {
      try {
        new URL(form.source_url.trim());
      } catch (_) {
        errors.source_url = "来源链接格式不正确。";
      }
    }
    if ((form.profile_summary || "").trim().length < 10) errors.profile_summary = "供应商简介至少填写 10 个字。";
    if ((form.procurement_notes || "").trim().length < 10) errors.procurement_notes = "采购说明至少填写 10 个字。";
    return errors;
  }

  function updateBusinessForm(field, value) {
    if (projectDetail && !projectDetail.draft_editable) return;
    const setter = projectDetail?.draft_editable ? setDraftForm : setCreateForm;
    setter((current) => ({ ...current, [field]: value }));
    setBusinessFormErrors((current) => ({ ...current, [field]: "" }));
  }

  function updateVendorField(field, value) {
    setVendorForm((current) => ({ ...current, [field]: value }));
    setVendorFormErrors((current) => ({ ...current, [field]: "" }));
  }

  function resetBusinessApplicationForm() {
    const emptyForm = {
      title: "",
      requester_name: "",
      department: "",
      vendor_name: "",
      category: "software",
      budget_amount: 0,
      currency: "CNY",
      summary: "",
      business_value: "",
      target_go_live_date: "",
      data_scope: "none",
    };
    setSelectedProjectId("");
    setProjectDetail(null);
    setTimeline([]);
    setError("");
    setLoadingDetail(false);
    setReviewQuery("");
    setBusinessCreatingNew(true);
    setBusinessFormErrors({});
    setCreateForm(emptyForm);
    setDraftForm(emptyForm);
  }

  async function saveBusinessApplication(event) {
    event.preventDefault();
    if (projectDetail && !projectDetail.draft_editable) return;
    if (projectDetail?.draft_editable) {
      setBusinessCreatingNew(false);
      await saveDraftProject(event);
      return;
    }
    const created = await createProject(event, createForm);
    if (created) setSelectedProjectId(created.id);
  }

  async function submitBusinessApplication() {
    const form = projectDetail?.draft_editable ? draftForm : createForm;
    const errors = businessFormErrorsFor(form);
    setBusinessFormErrors(errors);
    if (Object.values(errors).some(Boolean)) {
      window.alert("报表格式错误，请根据红色标记重新填写。");
      return;
    }

    try {
      let targetProjectId = projectDetail?.id || "";
      if (projectDetail?.draft_editable) {
        setBusinessCreatingNew(false);
        await apiPatch(`/projects/${projectDetail.id}`, { ...form, budget_amount: Number(form.budget_amount || 0) });
      } else {
        setBusinessCreatingNew(false);
        const created = await apiPost("/projects", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...form, budget_amount: Number(form.budget_amount || 0) }),
        });
        targetProjectId = created.id;
      }
      await apiPost(`/projects/${targetProjectId}/submit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: "" }),
      });
      await refreshAll({ silent: true });
      setSelectedProjectId(targetProjectId);
      await loadProject(targetProjectId);
    } catch (err) {
      setError(err.message);
      window.alert(`提交失败：${err.message}`);
    }
  }

  function renderBusinessField({ form, errors, field, label, placeholder, type = "text", textarea = false, selectOptions = null, full = false }) {
    const editable = !projectDetail || projectDetail.draft_editable;
    const fieldError = businessFormErrors[field] || errors[field];
    const className = fieldError ? "field error" : "field";
    return html`
      <label className=${full ? "business-form-field full" : "business-form-field"}>
        <span className="business-form-label">${label}</span>
        ${selectOptions
          ? html`
              <select className=${className} value=${form[field] || ""} disabled=${!editable} onInput=${(event) => updateBusinessForm(field, event.target.value)}>
                ${selectOptions.map((item) => html`<option key=${item.value} value=${item.value}>${item.label}</option>`)}
              </select>
            `
          : textarea
            ? html`<textarea className=${`${className} textarea-medium`} placeholder=${placeholder} value=${form[field] || ""} disabled=${!editable} onInput=${(event) => updateBusinessForm(field, event.target.value)}></textarea>`
            : html`<input className=${className} type=${type} placeholder=${placeholder} value=${form[field] || ""} disabled=${!editable} onInput=${(event) => updateBusinessForm(field, event.target.value)} />`}
        ${fieldError ? html`<span className="field-hint error">${fieldError}</span>` : null}
      </label>
    `;
  }

  function renderBusinessForm() {
    const editable = !projectDetail || projectDetail.draft_editable;
    const form = projectDetail?.draft_editable ? draftForm : businessFormForView();
    const errors = editable ? businessFormErrorsFor(form) : {};
    const actions = new Set(projectDetail?.allowed_actions || []);

    return html`
      <form className="business-form" onSubmit=${saveBusinessApplication}>
        <div className="business-form-section">
          <div className="business-form-heading">
            <span>基本信息</span>
            <small>${editable ? "可编辑并暂存" : `当前阶段：${stageText(projectDetail?.current_stage)}`}</small>
          </div>
          <div className="business-form-grid">
            ${renderBusinessField({ form, errors, field: "title", label: "项目名称", placeholder: "例如：客服工单协同 SaaS 采购" })}
            ${renderBusinessField({ form, errors, field: "requester_name", label: "发起人", placeholder: "填写业务发起人" })}
            ${renderBusinessField({ form, errors, field: "department", label: "所属部门", placeholder: "填写业务部门" })}
            ${renderBusinessField({ form, errors, field: "vendor_name", label: "意向供应商", placeholder: "可选，后续采购可重新筛选" })}
            ${renderBusinessField({ form, errors, field: "category", label: "采购类别", placeholder: "例如：software / service" })}
            ${renderBusinessField({ form, errors, field: "budget_amount", label: "预算金额", placeholder: "填写大于 0 的金额", type: "number" })}
            ${renderBusinessField({ form, errors, field: "currency", label: "币种", placeholder: "CNY" })}
            ${renderBusinessField({ form, errors, field: "target_go_live_date", label: "期望上线时间", placeholder: "", type: "date" })}
            ${renderBusinessField({
              form,
              errors,
              field: "data_scope",
              label: "数据范围",
              placeholder: "",
              selectOptions: [
                { value: "none", label: "不涉及敏感或客户数据" },
                { value: "internal", label: "仅内部业务数据" },
                { value: "customer_data", label: "涉及客户数据" },
                { value: "sensitive_data", label: "涉及敏感数据" },
              ],
            })}
          </div>
        </div>

        <div className="business-form-section">
          <div className="business-form-heading">
            <span>采购说明</span>
            <small>用于上级判断业务必要性</small>
          </div>
          <div className="business-form-grid">
            ${renderBusinessField({ form, errors, field: "summary", label: "采购目的", placeholder: "说明采购背景、要解决的问题和采购内容", textarea: true, full: true })}
            ${renderBusinessField({ form, errors, field: "business_value", label: "业务价值", placeholder: "说明预期收益、效率提升或业务影响", textarea: true, full: true })}
          </div>
        </div>

        <div className="business-form-footer">
          <div className="subtle">${editable ? "提交前系统会检查红色字段；通过后直接流转到上级审批。" : "业务部门已完成当前阶段任务，可通过历史项目继续跟踪状态。"}</div>
          <div className="button-row">
            ${editable ? html`<button className="btn secondary" type="submit">暂存申请表</button>` : null}
            ${editable ? html`<button className="btn primary" type="button" onClick=${submitBusinessApplication}>提交申请表</button>` : null}
            ${actions.has("withdraw") ? html`<button className="btn secondary" type="button" onClick=${() => runAction(`/projects/${projectDetail.id}/withdraw`, { reason: "申请人主动撤回修改。" })}>撤回修改</button>` : null}
            ${actions.has("cancel") ? html`<button className="btn ghost" type="button" onClick=${() => runAction(`/projects/${projectDetail.id}/cancel`, { reason: "业务部门撤销采购申请。" })}>撤销申请</button>` : null}
          </div>
        </div>
      </form>
    `;
  }

  function renderBusinessWorkspaceV2() {
    const currentStageIndex = projectDetail ? Math.max(PROJECT_STAGE_ORDER.indexOf(projectDetail.current_stage), 0) : 0;

    return html`
      <div>
        <div className="topbar">
          <div>
            <h2>业务审核</h2>
            <p>填写采购申请表，暂存修改，确认格式无误后提交到上级审批。</p>
          </div>
        </div>
        ${error ? html`<div className="error" style=${{ marginBottom: "18px" }}>${error}</div>` : null}

        <section className="section-block">
          <div className="panel business-workbench">
            <div className="section-title-row">
              <div>
                <h3>${projectDetail?.title || "新采购申请表"}</h3>
                <div className="subtle">
                  ${projectDetail ? `当前状态：${stageText(projectDetail.current_stage)} / ${formatCurrency(projectDetail.budget_amount, projectDetail.currency)}` : "当前为未暂存的新申请表。"}
                </div>
              </div>
              <div className="business-toolbar">
                <button className="btn ghost" type="button" onClick=${resetBusinessApplicationForm}>新建空白表</button>
                <button className="btn secondary" type="button" onClick=${() => setBusinessDialog("history")}>历史项目列表</button>
              </div>
            </div>

            <div className="business-progress-rail">
              ${PROJECT_STAGE_ORDER.map((stage, index) => {
                const nodeTone = index < currentStageIndex ? "done" : index === currentStageIndex ? "active" : "pending";
                return html`
                  <div className="business-progress-step" key=${stage}>
                    <div className=${`business-progress-node ${nodeTone}`}>
                      <span className="business-progress-dot">${index + 1}</span>
                      <span className="business-progress-name">${stageText(stage)}</span>
                    </div>
                    ${index < PROJECT_STAGE_ORDER.length - 1 ? html`<div className=${`business-progress-link ${index < currentStageIndex ? "active" : ""}`}></div>` : null}
                  </div>
                `;
              })}
            </div>
          </div>
        </section>

        <section className="section-block">
          <div className="panel business-form-panel">
            <div className="section-title-row">
              <div>
                <h3>采购申请表</h3>
                <div className="subtle">空白或不符合要求的字段会标红；提交时如果仍有错误，系统会弹窗提醒重新填写。</div>
              </div>
              ${projectDetail
                ? html`
                    <div className="button-row">
                      <span className="status-badge ${toneOf(projectDetail.status)}">${displayLabel(projectDetail.status)}</span>
                      <span className="status-badge neutral">${stageText(projectDetail.current_stage)}</span>
                    </div>
                  `
                : null}
            </div>
            ${loadingDetail && selectedProjectId
              ? html`<div className="center-panel" style=${{ minHeight: "220px" }}><div className="loading-ring"></div></div>`
              : renderBusinessForm()}
          </div>
        </section>

        ${businessDialog === "history"
          ? html`
              <div className="business-modal-mask" onClick=${() => setBusinessDialog("")}>
                <div className="business-modal-panel history-panel" onClick=${(event) => event.stopPropagation()}>
                  <div className="section-title-row">
                    <h3>历史项目列表</h3>
                    <button className="btn ghost small" type="button" onClick=${() => setBusinessDialog("")}>关闭</button>
                  </div>
                  ${projects.length
                    ? html`
                        <div className="stack-list">
                          ${projects.map((item) => html`
                            <button key=${item.id} className=${selectedProjectId === item.id ? "project-list-item active" : "project-list-item"} onClick=${() => { setBusinessCreatingNew(false); setSelectedProjectId(item.id); setBusinessDialog(""); }}>
                              <div className="activity-main">
                                <strong>${item.title}</strong>
                                <div className="subtle">${stageText(item.current_stage)} / ${formatCurrency(item.budget_amount, item.currency)}</div>
                              </div>
                              <div className="activity-meta"><span className="status-badge ${toneOf(item.status)}">${displayLabel(item.status)}</span></div>
                            </button>
                          `)}
                        </div>
                      `
                    : html`<div className="empty-box">暂时还没有历史项目。</div>`}
                </div>
              </div>
            `
          : null}
      </div>
    `;
  }

  function openManagerProject(projectId) {
    setSelectedProjectId(projectId);
    setManagerDialogOpen(true);
  }

  function renderManagerDetailModal() {
    if (!managerDialogOpen || !projectDetail) return null;

    return html`
      <div className="manager-modal-mask" onClick=${() => setManagerDialogOpen(false)}>
        <div className="manager-modal-panel" onClick=${(event) => event.stopPropagation()}>
          <div className="section-title-row">
            <div>
              <h3>${projectDetail.title}</h3>
              <div className="subtle">${stageText(projectDetail.current_stage)} / ${formatCurrency(projectDetail.budget_amount, projectDetail.currency)}</div>
            </div>
            <div className="button-row">
              <span className="status-badge ${toneOf(projectDetail.status)}">${displayLabel(projectDetail.status)}</span>
              <button className="btn ghost small" type="button" onClick=${() => setManagerDialogOpen(false)}>关闭</button>
            </div>
          </div>

          <div className="manager-modal-grid">
            <div className="mini-metric"><span className="mini-label">发起人</span><strong>${projectDetail.requester_name || "-"}</strong></div>
            <div className="mini-metric"><span className="mini-label">所属部门</span><strong>${projectDetail.department || "-"}</strong></div>
            <div className="mini-metric"><span className="mini-label">当前阶段</span><strong>${stageText(projectDetail.current_stage)}</strong></div>
            <div className="mini-metric"><span className="mini-label">目标供应商</span><strong>${projectDetail.vendor_name || "待确定"}</strong></div>
          </div>

          <div className="info-box">
            <strong>采购目的</strong>
            <div className="subtle">${projectDetail.summary || "未填写"}</div>
          </div>

          <div className="info-box">
            <strong>业务价值</strong>
            <div className="subtle">${projectDetail.business_value || "未填写"}</div>
          </div>

          ${projectDetail.latest_legal_review
            ? html`
                <div className="info-box">
                  <strong>法务结论摘要</strong>
                  <div className="subtle">${projectDetail.latest_legal_review.summary || projectDetail.latest_legal_review.conclusion || "暂无摘要"}</div>
                </div>
              `
            : null}

          ${projectDetail.blocker_summary?.length
            ? html`
                <div className="stack-list">
                  ${projectDetail.blocker_summary.map((item) => html`<div className="inline-alert warn" key=${item}>${item}</div>`)}
                </div>
              `
            : html`<div className="empty-box compact">当前没有阻塞项。</div>`}

          <div className="section-title-row">
            <h4>审批动作</h4>
            <div className="button-row">${renderStageActions()}</div>
          </div>

          <div className="manager-section-grid">
            <div>
              <div className="section-title-row"><h4>当前任务</h4></div>
              ${currentTasks.length
                ? html`<div className="stack-list">${currentTasks.map((item) => html`<div className="activity-item" key=${item.id}><div className="activity-main"><strong>${item.title}</strong><div className="subtle">${item.details}</div></div><div className="activity-meta"><span className="status-badge ${toneOf(item.status)}">${displayLabel(item.status)}</span></div></div>`)}</div>`
                : html`<div className="empty-box compact">当前阶段没有额外任务。</div>`}
            </div>
            <div>
              <div className="section-title-row"><h4>当前材料</h4></div>
              ${currentArtifacts.length
                ? html`<div className="stack-list">${currentArtifacts.map((item) => html`<div className="activity-item" key=${item.id}><div className="activity-main"><strong>${item.title}</strong><div className="subtle">${item.description}</div></div><div className="activity-meta"><span className="status-badge ${toneOf(item.status)}">${displayLabel(item.status)}</span></div></div>`)}</div>`
                : html`<div className="empty-box compact">当前阶段没有额外材料。</div>`}
            </div>
          </div>
        </div>
      </div>
    `;
  }

  function renderManagerWorkspace() {
    const pendingStages = new Set(["manager_review", "final_approval"]);
    const pendingProjects = projects.filter((item) => item.status === "active" && pendingStages.has(item.current_stage));
    const grouped = groupByStage(projects);

    return html`
      <div>
        <div className="topbar">
          <div>
            <h2>审批工作台</h2>
            <p>看阶段、挑项目、做决定，信息够用就好，不在这儿堆太多东西。</p>
          </div>
        </div>
        ${error ? html`<div className="error" style=${{ marginBottom: "18px" }}>${error}</div>` : null}

        <section className="section-block">
          <div className="section-title-row">
            <h3>阶段看板</h3>
          </div>
          <div className="stage-board manager-stage-board">
            ${grouped.map((group) => html`
              <div className="stage-column" key=${group.stage}>
                <div className="stage-column-head">
                  <strong>${stageText(group.stage)}</strong>
                  <span>${group.items.length}</span>
                </div>
                <div className="stage-column-body">
                  ${group.items.length
                    ? group.items.map((item) => html`
                        <button key=${item.id} className=${selectedProjectId === item.id && managerDialogOpen ? "stage-card active" : "stage-card"} onClick=${() => openManagerProject(item.id)}>
                          <strong>${item.title}</strong>
                          <div className="subtle">${item.department || "未标记部门"} / ${item.vendor_name || "待确定供应商"}</div>
                          <div className="status-line">
                            <span className="status-badge ${toneOf(item.status)}">${displayLabel(item.status)}</span>
                          </div>
                        </button>
                      `)
                    : html`<div className="empty-box compact">暂无项目</div>`}
                </div>
              </div>
            `)}
          </div>
        </section>

        <section className="section-block">
          <div className="section-title-row">
            <h3>待我审批</h3>
            <div className="subtle">${pendingProjects.length} 个项目</div>
          </div>
          ${pendingProjects.length
            ? html`
                <div className="panel">
                  <div className="stack-list">
                    ${pendingProjects.map((item) => html`
                      <button key=${item.id} className=${selectedProjectId === item.id && managerDialogOpen ? "project-list-item active" : "project-list-item"} onClick=${() => openManagerProject(item.id)}>
                        <div className="activity-main">
                          <strong>${item.title}</strong>
                          <div className="subtle">${stageText(item.current_stage)} / ${item.department || "未标记部门"} / ${formatCurrency(item.budget_amount, item.currency)}</div>
                        </div>
                        <div className="activity-meta">
                          <span className="status-badge neutral">${item.vendor_name || "待确定供应商"}</span>
                        </div>
                      </button>
                    `)}
                  </div>
                </div>
              `
            : html`<div className="panel"><div className="empty-box">当前没有待审批项目。</div></div>`}
        </section>

        ${renderManagerDetailModal()}
      </div>
    `;
  }

  function renderProcurementWorkspace() {
    const sourcingProjects = projects.filter((item) => item.status === "active" && item.current_stage === "procurement_sourcing");
    const actions = new Set(projectDetail?.allowed_actions || []);
    const currentStageIndex = projectDetail ? Math.max(PROJECT_STAGE_ORDER.indexOf(projectDetail.current_stage), 0) : 0;
    const vendorErrors = vendorFormErrorsFor(vendorForm);
    const otherSourcingProjects = sourcingProjects.filter((item) => item.id !== projectDetail?.id);

    return html`
      <div>
        <div className="topbar">
          <div>
            <h2>采购执行工作台</h2>
            <p>采购人员只处理已获批项目的供应商绑定。供应商筛选在线下完成，平台内只录入确认后的供应商信息，并在需要时提交法务。</p>
          </div>
          <div className="button-row">
            <button className="btn secondary" type="button" onClick=${openProcurementAssistant} disabled=${!projectDetail}>
              去审查助手评估供应商
            </button>
          </div>
        </div>
        ${error ? html`<div className="error" style=${{ marginBottom: "18px" }}>${error}</div>` : null}

        ${projectDetail
          ? html`
              <section className="section-block">
                <div className="panel">
                  <div className="section-title-row">
                    <div>
                      <h3>${projectDetail.title}</h3>
                      <div className="subtle">${stageText(projectDetail.current_stage)} / ${formatCurrency(projectDetail.budget_amount, projectDetail.currency)}</div>
                    </div>
                    <span className="status-badge ${toneOf(projectDetail.status)}">${displayLabel(projectDetail.status)}</span>
                  </div>
                  <div className="project-progress-line">
                    ${PROJECT_STAGE_ORDER.map((stage, index) => html`
                      <div key=${stage} className=${index <= currentStageIndex ? "progress-node active" : "progress-node"}>
                        <span>${index + 1}</span>
                        <small>${stageText(stage)}</small>
                      </div>
                    `)}
                  </div>
                </div>
              </section>
            `
          : null}

        <div className="projects-layout wide procurement-layout">
          <section className="panel">
            ${loadingDetail
              ? html`<div className="center-panel" style=${{ minHeight: "220px" }}><div className="loading-ring"></div></div>`
              : projectDetail
                ? html`
                    <div className="info-box">
                      <strong>项目摘要</strong>
                      <div className="subtle">${projectDetail.summary || "暂无摘要"}</div>
                    </div>

                    <div className="info-box" style=${{ marginTop: "12px" }}>
                      <strong>业务价值</strong>
                      <div className="subtle">${projectDetail.business_value || "暂无说明"}</div>
                    </div>

                    ${projectDetail.current_stage === "procurement_sourcing" && projectDetail.status === "active"
                      ? html`
                          <div className="section-title-row" style=${{ marginTop: "20px" }}>
                            <h4>绑定供应商信息</h4>
                            <div className="button-row">
                              <button className="btn ghost small" type="button" onClick=${openProcurementAssistant}>先去审查助手</button>
                            </div>
                          </div>
                          <div className="section-title-row" style=${{ marginTop: "20px" }}>
                            <h4>上传供应商材料包</h4>
                          </div>
                          <div className="info-box">
                            <div className="stack-list">
                              <div className="subtle">支持一次上传多份材料，Agent 会先提取核心信息，再自动补全下面的供应商表单。</div>
                              <input
                                className="field"
                                type="file"
                                multiple=${true}
                                accept=".pdf,.doc,.docx,.md,.markdown,.txt,.csv"
                                onChange=${(e) => setVendorMaterialFiles(Array.from(e.target.files || []))}
                              />
                              ${vendorMaterialFiles.length
                                ? html`
                                    <div className="stack-list">
                                      ${vendorMaterialFiles.map((file) => html`
                                        <div className="activity-item" key=${`${file.name}-${file.size}`}>
                                          <div className="activity-main">
                                            <strong>${file.name}</strong>
                                            <div className="subtle">${Math.max(1, Math.round(file.size / 1024))} KB</div>
                                          </div>
                                        </div>
                                      `)}
                                    </div>
                                  `
                                : null}
                              <div className="button-row">
                                <button className="btn secondary" type="button" onClick=${extractVendorMaterials} disabled=${extractingVendorMaterials || !vendorMaterialFiles.length}>
                                  ${extractingVendorMaterials ? "正在提取材料..." : "Agent 提取并补全表单"}
                                </button>
                              </div>
                            </div>
                          </div>

                          ${vendorMaterialExtraction
                            ? html`
                                <div className="info-box" style=${{ marginTop: "12px" }}>
                                  <strong>材料提取结果</strong>
                                  <div className="subtle" style=${{ marginTop: "8px" }}>${vendorMaterialExtraction.extraction_summary}</div>
                                  ${vendorMaterialExtraction.warnings?.length
                                    ? html`
                                        <div className="stack-list" style=${{ marginTop: "10px" }}>
                                          ${vendorMaterialExtraction.warnings.map((item) => html`<div className="inline-alert warn" key=${item}>${item}</div>`)}
                                        </div>
                                      `
                                    : null}
                                  ${vendorMaterialExtraction.extracted_materials?.length
                                    ? html`
                                        <div className="stack-list" style=${{ marginTop: "12px" }}>
                                          ${vendorMaterialExtraction.extracted_materials.map((item) => html`
                                            <div className="activity-item" key=${`${item.name}-${item.source_type}`}>
                                              <div className="activity-main">
                                                <strong>${item.name}</strong>
                                                <div className="subtle">${item.source_type} / ${item.char_count} 字符</div>
                                                <div className="subtle">${item.excerpt}</div>
                                              </div>
                                            </div>
                                          `)}
                                        </div>
                                      `
                                    : null}
                                </div>
                              `
                            : null}

                          <form className="business-form" onSubmit=${createVendor}>
                            <div className="business-form-grid">
                              <label className="business-form-field">
                                <span className="business-form-label">供应商名称</span>
                                <input className=${vendorErrors.vendor_name || vendorFormErrors.vendor_name ? "field error" : "field"} placeholder="填写供应商名称" value=${vendorForm.vendor_name} onInput=${(e) => updateVendorField("vendor_name", e.target.value)} />
                                ${(vendorErrors.vendor_name || vendorFormErrors.vendor_name) ? html`<small className="field-error-text">${vendorErrors.vendor_name || vendorFormErrors.vendor_name}</small>` : null}
                              </label>
                              <label className="business-form-field">
                                <span className="business-form-label">来源平台</span>
                                <input className=${vendorErrors.source_platform || vendorFormErrors.source_platform ? "field error" : "field"} placeholder="例如：官网 / 天眼查 / 招标网" value=${vendorForm.source_platform} onInput=${(e) => updateVendorField("source_platform", e.target.value)} />
                                ${(vendorErrors.source_platform || vendorFormErrors.source_platform) ? html`<small className="field-error-text">${vendorErrors.source_platform || vendorFormErrors.source_platform}</small>` : null}
                              </label>
                              <label className="business-form-field full">
                                <span className="business-form-label">来源链接</span>
                                <input className=${vendorErrors.source_url || vendorFormErrors.source_url ? "field error" : "field"} placeholder="可选，填写公开链接" value=${vendorForm.source_url} onInput=${(e) => updateVendorField("source_url", e.target.value)} />
                                ${(vendorErrors.source_url || vendorFormErrors.source_url) ? html`<small className="field-error-text">${vendorErrors.source_url || vendorFormErrors.source_url}</small>` : null}
                              </label>
                              <label className="business-form-field full">
                                <span className="business-form-label">供应商简介</span>
                                <textarea className=${vendorErrors.profile_summary || vendorFormErrors.profile_summary ? "field error textarea-medium" : "field textarea-medium"} placeholder="说明公司背景、产品能力、服务范围等关键信息" value=${vendorForm.profile_summary} onInput=${(e) => updateVendorField("profile_summary", e.target.value)}></textarea>
                                ${(vendorErrors.profile_summary || vendorFormErrors.profile_summary) ? html`<small className="field-error-text">${vendorErrors.profile_summary || vendorFormErrors.profile_summary}</small>` : null}
                              </label>
                              <label className="business-form-field full">
                                <span className="business-form-label">采购说明</span>
                                <textarea className=${vendorErrors.procurement_notes || vendorFormErrors.procurement_notes ? "field error textarea-medium" : "field textarea-medium"} placeholder="填写报价情况、线下筛选结论、为什么要绑定到这个项目" value=${vendorForm.procurement_notes} onInput=${(e) => updateVendorField("procurement_notes", e.target.value)}></textarea>
                                ${(vendorErrors.procurement_notes || vendorFormErrors.procurement_notes) ? html`<small className="field-error-text">${vendorErrors.procurement_notes || vendorFormErrors.procurement_notes}</small>` : null}
                              </label>
                            </div>
                            <div className="split-fields">
                              <div className="subtle">必填项未完成会直接标红；补齐后再保存并绑定到当前项目。</div>
                            </div>
                            <div className="button-row">
                              <button className="btn secondary" type="button" onClick=${openProcurementAssistant}>带着这些信息去审查助手</button>
                              <button className="btn primary" type="submit">保存并绑定到项目</button>
                            </div>
                          </form>
                        `
                      : null}

                    ${vendors.length
                      ? html`
                          <div className="section-title-row" style=${{ marginTop: "22px" }}>
                            <h4>已绑定供应商</h4>
                          </div>
                          <div className="stack-list">${vendors.map((vendor) => html`
                            <button key=${vendor.id} className=${activeVendor?.id === vendor.id ? "project-list-item active" : "project-list-item"} onClick=${() => setActiveVendorId(vendor.id)}>
                              <div className="activity-main">
                                <strong>${vendor.vendor_name}</strong>
                                <div className="subtle">${vendor.source_platform || "手工录入"} / ${vendor.profile_summary || "暂无简介"}</div>
                              </div>
                              <div className="activity-meta">
                                <span className="status-badge ${toneOf(vendor.status)}">${displayLabel(vendor.status)}</span>
                              </div>
                            </button>
                          `)}</div>

                          ${activeVendor
                            ? html`
                                <div className="info-box" style=${{ marginTop: "16px" }}>
                                  <strong>当前供应商信息</strong>
                                  <div className="stack-list" style=${{ marginTop: "10px" }}>
                                    <div className="subtle">供应商：${activeVendor.vendor_name || "-"}</div>
                                    <div className="subtle">来源：${activeVendor.source_platform || "-"} ${activeVendor.source_url ? `/ ${activeVendor.source_url}` : ""}</div>
                                    <div className="subtle">简介：${activeVendor.profile_summary || "暂无简介"}</div>
                                    <div className="subtle">采购说明：${activeVendor.procurement_notes || "暂无说明"}</div>
                                  </div>
                                  ${projectDetail.current_stage === "procurement_sourcing" && actions.has("select_vendor") && !["legal_rejected", "rejected"].includes(activeVendor.status)
                                    ? html`<div className="button-row" style=${{ marginTop: "14px" }}>
                                        <button className="btn primary" type="button" onClick=${() => runAction(`/projects/${projectDetail.id}/vendors/${activeVendor.id}/select`, { reason: "采购已确认该供应商，提交法务审查。" })}>
                                          确认该供应商并提交法务
                                        </button>
                                      </div>`
                                    : null}
                                </div>
                              `
                            : null}
                        `
                      : null}
                  `
                : html`<div className="empty-box">请选择一个采购项目</div>`}
          </section>

          <section className="panel">
            <div className="section-title-row">
              <h3>当前计划</h3>
              <div className="button-row">
                <button className="btn ghost small" type="button" onClick=${() => setProcurementDialogOpen(true)}>
                  查看进行中计划
                </button>
              </div>
            </div>
            ${projectDetail
              ? html`
                  <div className="stack-list">
                    <div className="info-box">
                      <strong>${projectDetail.title}</strong>
                      <div className="subtle">${projectDetail.department || "-"} / ${formatCurrency(projectDetail.budget_amount, projectDetail.currency)}</div>
                    </div>
                    <div className="mini-metric"><span className="mini-label">当前阶段</span><strong>${stageText(projectDetail.current_stage)}</strong></div>
                    <div className="mini-metric"><span className="mini-label">目标供应商</span><strong>${projectDetail.vendor_name || "待绑定"}</strong></div>
                    <div className="mini-metric"><span className="mini-label">业务摘要</span><strong>${projectDetail.summary || "暂无摘要"}</strong></div>
                  </div>
                `
              : html`<div className="empty-box">当前没有采购计划</div>`}
          </section>
        </div>

        ${procurementDialogOpen
          ? html`
              <div className="business-modal-mask" onClick=${() => setProcurementDialogOpen(false)}>
                <div className="business-modal-panel history-panel" onClick=${(event) => event.stopPropagation()}>
                  <div className="section-title-row">
                    <h3>进行中计划</h3>
                    <button className="btn ghost small" type="button" onClick=${() => setProcurementDialogOpen(false)}>关闭</button>
                  </div>
                  ${otherSourcingProjects.length
                    ? html`<div className="stack-list">
                        ${otherSourcingProjects.map((item) => html`
                          <button key=${item.id} className="project-list-item" onClick=${() => { setSelectedProjectId(item.id); setProcurementDialogOpen(false); }}>
                            <div className="activity-main">
                              <strong>${item.title}</strong>
                              <div className="subtle">${item.department || "-"} / ${formatCurrency(item.budget_amount, item.currency)}</div>
                            </div>
                            <div className="activity-meta">
                              <span className="status-badge neutral">${item.vendor_name || "待绑定供应商"}</span>
                            </div>
                          </button>
                        `)}
                      </div>`
                    : html`<div className="empty-box">当前没有其他进行中计划</div>`}
                </div>
              </div>
            `
          : null}
      </div>
    `;
  }

  if (currentUser.role === "business") {
    return renderBusinessWorkspaceV2();
  }

  if (currentUser.role === "manager") {
    return renderManagerWorkspace();
  }

  if (currentUser.role === "procurement") {
    return renderProcurementWorkspace();
  }

  const grouped = groupByStage(projects);

  return html`
    <div>
      <div className="topbar"><div><h2>采购项目</h2><p>围绕业务申请、采购比选、法务审查、终审与签署的多角色协同工作台。</p></div></div>
      ${error ? html`<div className="error" style=${{ marginBottom: "18px" }}>${error}</div>` : null}

      <section className="section-block">
        <div className="section-title-row"><h3>阶段看板</h3></div>
        <div className="stage-board">
          ${grouped.map((group) => html`
            <div className="stage-column" key=${group.stage}>
              <div className="stage-column-head"><strong>${stageText(group.stage)}</strong><span>${group.items.length}</span></div>
              <div className="stage-column-body">
                ${group.items.length ? group.items.map((item) => html`
                  <button key=${item.id} className=${selectedProjectId === item.id ? "stage-card active" : "stage-card"} onClick=${() => setSelectedProjectId(item.id)}>
                    <strong>${item.title}</strong>
                    <div className="subtle">${item.vendor_name || "尚未选定目标供应商"}</div>
                    <div className="status-line">
                      <span className="status-badge ${toneOf(item.risk_level)}">${displayLabel(item.risk_level)}</span>
                      <span className="status-badge ${toneOf(item.status)}">${displayLabel(item.status)}</span>
                    </div>
                  </button>
                `) : html`<div className="empty-box compact">暂无项目</div>`}
              </div>
            </div>
          `)}
        </div>
      </section>

      <div className="projects-layout">
        <section className="panel">
          <div className="section-title-row"><h3>创建新项目</h3>${currentUser.role === "admin" ? html`<button className="btn secondary" type="button" onClick=${createDemoProject}>加载演示项目</button>` : null}</div>
          <form className="stack-list" onSubmit=${createProject}>
            <input className="field" placeholder="项目名称" value=${createForm.title} onInput=${(e) => setCreateForm({ ...createForm, title: e.target.value })} />
            <div className="split-fields">
              <input className="field" placeholder="发起人" value=${createForm.requester_name} onInput=${(e) => setCreateForm({ ...createForm, requester_name: e.target.value })} />
              <input className="field" placeholder="所属部门" value=${createForm.department} onInput=${(e) => setCreateForm({ ...createForm, department: e.target.value })} />
            </div>
            <div className="split-fields">
              <input className="field" placeholder="初始候选供应商" value=${createForm.vendor_name} onInput=${(e) => setCreateForm({ ...createForm, vendor_name: e.target.value })} />
              <input className="field" placeholder="采购类别" value=${createForm.category} onInput=${(e) => setCreateForm({ ...createForm, category: e.target.value })} />
            </div>
            <div className="split-fields">
              <input className="field" type="number" placeholder="预算金额" value=${createForm.budget_amount} onInput=${(e) => setCreateForm({ ...createForm, budget_amount: e.target.value })} />
              <input className="field" placeholder="币种" value=${createForm.currency} onInput=${(e) => setCreateForm({ ...createForm, currency: e.target.value })} />
            </div>
            <input className="field" type="date" value=${createForm.target_go_live_date} onInput=${(e) => setCreateForm({ ...createForm, target_go_live_date: e.target.value })} />
            <input className="field" placeholder="数据范围" value=${createForm.data_scope} onInput=${(e) => setCreateForm({ ...createForm, data_scope: e.target.value })} />
            <textarea className="field textarea-medium" placeholder="项目背景与采购目的" value=${createForm.summary} onInput=${(e) => setCreateForm({ ...createForm, summary: e.target.value })}></textarea>
            <textarea className="field textarea-medium" placeholder="预期收益 / 业务价值" value=${createForm.business_value} onInput=${(e) => setCreateForm({ ...createForm, business_value: e.target.value })}></textarea>
            <div className="button-row"><button className="btn primary" type="submit">创建项目</button></div>
          </form>
        </section>

        <section className="panel">
          <div className="section-title-row"><h3>项目列表</h3></div>
          ${projects.length ? html`<div className="stack-list">${projects.map((item) => html`
            <button key=${item.id} className=${selectedProjectId === item.id ? "project-list-item active" : "project-list-item"} onClick=${() => setSelectedProjectId(item.id)}>
              <div className="activity-main"><strong>${item.title}</strong><div className="subtle">${stageText(item.current_stage)} / ${formatCurrency(item.budget_amount, item.currency)}</div></div>
              <div className="activity-meta"><span className="status-badge ${toneOf(item.status)}">${displayLabel(item.status)}</span></div>
            </button>
          `)}</div>` : html`<div className="empty-box">暂时还没有采购项目。</div>`}
        </section>
      </div>

      ${loadingDetail ? html`<div className="center-panel" style=${{ minHeight: "220px" }}><div className="loading-ring"></div></div>` : projectDetail ? html`
        <section className="section-block">
          <div className="section-title-row">
            <h3>${projectDetail.title}</h3>
            <div className="button-row">
              <span className="status-badge ${toneOf(projectDetail.risk_level)}">${displayLabel(projectDetail.risk_level)}</span>
              <span className="status-badge ${toneOf(projectDetail.status)}">${displayLabel(projectDetail.status)}</span>
              <span className="status-badge neutral">${stageText(projectDetail.current_stage)}</span>
            </div>
          </div>
          <div className="project-meta-grid">
            <div className="mini-metric"><span className="mini-label">当前负责人</span><strong>${displayLabel(projectDetail.current_owner_role)}</strong></div>
            <div className="mini-metric"><span className="mini-label">目标供应商</span><strong>${projectDetail.vendor_name || "-"}</strong></div>
            <div className="mini-metric"><span className="mini-label">预算</span><strong>${formatCurrency(projectDetail.budget_amount, projectDetail.currency)}</strong></div>
            <div className="mini-metric"><span className="mini-label">可执行动作</span><strong>${projectDetail.allowed_actions.length}</strong></div>
          </div>
          ${projectDetail.blocker_summary.length ? html`<div className="project-blocker-banner"><strong>当前阻塞</strong><div className="stack-list">${projectDetail.blocker_summary.slice(0, 5).map((item) => html`<div className="inline-alert warn" key=${item}>${item}</div>`)}</div></div>` : html`<div className="project-blocker-banner success"><strong>${projectDetail.status === "cancelled" ? "项目已取消" : "当前阶段可继续推进"}</strong></div>`}
        </section>

        <div className="projects-layout wide">
          <section className="panel">
            <div className="section-title-row"><h3>当前阶段动作</h3><div className="button-row">${renderStageActions()}</div></div>
            ${["procurement_sourcing", "legal_review"].includes(projectDetail.current_stage)
              ? html`
                  <label className="label">AI 审查问题</label>
                  <textarea className="field textarea-large" value=${reviewQuery} onInput=${(e) => setReviewQuery(e.target.value)}></textarea>
                `
              : null}

            ${projectDetail.draft_editable ? html`
              <div className="section-title-row" style=${{ marginTop: "20px" }}><h4>采购申请表</h4></div>
              <form className="stack-list" onSubmit=${saveDraftProject}>
                <input className="field" placeholder="项目名称" value=${draftForm.title} onInput=${(e) => setDraftForm({ ...draftForm, title: e.target.value })} />
                <div className="split-fields">
                  <input className="field" placeholder="发起人" value=${draftForm.requester_name} onInput=${(e) => setDraftForm({ ...draftForm, requester_name: e.target.value })} />
                  <input className="field" placeholder="所属部门" value=${draftForm.department} onInput=${(e) => setDraftForm({ ...draftForm, department: e.target.value })} />
                </div>
                <div className="split-fields">
                  <input className="field" placeholder="初始候选供应商" value=${draftForm.vendor_name} onInput=${(e) => setDraftForm({ ...draftForm, vendor_name: e.target.value })} />
                  <input className="field" placeholder="采购类别" value=${draftForm.category} onInput=${(e) => setDraftForm({ ...draftForm, category: e.target.value })} />
                </div>
                <div className="split-fields">
                  <input className="field" type="number" placeholder="预算金额" value=${draftForm.budget_amount} onInput=${(e) => setDraftForm({ ...draftForm, budget_amount: e.target.value })} />
                  <input className="field" placeholder="币种" value=${draftForm.currency} onInput=${(e) => setDraftForm({ ...draftForm, currency: e.target.value })} />
                </div>
                <input className="field" type="date" value=${draftForm.target_go_live_date} onInput=${(e) => setDraftForm({ ...draftForm, target_go_live_date: e.target.value })} />
                <input className="field" placeholder="数据范围" value=${draftForm.data_scope} onInput=${(e) => setDraftForm({ ...draftForm, data_scope: e.target.value })} />
                <textarea className="field textarea-medium" placeholder="项目背景与采购目的" value=${draftForm.summary} onInput=${(e) => setDraftForm({ ...draftForm, summary: e.target.value })}></textarea>
                <textarea className="field textarea-medium" placeholder="预期收益 / 业务价值" value=${draftForm.business_value} onInput=${(e) => setDraftForm({ ...draftForm, business_value: e.target.value })}></textarea>
                <div className="button-row"><button className="btn secondary" type="submit">保存采购申请表</button></div>
              </form>
            ` : null}

            ${projectDetail.current_stage === "business_draft"
              ? html`
                  <div className="section-title-row" style=${{ marginTop: "20px" }}><h4>系统校验结果</h4></div>
                  <div className=${projectDetail.application_form_ready ? "project-blocker-banner success" : "project-blocker-banner"}>
                    <strong>${projectDetail.application_form_ready ? "采购申请表已满足推进条件" : "采购申请表还有待补齐项"}</strong>
                    <div className="subtle">${projectDetail.application_form_summary}</div>
                  </div>
                  ${projectDetail.application_checks?.length
                    ? html`
                        <div className="stack-list" style=${{ marginTop: "12px" }}>
                          ${projectDetail.application_checks.map((item) => html`
                            <div className="activity-item" key=${item.key}>
                              <div className="activity-main">
                                <strong>${item.label}</strong>
                                <div className="subtle">${item.detail}</div>
                              </div>
                              <div className="activity-meta">
                                <span className="status-badge ${toneOf(item.checked ? "pass" : "pending")}">${displayLabel(item.checked ? "pass" : "pending")}</span>
                              </div>
                            </div>
                          `)}
                        </div>
                      `
                    : html`<div className="empty-box">当前还没有申请表校验项。</div>`}

                  <div className="section-title-row" style=${{ marginTop: "20px" }}><h4>流转材料</h4></div>
                  <div className="activity-item">
                    <div className="activity-main">
                      <strong>采购申请表</strong>
                      <div className="subtle">系统内置主文档，随表单字段自动更新并贯穿整个流程。</div>
                    </div>
                    <div className="activity-meta">
                      <span className="status-badge ${toneOf(projectDetail.application_form_ready ? "provided" : "missing")}">${displayLabel(projectDetail.application_form_ready ? "provided" : "missing")}</span>
                    </div>
                  </div>
                `
              : html`
                  <div className="section-title-row" style=${{ marginTop: "20px" }}><h4>当前阶段待办</h4></div>
                  ${currentTasks.length ? html`<div className="stack-list">${currentTasks.map((task) => html`
                    <div className="activity-item" key=${task.id}>
                      <div className="activity-main"><strong>${task.title}</strong><div className="subtle">${displayLabel(task.assignee_role)} / ${task.task_type}</div></div>
                      <div className="activity-meta"><span className="status-badge ${toneOf(task.status)}">${displayLabel(task.status)}</span>${task.status !== "done" && projectDetail.status === "active" ? html`<button className="btn ghost small" onClick=${() => markTaskDone(task.id)}>标记完成</button>` : null}</div>
                    </div>
                  `)}</div>` : html`<div className="empty-box">当前阶段暂无待办。</div>`}

                  <div className="section-title-row" style=${{ marginTop: "20px" }}><h4>当前阶段材料</h4></div>
                  ${currentArtifacts.length ? html`<div className="stack-list">${currentArtifacts.map((artifact) => html`
                    <div className="activity-item" key=${artifact.id}>
                      <div className="activity-main"><strong>${artifact.title}</strong><div className="subtle">${artifact.artifact_type} / ${displayLabel(artifact.direction)}</div></div>
                      <div className="activity-meta"><span className="status-badge ${toneOf(artifact.status)}">${displayLabel(artifact.status)}</span>${!["provided", "approved"].includes(artifact.status) && projectDetail.status === "active" ? html`<button className="btn ghost small" onClick=${() => markArtifactProvided(artifact.id)}>标记已提供</button>` : null}</div>
                    </div>
                  `)}</div>` : html`<div className="empty-box">当前阶段暂无材料要求。</div>`}
                `}
          </section>

          <section className="panel">
            <div className="section-title-row"><h3>候选供应商</h3></div>
            ${projectDetail.current_stage === "procurement_sourcing" && projectDetail.status === "active" ? html`
              <form className="stack-list" onSubmit=${createVendor}>
                <input className="field" placeholder="供应商名称" value=${vendorForm.vendor_name} onInput=${(e) => setVendorForm({ ...vendorForm, vendor_name: e.target.value })} />
                <div className="split-fields">
                  <input className="field" placeholder="来源平台" value=${vendorForm.source_platform} onInput=${(e) => setVendorForm({ ...vendorForm, source_platform: e.target.value })} />
                  <input className="field" placeholder="来源链接" value=${vendorForm.source_url} onInput=${(e) => setVendorForm({ ...vendorForm, source_url: e.target.value })} />
                </div>
                <textarea className="field textarea-medium" placeholder="公司简介与采集信息" value=${vendorForm.profile_summary} onInput=${(e) => setVendorForm({ ...vendorForm, profile_summary: e.target.value })}></textarea>
                <textarea className="field textarea-medium" placeholder="采购备注" value=${vendorForm.procurement_notes} onInput=${(e) => setVendorForm({ ...vendorForm, procurement_notes: e.target.value })}></textarea>
                <div className="button-row"><button className="btn secondary" type="submit">新增候选供应商</button></div>
              </form>
            ` : null}
            ${vendors.length ? html`<div className="stack-list" style=${{ marginTop: "16px" }}>${vendors.map((vendor) => html`
              <button key=${vendor.id} className=${activeVendor?.id === vendor.id ? "project-list-item active" : "project-list-item"} onClick=${() => setActiveVendorId(vendor.id)}>
                <div className="activity-main"><strong>${vendor.vendor_name}</strong><div className="subtle">${vendor.source_platform || "未填写来源平台"} / ${vendor.ai_recommendation ? displayLabel(vendor.ai_recommendation) : "尚未评审"}</div></div>
                <div className="activity-meta"><span className="status-badge ${toneOf(vendor.status)}">${displayLabel(vendor.status)}</span></div>
              </button>
            `)}</div>` : html`<div className="empty-box">还没有候选供应商。</div>`}

            <div className="section-title-row" style=${{ marginTop: "20px" }}><h4>结构化审查结果</h4></div>
            ${projectDetail.current_stage === "legal_review" || projectDetail.current_stage === "final_approval" || projectDetail.current_stage === "signing" || projectDetail.current_stage === "completed"
              ? html`<${ReviewSummaryCard} html=${html} title="法务结构化结论" review=${projectDetail.latest_legal_review} />`
              : html`<${ReviewSummaryCard} html=${html} title="供应商结构化结论" review=${activeVendor?.structured_review} />`}

            <div className="section-title-row" style=${{ marginTop: "20px" }}><h4>风险提示</h4></div>
            ${projectDetail.risks.length ? html`<div className="stack-list">${projectDetail.risks.slice(0, 8).map((risk) => html`
              <div className="activity-item" key=${risk.id}>
                <div className="activity-main"><strong>${risk.risk_type}</strong><div className="subtle">${risk.summary}</div></div>
                <div className="activity-meta"><span className="status-badge ${toneOf(risk.severity)}">${displayLabel(risk.severity)}</span></div>
              </div>
            `)}</div>` : html`<div className="empty-box">还没有风险记录。</div>`}
          </section>
        </div>

        <section className="section-block">
          <div className="section-title-row"><h3>项目时间线</h3></div>
          ${timeline.length ? html`<div className="timeline-list">${timeline.map((event) => html`
            <article className="timeline-card" key=${`${event.kind}-${event.created_at}-${event.title}`}>
              <div className="timeline-badge neutral">${event.kind}</div>
              <div className="timeline-body"><strong>${event.title}</strong><div className="subtle">${stageText(event.stage)} / ${event.created_at}</div><p>${event.summary}</p></div>
            </article>
          `)}</div>` : html`<div className="empty-box">暂无时间线事件。</div>`}
        </section>
      ` : null}
    </div>
  `;
}
