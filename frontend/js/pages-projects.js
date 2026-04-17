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

function projectArtifactTitle(artifact) {
  if (!artifact) return "-";
  if (artifact.artifact_type === "our_procurement_contract") return "我方采购合同";
  if (artifact.artifact_type === "counterparty_redline_contract") return "对方修改后的采购合同";
  return artifact.title;
}

function projectArtifactActionLabel(artifact) {
  if (artifact?.artifact_type === "our_procurement_contract") return "确认已上传我方合同";
  if (artifact?.artifact_type === "counterparty_redline_contract") return "确认已上传对方修改版";
  if (artifact?.artifact_type === "signed_contract") return "确认已上传签署合同";
  if (artifact?.artifact_type === "archive_summary") return "确认已补齐归档摘要";
  return "标记已提供";
}

function artifactIsReady(status) {
  return ["provided", "approved"].includes(status || "");
}

function legalProjectPriority(item) {
  if (!item) return 99;
  if (item.current_stage === "legal_review" && item.status === "active") return 0;
  if (item.current_stage === "legal_review") return 1;
  if (item.current_stage === "final_approval") return 2;
  if (item.current_stage === "signing") return 3;
  if (item.current_stage === "completed") return 4;
  return 9;
}

function adminProjectPriority(item) {
  if (!item) return 99;
  if (item.current_stage === "signing" && item.status === "active") return 0;
  if (item.current_stage === "signing") return 1;
  if (item.current_stage === "final_approval") return 2;
  if (item.current_stage === "completed") return 3;
  return 9;
}

function isSupportedLegalContractFile(file) {
  const name = (file?.name || "").toLowerCase();
  return name.endsWith(".md") || name.endsWith(".markdown") || name.endsWith(".docx");
}

function projectStageProgressIndex(stage) {
  const normalizedStage = stage === "final_approval" ? "signing" : stage;
  return Math.max(PROJECT_STAGE_ORDER.indexOf(normalizedStage), 0);
}

function groupByStage(projects) {
  return PROJECT_STAGE_ORDER.map((stage) => ({
    stage,
    items: projects.filter((item) => item.current_stage === stage && item.status !== "cancelled"),
  }));
}

function ReviewSummaryCard({ html, title, review }) {
  if (!review) {
    return html`<div className="empty-box">当前还没有结构化审查结论。</div>`;
  }

  return html`
    <div className="stack-list">
      <div className="info-box">
        <strong>${title}</strong>
        <p className="muted">${review.summary || review.conclusion}</p>
        <div className="button-row">
          <span className="status-badge ${toneOf(review.recommendation)}">${displayLabel(review.recommendation)}</span>
          ${review.risk_level ? html`<span className="status-badge ${toneOf(review.risk_level)}">${displayLabel(review.risk_level)}</span>` : null}
          ${review.decision_suggestion ? html`<span className="status-badge ${toneOf(review.decision_suggestion)}">${displayLabel(review.decision_suggestion)}</span>` : null}
        </div>
        <div className="subtle" style=${{ marginTop: "10px" }}>${review.conclusion}</div>
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

      ${review.clause_gaps?.length
        ? html`
            <div className="info-box">
              <strong>问题条款</strong>
              <div className="stack-list">
                ${review.clause_gaps.map((item) => html`<div className="inline-alert warn" key=${item}>${item}</div>`)}
              </div>
            </div>
          `
        : null}

      ${review.blocking_issues?.length
        ? html`
            <div className="info-box">
              <strong>审查提示</strong>
              <div className="stack-list">
                ${review.blocking_issues.map((item) => html`<div className="inline-alert info" key=${item}>${item}</div>`)}
              </div>
            </div>
          `
        : null}

      ${review.evidence?.length
        ? html`
            <div className="info-box">
              <strong>引用依据</strong>
              <div className="stack-list">
                ${review.evidence.map((item, index) => html`
                  <div className="activity-item" key=${`${item.document_title}-${item.location}-${index}`}>
                    <div className="activity-main">
                      <strong>${item.document_title || "引用片段"}</strong>
                      <div className="subtle">${item.location || "未标注位置"}</div>
                      <div className="subtle">${item.snippet}</div>
                    </div>
                  </div>
                `)}
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
  assistantResult,
  setAssistantTask,
  setAssistantResult,
  projectNavigationRequest,
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
  const [vendorMaterialFiles, setVendorMaterialFiles] = useState([]);
  const [vendorMaterialExtraction, setVendorMaterialExtraction] = useState(null);
  const [extractingVendorMaterials, setExtractingVendorMaterials] = useState(false);
  const [runningVendorMaterialAgent, setRunningVendorMaterialAgent] = useState(false);
  const [vendorMaterialFocus, setVendorMaterialFocus] = useState("");
  const [procurementFeedback, setProcurementFeedback] = useState("");
  const [legalContractFiles, setLegalContractFiles] = useState({});
  const [legalUploadFeedback, setLegalUploadFeedback] = useState({});
  const [uploadingLegalArtifactId, setUploadingLegalArtifactId] = useState("");
  const [legalArtifactPreviews, setLegalArtifactPreviews] = useState({});
  const [loadingLegalPreviewId, setLoadingLegalPreviewId] = useState("");
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
    contact_name: "",
    contact_email: "",
    contact_phone: "",
    profile_summary: "",
    procurement_notes: "",
  });
  const selectedProjectIdRef = useRef(selectedProjectId);

  useEffect(() => {
    selectedProjectIdRef.current = selectedProjectId;
  }, [selectedProjectId]);

  useEffect(() => {
    setProcurementFeedback("");
    setLegalContractFiles({});
    setLegalUploadFeedback({});
    setUploadingLegalArtifactId("");
    setLegalArtifactPreviews({});
    setLoadingLegalPreviewId("");
    setProjectDetail(null);
    setTimeline([]);
  }, [selectedProjectId]);

  useEffect(() => {
    if (selectedProjectId || !projects[0]?.id) return;
    if (currentUser.role === "business" && businessCreatingNew) return;
    const preferredProject =
      currentUser.role === "manager"
        ? [...projects].filter((item) => item.status !== "cancelled" && ["manager_review", "procurement_sourcing", "legal_review", "final_approval", "signing", "completed"].includes(item.current_stage)).sort((a, b) => {
            const aPriority = a.current_stage === "manager_review" && a.status === "active" ? 0 : 1;
            const bPriority = b.current_stage === "manager_review" && b.status === "active" ? 0 : 1;
            return aPriority - bPriority;
          })[0] || projects[0]
        : currentUser.role === "legal"
        ? [...projects]
            .filter((item) => ["legal_review", "final_approval", "signing", "completed"].includes(item.current_stage))
            .sort((a, b) => legalProjectPriority(a) - legalProjectPriority(b))[0] || projects[0]
        : currentUser.role === "admin"
          ? [...projects]
              .filter((item) => ["signing", "final_approval", "completed"].includes(item.current_stage))
              .sort((a, b) => adminProjectPriority(a) - adminProjectPriority(b))[0] || projects[0]
        : projects[0];
    setSelectedProjectId(preferredProject.id);
  }, [projects, selectedProjectId, currentUser.role, businessCreatingNew]);

  useEffect(() => {
    if (currentUser.role !== "admin" || !projects.length) return;
    const selectedProject = projects.find((item) => item.id === selectedProjectId) || null;
    const preferredAdminProject =
      [...projects]
        .filter((item) => ["signing", "final_approval", "completed"].includes(item.current_stage))
        .sort((a, b) => adminProjectPriority(a) - adminProjectPriority(b))[0] || null;
    if (!preferredAdminProject) return;
    if (!selectedProject || !["signing", "final_approval", "completed"].includes(selectedProject.current_stage)) {
      setSelectedProjectId(preferredAdminProject.id);
      return;
    }
    if (preferredAdminProject.current_stage === "signing" && selectedProject.current_stage !== "signing") {
      setSelectedProjectId(preferredAdminProject.id);
    }
  }, [projects, selectedProjectId, currentUser.role]);

  useEffect(() => {
    if (!["procurement", "legal"].includes(currentUser.role)) return;
    if (!["procurement_vendor_review", "legal_contract_review"].includes(assistantTask?.kind || "")) return;
    if (!assistantTask.projectId || assistantTask.projectId === selectedProjectId) return;
    setSelectedProjectId(assistantTask.projectId);
  }, [assistantTask?.kind, assistantTask?.projectId, currentUser.role, selectedProjectId]);

  useEffect(() => {
    if (selectedProjectId) loadProject(selectedProjectId);
  }, [selectedProjectId]);

  useEffect(() => {
    if (!projectNavigationRequest?.projectId) return;
    setBusinessCreatingNew(false);
    setManagerDialogOpen(false);
    setProjectDetail(null);
    setTimeline([]);
    setError("");
    setLoadingDetail(true);
    setActiveVendorId("");
    setSelectedProjectId(projectNavigationRequest.projectId);
  }, [projectNavigationRequest?.nonce]);

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
      setVendorMaterialExtraction(projectDetail.procurement_material_session || null);
      setVendorMaterialFocus(projectDetail.procurement_material_session?.focus_points || "");
      if (projectDetail.procurement_material_session?.vendor_draft) {
        fillVendorFormFromDraft(projectDetail.procurement_material_session.vendor_draft);
      }
    }
  }, [projectDetail?.id, projectDetail?.current_stage, projectDetail?.updated_at]);

  useEffect(() => {
    if (currentUser.role !== "procurement") return;
    if (assistantTask?.kind !== "procurement_vendor_review") return;
    if (!projectDetail || assistantTask.projectId !== projectDetail.id) return;
    fillVendorFormFromDraft(assistantTask.vendorDraft);
    if (assistantTask.linkedVendorId) setActiveVendorId(assistantTask.linkedVendorId);
  }, [assistantTask, currentUser.role, projectDetail?.id]);

  const currentTasks = useMemo(
    () => {
      if (!projectDetail) return [];
      const activeStage = projectDetail.current_stage === "final_approval" ? "signing" : projectDetail.current_stage;
      return (projectDetail.tasks || []).filter((item) => item.stage === activeStage);
    },
    [projectDetail],
  );
  const currentArtifacts = useMemo(() => {
    if (!projectDetail) return [];
    const activeStage = projectDetail.current_stage === "final_approval" ? "signing" : projectDetail.current_stage;
    return (projectDetail.artifacts || []).filter((item) => {
      if (item.stage !== activeStage) return false;
      if (activeStage !== "legal_review") return true;
      return !item.linked_vendor_id || item.linked_vendor_id === projectDetail.selected_vendor_id;
    });
  }, [projectDetail]);
  const vendors = useMemo(() => projectDetail?.vendors || [], [projectDetail]);
  const candidateVendors = useMemo(
    () =>
      vendors.filter(
        (item) =>
          item?.structured_review?.review_kind === "procurement_agent_review" &&
          ["recommend_proceed", "review_with_risks"].includes(item?.structured_review?.recommendation || item?.ai_recommendation || ""),
      ),
    [vendors],
  );
  const activeVendor = useMemo(() => vendors.find((item) => item.id === activeVendorId) || vendors[0] || null, [vendors, activeVendorId]);
  const selectedVendor = useMemo(
    () => vendors.find((item) => item.id === projectDetail?.selected_vendor_id) || null,
    [vendors, projectDetail?.selected_vendor_id],
  );
  const showLegalWorkspace = Boolean(
    projectDetail && ["legal_review", "final_approval", "signing", "completed"].includes(projectDetail.current_stage),
  );
  const legalReviewReady = Boolean(projectDetail?.legal_handoff?.ready_for_legal_review);
  const legalArtifacts = useMemo(() => {
    if (!projectDetail) return [];
    return (projectDetail.artifacts || []).filter((item) => {
      if (item.stage !== "legal_review") return false;
      return !item.linked_vendor_id || item.linked_vendor_id === projectDetail.selected_vendor_id;
    });
  }, [projectDetail]);
  const ourContractArtifact = useMemo(
    () => legalArtifacts.find((item) => item.artifact_type === "our_procurement_contract") || null,
    [legalArtifacts],
  );
  const counterpartyContractArtifact = useMemo(
    () => legalArtifacts.find((item) => item.artifact_type === "counterparty_redline_contract") || null,
    [legalArtifacts],
  );
  const activeCandidateVendor = useMemo(
    () => candidateVendors.find((item) => item.id === activeVendorId) || candidateVendors[0] || null,
    [candidateVendors, activeVendorId],
  );
  const persistedMaterialSession = useMemo(() => projectDetail?.procurement_material_session || null, [projectDetail]);
  const hasPersistedMaterials = Boolean(persistedMaterialSession?.extracted_materials?.length);

  useEffect(() => {
    if (!projectDetail?.id) return;
    const previewTargets = [ourContractArtifact, counterpartyContractArtifact].filter(
      (item) => item?.document_id && artifactIsReady(item?.status) && !legalArtifactPreviews[item.id],
    );
    if (!previewTargets.length) return;
    previewTargets.forEach((item) => {
      fetchLegalArtifactPreview(item.id);
    });
  }, [projectDetail?.id, ourContractArtifact?.document_id, counterpartyContractArtifact?.document_id]);

  function fillVendorFormFromDraft(draft) {
    setVendorForm({
      vendor_name: draft?.vendor_name || "",
      source_platform: draft?.source_platform || "",
      source_url: draft?.source_url || "",
      contact_name: draft?.contact_name || "",
      contact_email: draft?.contact_email || "",
      contact_phone: draft?.contact_phone || "",
      profile_summary: draft?.profile_summary || "",
      procurement_notes: draft?.procurement_notes || "",
    });
  }

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
    if (!projectDetail?.id) return;
    const errors = vendorFormErrorsFor(vendorForm);
    setVendorFormErrors(errors);
    if (Object.values(errors).some(Boolean)) {
      window.alert("请先补齐供应商表单中的必填信息。");
      return null;
    }
    try {
      const created = await apiPost(`/projects/${projectDetail.id}/vendors`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(vendorForm),
      });
      setActiveVendorId(created.id);
      await refreshAll({ silent: true });
      await loadProject(projectDetail.id);
      return created;
    } catch (err) {
      setError(err.message);
      return null;
    }
  }

  async function resetVendorWorkspaceAfterBind(createdVendorId = "") {
    setVendorFormErrors({});
    setVendorMaterialFiles([]);
    setVendorMaterialExtraction(null);
    setVendorMaterialFocus("");
    if (setAssistantTask) setAssistantTask(null);
    if (setAssistantResult) setAssistantResult(null);
    if (createdVendorId) setActiveVendorId(createdVendorId);
    await refreshAll({ silent: true });
    await loadProject(projectDetail.id);
  }

  async function createVendorManually(event) {
    event.preventDefault();
    const errors = vendorFormErrorsFor(vendorForm);
    setVendorFormErrors(errors);
    if (Object.values(errors).some(Boolean)) {
      window.alert("请先补齐供应商表单中的必填信息。");
      return;
    }
    try {
      const created = await createVendor(event);
      if (!created) return;
      setVendorForm({ vendor_name: "", source_platform: "", source_url: "", contact_name: "", contact_email: "", contact_phone: "", profile_summary: "", procurement_notes: "" });
      await resetVendorWorkspaceAfterBind(created.id);
    } catch (err) {
      setError(err.message);
    }
  }

  async function submitCurrentVendorToLegal() {
    if (!projectDetail?.id) return;
    try {
      setError("");
      const vendorId = activeCandidateVendor?.id || "";
      if (!vendorId) {
        window.alert("当前没有可提交给法务的候选供应商。");
        return;
      }
      const detail = await apiPost(`/projects/${projectDetail.id}/vendors/${vendorId}/select`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: "采购已确认本次候选供应商，并移交法务处理。" }),
      });
      setProcurementFeedback(`已将 ${detail.vendor_name || activeCandidateVendor?.vendor_name || "当前供应商"} 提交给法务，项目已进入法务处理阶段。`);
      await resetVendorWorkspaceAfterBind(vendorId);
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
      contact_name: vendorForm.contact_name || draftVendor.contact_name || "",
      contact_email: vendorForm.contact_email || draftVendor.contact_email || "",
      contact_phone: vendorForm.contact_phone || draftVendor.contact_phone || "",
      profile_summary: vendorForm.profile_summary || draftVendor.profile_summary || "",
      procurement_notes: vendorForm.procurement_notes || draftVendor.procurement_notes || "",
    };
    const errors = vendorFormErrorsFor(mergedVendor);
    setVendorFormErrors(errors);
    if (Object.values(errors).some(Boolean)) {
      window.alert("请先补齐供应商信息，再进入 Agent 审查。");
      return;
    }
    if (setAssistantTask) {
      setAssistantTask({
        kind: "procurement_vendor_review",
        projectId: projectDetail?.id || "",
        linkedVendorId: draftVendor.id || "",
        projectTitle: projectDetail?.title || "",
        vendorDraft: mergedVendor,
        uploadedFiles: vendorMaterialFiles,
        extractionSummary: vendorMaterialExtraction?.extraction_summary || "",
        extractedMaterials: vendorMaterialExtraction?.extracted_materials || [],
        warnings: vendorMaterialExtraction?.warnings || [],
        supplierProfile: vendorMaterialExtraction?.supplier_profile || persistedMaterialSession?.supplier_profile || null,
        materialGate: vendorMaterialExtraction?.material_gate || persistedMaterialSession?.material_gate || null,
        requirementChecks: vendorMaterialExtraction?.requirement_checks || persistedMaterialSession?.requirement_checks || [],
        supplierDossier: vendorMaterialExtraction?.supplier_dossier || persistedMaterialSession?.supplier_dossier || null,
        focusPoints: vendorMaterialFocus,
      });
    }
    if (setAssistantResult) setAssistantResult(null);
    if (setDraftQuestion) setDraftQuestion("");
    if (onNavigate) onNavigate("assistant");
  }

  function openLegalAssistant() {
    if (!projectDetail?.id) return;
    const contractsReady = artifactIsReady(ourContractArtifact?.status) && artifactIsReady(counterpartyContractArtifact?.status);
    if (!contractsReady) {
      const missingItems = [];
      if (!artifactIsReady(ourContractArtifact?.status)) missingItems.push("我方采购合同");
      if (!artifactIsReady(counterpartyContractArtifact?.status)) missingItems.push("对方修改后的采购合同");
      window.alert(`请先上传：${missingItems.join("、") || "法务合同材料"}。`);
      return;
    }
    if (setAssistantTask) {
      setAssistantTask({
        kind: "legal_contract_review",
        projectId: projectDetail.id,
        projectTitle: projectDetail.title || "",
        vendorName: selectedVendor?.vendor_name || projectDetail.vendor_name || "",
        query: reviewQuery?.trim?.() || PROJECT_REVIEW_PRESETS.legal_review,
        legalHandoff: projectDetail.legal_handoff || null,
        latestAssessment: projectDetail.latest_legal_review || null,
        autorun: true,
      });
    }
    if (setAssistantResult) setAssistantResult(null);
    if (setDraftQuestion) setDraftQuestion("");
    if (onNavigate) onNavigate("assistant");
  }

  async function extractVendorMaterials() {
    if (!projectDetail?.id) return;
    if (!vendorMaterialFiles.length) {
      if (persistedMaterialSession?.vendor_draft) {
        setVendorMaterialExtraction(persistedMaterialSession);
        fillVendorFormFromDraft(persistedMaterialSession.vendor_draft);
        return;
      }
      window.alert("请先上传供应商材料。");
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
      fillVendorFormFromDraft(payload.vendor_draft);
      setVendorFormErrors({});
      await loadProject(projectDetail.id);
    } catch (err) {
      setError(err.message);
    } finally {
      setExtractingVendorMaterials(false);
    }
  }

  async function runVendorMaterialAgent() {
    if (!projectDetail?.id) return;
    if (!vendorMaterialFiles.length) {
      if (!persistedMaterialSession?.vendor_draft) {
        window.alert("请先上传供应商材料。");
        return;
      }
      try {
        setRunningVendorMaterialAgent(true);
        setError("");
        const payload = await apiPost(`/projects/${projectDetail.id}/procurement-agent-review`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...persistedMaterialSession.vendor_draft,
            supplier_profile: persistedMaterialSession.supplier_profile,
            focus_points: vendorMaterialFocus,
            top_k: 6,
          }),
        });
        if (setAssistantTask) {
          setAssistantTask({
            kind: "procurement_vendor_review",
            projectId: projectDetail.id,
            linkedVendorId: "",
            projectTitle: projectDetail.title || "",
            vendorDraft: persistedMaterialSession.vendor_draft,
            uploadedFiles: [],
            extractionSummary: persistedMaterialSession.extraction_summary || "",
            extractedMaterials: persistedMaterialSession.extracted_materials || [],
            warnings: persistedMaterialSession.warnings || [],
            supplierProfile: persistedMaterialSession.supplier_profile || null,
            materialGate: persistedMaterialSession.material_gate || null,
            requirementChecks: persistedMaterialSession.requirement_checks || [],
            supplierDossier: persistedMaterialSession.supplier_dossier || null,
            focusPoints: vendorMaterialFocus,
          });
        }
        if (setAssistantResult) {
          setAssistantResult({
            ...payload,
            vendor_draft: persistedMaterialSession.vendor_draft,
            extraction_summary: persistedMaterialSession.extraction_summary || "",
            extracted_materials: persistedMaterialSession.extracted_materials || [],
            warnings: persistedMaterialSession.warnings || [],
            supplier_profile: persistedMaterialSession.supplier_profile || null,
            material_gate: persistedMaterialSession.material_gate || null,
            requirement_checks: persistedMaterialSession.requirement_checks || [],
            supplier_dossier: persistedMaterialSession.supplier_dossier || null,
          });
        }
        if (onTraceCreated) onTraceCreated(payload.review.trace_id);
        if (setDraftQuestion) setDraftQuestion("");
        await loadProject(projectDetail.id);
        if (onNavigate) onNavigate("assistant");
      } catch (err) {
        setError(err.message);
      } finally {
        setRunningVendorMaterialAgent(false);
      }
      return;
    }
    try {
      setRunningVendorMaterialAgent(true);
      setError("");
      const formData = new FormData();
      vendorMaterialFiles.forEach((file) => formData.append("files", file));
      formData.append("focus_points", vendorMaterialFocus);
      formData.append("top_k", "6");
      const payload = await apiPost(`/projects/${projectDetail.id}/procurement-agent-run`, {
        method: "POST",
        body: formData,
      });
      setVendorMaterialExtraction({
        extraction_summary: payload.extraction_summary,
        extracted_materials: payload.extracted_materials,
        warnings: payload.warnings,
        supplier_profile: payload.supplier_profile,
        material_gate: payload.material_gate,
        requirement_checks: payload.requirement_checks,
        supplier_dossier: payload.supplier_dossier,
      });
      fillVendorFormFromDraft(payload.vendor_draft);
      setVendorFormErrors({});
      if (setAssistantTask) {
        setAssistantTask({
          kind: "procurement_vendor_review",
          projectId: projectDetail.id,
          linkedVendorId: "",
          projectTitle: projectDetail.title || "",
          vendorDraft: payload.vendor_draft,
          uploadedFiles: vendorMaterialFiles,
          extractionSummary: payload.extraction_summary,
          extractedMaterials: payload.extracted_materials || [],
          warnings: payload.warnings || [],
          supplierProfile: payload.supplier_profile || null,
          materialGate: payload.material_gate || null,
          requirementChecks: payload.requirement_checks || [],
          supplierDossier: payload.supplier_dossier || null,
          focusPoints: vendorMaterialFocus,
        });
      }
      if (setAssistantResult) setAssistantResult(payload);
      if (onTraceCreated) onTraceCreated(payload.review.trace_id);
      if (setDraftQuestion) setDraftQuestion("");
      await loadProject(projectDetail.id);
      if (onNavigate) onNavigate("assistant");
    } catch (err) {
      setError(err.message);
    } finally {
      setRunningVendorMaterialAgent(false);
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
        body: JSON.stringify({ query: reviewQuery?.trim?.() || "", user_role: currentUser.role, top_k: 6 }),
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
        ${actions.has("submit") ? html`<button className="btn secondary" onClick=${() => runAction(`/projects/${projectDetail.id}/submit`, { reason: "" })}>提交申请表</button>` : null}
        ${actions.has("cancel") ? html`<button className="btn ghost" onClick=${() => runAction(`/projects/${projectDetail.id}/cancel`, { reason: "业务部门撤销采购申请。" })}>撤销</button>` : null}
      `;
    }
    if (projectDetail.current_stage === "manager_review") {
      return html`
        ${actions.has("manager_approve") ? html`<button className="btn primary" onClick=${() => runAction(`/projects/${projectDetail.id}/manager-decision`, { decision: "approve", reason: "" })}>通过</button>` : null}
        ${actions.has("manager_return") ? html`<button className="btn ghost" onClick=${() => runAction(`/projects/${projectDetail.id}/manager-decision`, { decision: "return", reason: "上级审核后退回业务修改。" })}>退回</button>` : null}
        ${actions.has("withdraw") ? html`<button className="btn ghost" onClick=${() => runAction(`/projects/${projectDetail.id}/withdraw`, { reason: "申请人主动撤回修改。" })}>撤回</button>` : null}
        ${actions.has("cancel") ? html`<button className="btn ghost" onClick=${() => runAction(`/projects/${projectDetail.id}/cancel`, { reason: "业务部门撤销采购申请。" })}>撤销</button>` : null}
      `;
    }
    if (projectDetail.current_stage === "procurement_sourcing") {
      return activeVendor
        ? html`
            ${actions.has("review_vendor") ? html`<button className="btn primary" onClick=${reviewVendor}>AI 审查</button>` : null}
            ${actions.has("select_vendor") ? html`<button className="btn secondary" onClick=${() => runAction(`/projects/${projectDetail.id}/vendors/${activeVendor.id}/select`, { reason: "采购完成供应商筛选并选定候选供应商。" })}>选定供应商</button>` : null}
            ${actions.has("cancel") ? html`<button className="btn ghost" onClick=${() => runAction(`/projects/${projectDetail.id}/cancel`, { reason: "采购阶段终止项目。" })}>撤销</button>` : null}
          `
        : html`<span className="muted">请先选择供应商</span>`;
    }
    if (projectDetail.current_stage === "legal_review") {
      return html`
        ${actions.has("review_legal") ? html`<button className="btn primary" onClick=${reviewLegal} disabled=${!legalReviewReady}>开始审查</button>` : null}
        ${actions.has("legal_approve") ? html`<button className="btn secondary" onClick=${() => runAction(`/projects/${projectDetail.id}/legal-decision`, { decision: "approve", reason: "法务审查通过，提交管理员签署。" })}>提交签署</button>` : null}
        ${actions.has("return_to_procurement") ? html`<button className="btn ghost" onClick=${() => runAction(`/projects/${projectDetail.id}/return-to-procurement`, { reason: "法务要求采购补充材料或重新筛选供应商。" })}>退回采购</button>` : null}
        ${actions.has("cancel") ? html`<button className="btn ghost" onClick=${() => runAction(`/projects/${projectDetail.id}/cancel`, { reason: "法务阶段终止项目。" })}>撤销</button>` : null}
      `;
    }
    if (projectDetail.current_stage === "final_approval") {
      return html`
        ${actions.has("final_approve") ? html`<button className="btn primary" onClick=${() => runAction(`/projects/${projectDetail.id}/final-approve`, { reason: "终审通过。" })}>通过</button>` : null}
        ${actions.has("final_return_legal") ? html`<button className="btn ghost" onClick=${() => runAction(`/projects/${projectDetail.id}/final-return`, { target_stage: "legal_review", reason: "终审要求法务补充说明。" })}>退回法务</button>` : null}
        ${actions.has("final_return_procurement") ? html`<button className="btn ghost" onClick=${() => runAction(`/projects/${projectDetail.id}/final-return`, { target_stage: "procurement_sourcing", reason: "终审要求采购重新准备材料。" })}>退回采购</button>` : null}
        ${actions.has("cancel") ? html`<button className="btn ghost" onClick=${() => runAction(`/projects/${projectDetail.id}/cancel`, { reason: "终审阶段终止项目。" })}>撤销</button>` : null}
      `;
    }
    if (projectDetail.current_stage === "signing") {
      return html`
        ${actions.has("sign") ? html`<button className="btn primary" onClick=${() => runAction(`/projects/${projectDetail.id}/sign`, { reason: "已完成签署归档。" })}>完成签署</button>` : null}
        ${actions.has("cancel") ? html`<button className="btn ghost" onClick=${() => runAction(`/projects/${projectDetail.id}/cancel`, { reason: "签署阶段终止项目。" })}>撤销</button>` : null}
      `;
    }
    return html`<span className="status-badge success">当前阶段正常</span>`;
  }

  function renderBusinessActions() {
    if (!projectDetail) return null;
    const actions = new Set(projectDetail.allowed_actions || []);
    return html`
      ${actions.has("submit") ? html`<button className="btn primary" type="button" onClick=${() => runAction(`/projects/${projectDetail.id}/submit`, { reason: "" })}>提交申请表</button>` : null}
      ${actions.has("withdraw") ? html`<button className="btn secondary" type="button" onClick=${() => runAction(`/projects/${projectDetail.id}/withdraw`, { reason: "申请人主动撤回修改。" })}>撤回</button>` : null}
      ${actions.has("cancel") ? html`<button className="btn ghost" type="button" onClick=${() => runAction(`/projects/${projectDetail.id}/cancel`, { reason: "业务部门撤销采购申请。" })}>撤销</button>` : null}
    `;
  }

  function renderBusinessWorkspace() {
    const currentStageIndex = projectDetail ? projectStageProgressIndex(projectDetail.current_stage) : 0;

    return html`
      <div>
        <div className="topbar">
          <div>
            <h2>业务申请工作台</h2>
            <p>业务部门负责填写采购申请表、根据系统提醒补齐信息并人工提交，不再进行大模型审查。</p>
          </div>
        </div>
        ${error ? html`<div className="error" style=${{ marginBottom: "18px" }}>${error}</div>` : null}

        <section className="section-block">
          <div className="panel business-workbench">
            <div className="section-title-row">
              <div>
                <h3>${projectDetail?.title || "新采购申请表"}</h3>
                <div className="subtle">
                  ${projectDetail
                    ? `当前状态：${stageText(projectDetail.current_stage)} / ${formatCurrency(projectDetail.budget_amount, projectDetail.currency)}`
                    : "当前是一个尚未暂存的新申请表。"}
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

            <div className="project-progress-line">
              ${PROJECT_STAGE_ORDER.map((stage, index) => html`
                <div key=${stage} className=${index <= currentStageIndex ? "progress-node active" : "progress-node"}>
                  <span>${index + 1}</span>
                  <small>${stageText(stage)}</small>
                </div>
              `)}
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
                          <div className="subtle">系统只负责检查采购申请表是否完整，并勾选需要确认的要点，最后仍由业务人工提交给上级审批。</div>
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

                        <div className="section-title-row" style=${{ marginTop: "20px" }}><h4>需求检查项</h4></div>
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
                    : html`<div className="empty-box">暂时还没有历史项目</div>`}
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
    if (!form.title?.trim()) errors.title = "请填写项目名称。";
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
    if (form.contact_email?.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.contact_email.trim())) {
      errors.contact_email = "联系人邮箱格式不正确。";
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
      window.alert("请先补齐采购申请表中的必填信息。");
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

  async function uploadLegalArtifact(artifact, fileOverride = null) {
    if (!projectDetail?.id || !artifact?.id) return;
    const file = fileOverride || legalContractFiles[artifact.id];
    if (!file) {
      window.alert("请先选择合同文件。");
      return;
    }
    if (!isSupportedLegalContractFile(file)) {
      window.alert("当前法务合同上传仅支持 .md 和 .docx 格式。");
      return;
    }
    try {
      setUploadingLegalArtifactId(artifact.id);
      setError("");
      const formData = new FormData();
      formData.append("file", file);
      const uploadedArtifact = await apiPost(`/projects/${projectDetail.id}/artifacts/${artifact.id}/upload`, {
        method: "POST",
        body: formData,
      });
      if (!artifactIsReady(uploadedArtifact?.status)) {
        throw new Error(`${projectArtifactTitle(artifact)}上传后状态未更新成功。`);
      }
      setLegalContractFiles((current) => {
        const next = { ...current };
        delete next[artifact.id];
        return next;
      });
      setLegalUploadFeedback((current) => ({
        ...current,
        [artifact.id]: `${projectArtifactTitle(artifact)}上传成功：${file.name}`,
      }));
      await refreshAll({ silent: true });
      await loadProject(projectDetail.id);
      await fetchLegalArtifactPreview(artifact.id);
      window.alert(`${projectArtifactTitle(artifact)}上传成功。`);
    } catch (err) {
      setError(err.message);
      window.alert(`上传失败：${err.message}`);
    } finally {
      setUploadingLegalArtifactId("");
    }
  }

  async function fetchLegalArtifactPreview(artifactId) {
    if (!projectDetail?.id || !artifactId) return;
    try {
      setLoadingLegalPreviewId(artifactId);
      setError("");
      const payload = await apiGet(`/projects/${projectDetail.id}/artifacts/${artifactId}/preview`);
      setLegalArtifactPreviews((current) => ({ ...current, [artifactId]: payload }));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingLegalPreviewId("");
    }
  }

  async function handleLegalContractSelection(artifact, event) {
    const file = event?.target?.files?.[0] || null;
    if (!artifact?.id || !file) return;
    setLegalContractFiles((current) => ({
      ...current,
      [artifact.id]: file,
    }));
    setLegalUploadFeedback((current) => {
      const next = { ...current };
      delete next[artifact.id];
      return next;
    });
    if (!isSupportedLegalContractFile(file)) {
      window.alert("当前法务合同上传仅支持 .md 和 .docx 格式。");
      setLegalContractFiles((current) => {
        const next = { ...current };
        delete next[artifact.id];
        return next;
      });
      if (event?.target) event.target.value = "";
      return;
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
            ${renderBusinessField({ form, errors, field: "title", label: "项目名称", placeholder: "例如：客服工单协同工具采购" })}
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
          <div className="subtle">${editable ? "暂存前系统会先校验字段，确认后再由业务人工提交给上级审批。" : "业务已进入当前阶段，可继续查看历史记录与项目状态。"}</div>
          <div className="button-row">
            ${editable ? html`<button className="btn secondary" type="submit">暂存</button>` : null}
            ${editable ? html`<button className="btn primary" type="button" onClick=${submitBusinessApplication}>提交上级审批</button>` : null}
            ${actions.has("withdraw") ? html`<button className="btn secondary" type="button" onClick=${() => runAction(`/projects/${projectDetail.id}/withdraw`, { reason: "业务需要继续修改申请表。" })}>撤回修改</button>` : null}
            ${actions.has("cancel") ? html`<button className="btn ghost" type="button" onClick=${() => runAction(`/projects/${projectDetail.id}/cancel`, { reason: "业务确认取消当前采购申请。" })}>取消项目</button>` : null}
          </div>
        </div>
      </form>
    `;
  }

  function renderBusinessWorkspaceV2() {
    const currentStageIndex = projectDetail ? projectStageProgressIndex(projectDetail.current_stage) : 0;

    return html`
      <div>
        <div className="topbar">
          <div>
            <h2>业务审核</h2>
            <p>先暂存采购申请表，确认信息完整后再提交到上级审批。</p>
          </div>
        </div>
        ${error ? html`<div className="error" style=${{ marginBottom: "18px" }}>${error}</div>` : null}

        <section className="section-block">
          <div className="panel business-workbench">
            <div className="section-title-row">
              <div>
                <h3>${projectDetail?.title || "²ɹ"}</h3>
                <div className="subtle">
                  ${projectDetail ? `当前状态：${stageText(projectDetail.current_stage)} / ${formatCurrency(projectDetail.budget_amount, projectDetail.currency)}` : "当前是尚未暂存的新申请表"}
                </div>
              </div>
              <div className="business-toolbar">
                <button className="btn ghost" type="button" onClick=${resetBusinessApplicationForm}>新建空白表</button>
                <button className="btn secondary" type="button" onClick=${() => setBusinessDialog("history")}>历史项目列表</button>
              </div>
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

        <section className="section-block">
          <div className="panel business-form-panel">
            <div className="section-title-row">
              <div>
                <h3>采购申</h3>
                <div className="subtle">空白或不符合要求的字段会标红；提交时如果仍有错，系统会弹窗提醒重新塆</div>
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
                    <h3>鍘嗗彶椤圭洰鍒楄〃</h3>
                    <button className="btn ghost small" type="button" onClick=${() => setBusinessDialog("")}>鍏抽棴</button>
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
                    : html`<div className="empty-box">暂时还没有历史项</div>`}
                </div>
              </div>
            `
          : null}
      </div>
    `;
  }

  function openManagerProject(projectId) {
    setSelectedProjectId(projectId);
    setManagerDialogOpen(false);
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
                  <strong>法务结摘</strong>
                  <div className="subtle">${projectDetail.latest_legal_review.summary || projectDetail.latest_legal_review.conclusion || "暂无摘"}</div>
                </div>
              `
            : null}

          ${projectDetail.blocker_summary?.length
            ? html`
                <div className="stack-list">
                  ${projectDetail.blocker_summary.map((item) => html`<div className="inline-alert warn" key=${item}>${item}</div>`)}
                </div>
              `
            : html`<div className="empty-box compact">当前没有阻项</div>`}

          <div className="section-title-row">
            <h4>瀹℃壒鍔ㄤ綔</h4>
            <div className="button-row">${renderStageActions()}</div>
          </div>

          <div className="manager-section-grid">
            <div>
              <div className="section-title-row"><h4>褰撳墠浠诲姟</h4></div>
              ${currentTasks.length
                ? html`<div className="stack-list">${currentTasks.map((item) => html`<div className="activity-item" key=${item.id}><div className="activity-main"><strong>${item.title}</strong><div className="subtle">${item.details}</div></div><div className="activity-meta"><span className="status-badge ${toneOf(item.status)}">${displayLabel(item.status)}</span></div></div>`)}</div>`
                : html`<div className="empty-box compact">当前阶没有额任务</div>`}
            </div>
            <div>
              <div className="section-title-row"><h4>褰撳墠鏉愭枡</h4></div>
              ${currentArtifacts.length
                ? html`<div className="stack-list">${currentArtifacts.map((item) => html`<div className="activity-item" key=${item.id}><div className="activity-main"><strong>${item.title}</strong><div className="subtle">${item.description}</div></div><div className="activity-meta"><span className="status-badge ${toneOf(item.status)}">${displayLabel(item.status)}</span></div></div>`)}</div>`
                : html`<div className="empty-box compact">当前阶没有额材料</div>`}
            </div>
          </div>
        </div>
      </div>
    `;
  }

  function renderManagerWorkspace() {
    const actions = new Set(projectDetail?.allowed_actions || []);
    const currentStageIndex = projectDetail ? projectStageProgressIndex(projectDetail.current_stage) : 0;
    const visibleProjects = projects.filter((item) => item.status !== "cancelled");
    const pendingProjects = visibleProjects.filter((item) => item.status === "active" && item.current_stage === "manager_review");
    const approvedProjects = visibleProjects.filter((item) =>
      ["procurement_sourcing", "legal_review", "final_approval", "signing", "completed"].includes(item.current_stage),
    );

    return html`
      <div>
        <div className="topbar">
          <div>
            <h2>审批工作台</h2>
            <p>上级只需要看申请信息，做简单审批，然后把项目交给采购继续推进。</p>
          </div>
        </div>
        ${error ? html`<div className="error" style=${{ marginBottom: "18px" }}>${error}</div>` : null}

        <section className="section-block">
          <div className="projects-layout">
            <section className="panel">
              <div className="section-title-row">
                <h3>1. 待我审批</h3>
                <div className="subtle">${pendingProjects.length} 个项目</div>
              </div>
              ${pendingProjects.length
                ? html`
                    <div className="stack-list">
                      ${pendingProjects.map((item) => html`
                        <button key=${item.id} className=${selectedProjectId === item.id ? "project-list-item active" : "project-list-item"} onClick=${() => openManagerProject(item.id)}>
                          <div className="activity-main">
                            <strong>${item.title}</strong>
                            <div className="subtle">${item.department || "未标记部门"} / ${formatCurrency(item.budget_amount, item.currency)} / ${stageText(item.current_stage)}</div>
                          </div>
                          <div className="activity-meta">
                            <span className="status-badge ${toneOf(item.status)}">${displayLabel(item.status)}</span>
                          </div>
                        </button>
                      `)}
                    </div>
                  `
                : html`<div className="empty-box">当前没有待审批项目。</div>`}
            </section>

            <section className="panel">
              <div className="section-title-row">
                <h3>2. 已批准并交给采购</h3>
                <div className="subtle">${approvedProjects.length} 个项目</div>
              </div>
              ${approvedProjects.length
                ? html`
                    <div className="stack-list">
                      ${approvedProjects.map((item) => html`
                        <button key=${item.id} className=${selectedProjectId === item.id ? "project-list-item active" : "project-list-item"} onClick=${() => openManagerProject(item.id)}>
                          <div className="activity-main">
                            <strong>${item.title}</strong>
                            <div className="subtle">${item.department || "未标记部门"} / ${item.vendor_name || "待确认供应商"} / ${stageText(item.current_stage)}</div>
                          </div>
                          <div className="activity-meta">
                            <span className="status-badge ${toneOf(item.status)}">${displayLabel(item.status)}</span>
                          </div>
                        </button>
                      `)}
                    </div>
                  `
                : html`<div className="empty-box">当前还没有已批准并进入采购流转的项目。</div>`}
            </section>
          </div>
        </section>

        ${selectedProjectId && projectDetail
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

              <div className="projects-layout wide procurement-layout">
                <section className="panel">
                  <div className="info-box">
                    <strong>申请摘要</strong>
                    <div className="stack-list" style=${{ marginTop: "10px" }}>
                      <div className="subtle">发起人：${projectDetail.requester_name || "-"}</div>
                      <div className="subtle">所属部门：${projectDetail.department || "-"}</div>
                      <div className="subtle">意向供应商：${projectDetail.vendor_name || "待确定供应商"}</div>
                    </div>
                  </div>

                  <div className="info-box" style=${{ marginTop: "18px" }}>
                    <strong>采购目的</strong>
                    <div className="subtle" style=${{ marginTop: "10px" }}>${projectDetail.summary || "未填写"}</div>
                  </div>

                  <div className="info-box" style=${{ marginTop: "18px" }}>
                    <strong>业务价值</strong>
                    <div className="subtle" style=${{ marginTop: "10px" }}>${projectDetail.business_value || "未填写"}</div>
                  </div>

                  <div className="info-box" style=${{ marginTop: "18px" }}>
                    <strong>审批动作</strong>
                    <div className="button-row" style=${{ marginTop: "10px" }}>
                      ${actions.has("manager_approve") ? html`<button className="btn primary" onClick=${() => runAction(`/projects/${projectDetail.id}/manager-decision`, { decision: "approve", reason: "上级审批通过。" })}>通过</button>` : null}
                      ${actions.has("manager_return") ? html`<button className="btn ghost" onClick=${() => runAction(`/projects/${projectDetail.id}/manager-decision`, { decision: "return", reason: "请补充采购申请信息后重新提交。" })}>退回业务</button>` : null}
                      ${actions.has("cancel") ? html`<button className="btn ghost" onClick=${() => runAction(`/projects/${projectDetail.id}/cancel`, { reason: "上级审批阶段终止项目。" })}>撤销</button>` : null}
                    </div>
                  </div>
                </section>

                <section className="panel">
                  <div className="section-title-row">
                    <h3>审批提醒</h3>
                  </div>
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
                    : html`<div className="empty-box">当前还没有可展示的审批检查项。</div>`}

                  <div className="section-title-row" style=${{ marginTop: "20px" }}>
                    <h3>阻塞提醒</h3>
                  </div>
                  ${projectDetail.blocker_summary?.length
                    ? html`<div className="stack-list">${projectDetail.blocker_summary.map((item) => html`<div className="inline-alert warn" key=${item}>${item}</div>`)}</div>`
                    : html`<div className="empty-box compact">当前没有阻塞项。</div>`}

                  ${projectDetail.latest_legal_review
                    ? html`
                        <div className="section-title-row" style=${{ marginTop: "20px" }}>
                          <h3>后续法务结论</h3>
                        </div>
                        <${ReviewSummaryCard} html=${html} title="法务结构化审查" review=${projectDetail.latest_legal_review} />
                      `
                    : null}
                </section>
              </div>
            `
          : null}
      </div>
    `;
  }

  function renderAdminWorkspace() {
    const actions = new Set(projectDetail?.allowed_actions || []);
    const currentStageIndex = projectDetail ? projectStageProgressIndex(projectDetail.current_stage) : 0;
    const adminProjects = [...projects]
      .filter((item) => ["signing", "completed", "final_approval"].includes(item.current_stage))
      .sort((a, b) => adminProjectPriority(a) - adminProjectPriority(b));
    const signingProjects = adminProjects.filter((item) => ["signing", "final_approval"].includes(item.current_stage) && item.status === "active");
    const latestLegalReview = projectDetail?.latest_legal_review || null;
    const signingBlockers =
      projectDetail?.current_stage === "signing" || projectDetail?.current_stage === "final_approval"
        ? [
            ...currentTasks.filter((item) => item.status !== "done").map((item) => `Task pending: ${item.title}`),
            ...currentArtifacts
              .filter((item) => !["provided", "approved"].includes(item.status))
              .map((item) => `Artifact missing: ${projectArtifactTitle(item)}`),
          ]
        : [];
    const canCompleteSigning = actions.has("sign") && signingBlockers.length === 0;

    return html`
      <div>
        <div className="topbar">
          <div>
            <h2>签署归档工作台</h2>
            <p>管理员只处理最后一步：查看法务结论，确认签署，并完成归档。</p>
          </div>
        </div>
        ${error ? html`<div className="error" style=${{ marginBottom: "18px" }}>${error}</div>` : null}

        <section className="section-block">
          <div className="projects-layout">
            <section className="panel">
              <div className="section-title-row">
                <h3>1. 待签署项目</h3>
                <div className="subtle">${signingProjects.length} 个项目</div>
              </div>
              ${signingProjects.length
                ? html`
                    <div className="stack-list">
                      ${signingProjects.map((item) => html`
                        <button key=${item.id} className=${selectedProjectId === item.id ? "project-list-item active" : "project-list-item"} onClick=${() => setSelectedProjectId(item.id)}>
                          <div className="activity-main">
                            <strong>${item.title}</strong>
                            <div className="subtle">${item.vendor_name || "待确认供应商"} / ${formatCurrency(item.budget_amount, item.currency)}</div>
                          </div>
                          <div className="activity-meta">
                            <span className="status-badge ${toneOf(item.status)}">${displayLabel(item.status)}</span>
                          </div>
                        </button>
                      `)}
                    </div>
                  `
                : html`<div className="empty-box">当前没有待管理员签署的项目。</div>`}
            </section>

            <section className="panel">
              <div className="section-title-row">
                <h3>2. 已完成记录</h3>
                <div className="subtle">${adminProjects.filter((item) => item.current_stage === "completed").length} 个项目</div>
              </div>
              ${adminProjects.filter((item) => item.current_stage === "completed").length
                ? html`
                    <div className="stack-list">
                      ${adminProjects.filter((item) => item.current_stage === "completed").map((item) => html`
                        <button key=${item.id} className=${selectedProjectId === item.id ? "project-list-item active" : "project-list-item"} onClick=${() => setSelectedProjectId(item.id)}>
                          <div className="activity-main">
                            <strong>${item.title}</strong>
                            <div className="subtle">${item.vendor_name || "已签署供应商"} / ${stageText(item.current_stage)}</div>
                          </div>
                          <div className="activity-meta">
                            <span className="status-badge ${toneOf(item.status)}">${displayLabel(item.status)}</span>
                          </div>
                        </button>
                      `)}
                    </div>
                  `
                : html`<div className="empty-box">当前还没有已完成签署的项目。</div>`}
            </section>
          </div>
        </section>

        ${selectedProjectId && projectDetail
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

              <div className="projects-layout wide procurement-layout">
                <section className="panel">
                  ${projectDetail.current_stage === "final_approval"
                    ? html`
                        <div className="project-blocker-banner" style=${{ marginBottom: "16px" }}>
                          <strong>这是旧流程项目</strong>
                          <div className="subtle" style=${{ marginTop: "6px" }}>系统已按“签署归档”方式兼容处理。先补齐下面的签署待办和材料，随后即可由管理员直接完成签署。</div>
                        </div>
                      `
                    : null}
                  <div className="info-box">
                    <strong>签署信息</strong>
                    <div className="stack-list" style=${{ marginTop: "10px" }}>
                      <div className="subtle">目标供应商：${projectDetail.vendor_name || "-"}</div>
                      <div className="subtle">申请部门：${projectDetail.department || "-"}</div>
                      <div className="subtle">申请人：${projectDetail.requester_name || "-"}</div>
                    </div>
                  </div>

                  <div className="info-box" style=${{ marginTop: "18px" }}>
                    <strong>管理员动作</strong>
                    <div className="button-row" style=${{ marginTop: "10px" }}>
                      <button className="btn primary" type="button" onClick=${() => runAction(`/projects/${projectDetail.id}/sign`, { reason: "管理员完成签署归档。" })} disabled=${!canCompleteSigning}>
                        完成签署
                      </button>
                      ${actions.has("cancel")
                        ? html`<button className="btn ghost" type="button" onClick=${() => runAction(`/projects/${projectDetail.id}/cancel`, { reason: "管理员终止签署归档。" })}>撤销</button>`
                        : null}
                    </div>
                    ${projectDetail.current_stage === "signing"
                      ? signingBlockers.length
                        ? html`
                            <div className="stack-list" style=${{ marginTop: "12px" }}>
                              <div className="inline-alert warn">完成签署前，请先把下面这些待办和材料补齐。</div>
                              ${signingBlockers.map((item) => html`<div className="inline-alert warn" key=${item}>${item}</div>`)}
                            </div>
                          `
                        : html`<div className="inline-alert success" style=${{ marginTop: "12px" }}>签署待办已齐备，现在可以完成签署。</div>`
                      : null}
                  </div>

                  ${currentTasks.length
                    ? html`
                        <div className="section-title-row" style=${{ marginTop: "20px" }}><h4>签署待办</h4></div>
                        <div className="stack-list">
                          ${currentTasks.map((task) => html`
                            <div className="activity-item" key=${task.id}>
                              <div className="activity-main">
                                <strong>${task.title}</strong>
                                <div className="subtle">${displayLabel(task.assignee_role)} / ${task.task_type}</div>
                              </div>
                              <div className="activity-meta">
                                <span className="status-badge ${toneOf(task.status)}">${displayLabel(task.status)}</span>
                                ${task.status !== "done" && projectDetail.status === "active"
                                  ? html`<button className="btn ghost small" onClick=${() => markTaskDone(task.id)}>标记完成</button>`
                                  : null}
                              </div>
                            </div>
                          `)}
                        </div>
                      `
                    : null}

                  ${currentArtifacts.length
                    ? html`
                        <div className="section-title-row" style=${{ marginTop: "20px" }}><h4>签署材料</h4></div>
                        <div className="stack-list">
                          ${currentArtifacts.map((artifact) => html`
                            <div className="activity-item" key=${artifact.id}>
                              <div className="activity-main">
                                <strong>${projectArtifactTitle(artifact)}</strong>
                                <div className="subtle">${displayLabel(artifact.direction)} / ${displayLabel(artifact.status)}</div>
                                ${artifact.notes ? html`<div className="subtle">${artifact.notes}</div>` : null}
                              </div>
                              <div className="activity-meta">
                                <span className="status-badge ${toneOf(artifact.status)}">${displayLabel(artifact.status)}</span>
                                ${!["provided", "approved"].includes(artifact.status) && projectDetail.status === "active"
                                  ? html`<button className="btn ghost small" onClick=${() => markArtifactProvided(artifact.id)}>${projectArtifactActionLabel(artifact)}</button>`
                                  : null}
                              </div>
                            </div>
                          `)}
                        </div>
                      `
                    : null}
                </section>

                <section className="panel">
                  <div className="section-title-row">
                    <h3>法务结论</h3>
                  </div>
                  <${ReviewSummaryCard} html=${html} title="最近一次法务结构化审查" review=${latestLegalReview} />

                  ${timeline.length
                    ? html`
                        <div className="section-title-row" style=${{ marginTop: "20px" }}><h4>最近流转记录</h4></div>
                        <div className="timeline-list">
                          ${timeline.slice(0, 6).map((event) => html`
                            <article className="timeline-card" key=${`${event.kind}-${event.created_at}-${event.title}`}>
                              <div className="timeline-badge neutral">${event.kind}</div>
                              <div className="timeline-body">
                                <strong>${event.title}</strong>
                                <div className="subtle">${stageText(event.stage)} / ${event.created_at}</div>
                                <p>${event.summary}</p>
                              </div>
                            </article>
                          `)}
                        </div>
                      `
                    : html`<div className="empty-box" style=${{ marginTop: "20px" }}>当前还没有可展示的流转记录。</div>`}
                </section>
              </div>
            `
          : null}
      </div>
    `;
  }

  function renderProcurementWorkspace() {
    const actions = new Set(projectDetail?.allowed_actions || []);
    const currentStageIndex = projectDetail ? projectStageProgressIndex(projectDetail.current_stage) : 0;
    const vendorErrors = vendorFormErrorsFor(vendorForm);
    const procurementAssistantAssessment =
      assistantTask?.kind === "procurement_vendor_review" && assistantTask?.projectId === projectDetail?.id
        ? assistantResult?.assessment || null
        : null;
    const procurementAssistantReview = procurementAssistantAssessment ? assistantResult?.review || null : null;
    const procurementAssistantGate =
      assistantTask?.kind === "procurement_vendor_review" && assistantTask?.projectId === projectDetail?.id
        ? assistantResult?.material_gate || persistedMaterialSession?.material_gate || null
        : persistedMaterialSession?.material_gate || null;
    const procurementRequirementChecks =
      assistantTask?.kind === "procurement_vendor_review" && assistantTask?.projectId === projectDetail?.id
        ? assistantResult?.requirement_checks || persistedMaterialSession?.requirement_checks || []
        : persistedMaterialSession?.requirement_checks || [];
    const procurementBlockingReasons = procurementAssistantGate?.blocking_reasons || [];
    const procurementMissingMaterials = procurementRequirementChecks.filter((item) => item.required && item.status !== "pass");
    const hasAssistantDecision = Boolean(procurementAssistantAssessment || activeVendor?.structured_review);
    const canSubmitToLegal =
      projectDetail?.current_stage === "procurement_sourcing" &&
      actions.has("select_vendor") &&
      !["legal_rejected", "rejected"].includes(activeCandidateVendor?.status || "") &&
      hasAssistantDecision &&
      procurementAssistantGate?.decision === "pass" &&
      !["reject_irrelevant_materials", "needs_required_materials"].includes(procurementAssistantAssessment?.recommendation || "") &&
      Boolean(activeCandidateVendor?.id);
    const uploadStatusText = vendorMaterialExtraction?.extracted_materials?.length
      ? `已成功上传 ${vendorMaterialExtraction.extracted_materials.length} 份材料。`
      : hasPersistedMaterials
        ? `已保存 ${persistedMaterialSession.extracted_materials.length} 份材料，可继续使用。`
        : "";

    return html`
      <div>
        <div className="topbar">
          <div>
            <h2>采购执行工作台</h2>
            <p>采购只需要上传材料并点击一次确认按钮，系统会自动解析供应商信息、跳转审查助手并返回审查结果。</p>
          </div>
        </div>
        ${error ? html`<div className="error" style=${{ marginBottom: "18px" }}>${error}</div>` : null}
        ${procurementFeedback ? html`<div className="project-blocker-banner success" style=${{ marginBottom: "18px" }}><strong>${procurementFeedback}</strong></div>` : null}

        ${selectedProjectId && projectDetail
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
          : html`
              <section className="section-block">
                <div className="panel">
                  <div className="empty-box">从上方选择一个项目后，这里会显示当前项目的采购处理区。</div>
                </div>
              </section>
            `}

        ${selectedProjectId && projectDetail ? html`<div className="projects-layout wide procurement-layout">
          <section className="panel">
            ${loadingDetail
              ? html`<div className="center-panel" style=${{ minHeight: "220px" }}><div className="loading-ring"></div></div>`
              : projectDetail
                ? html`
                    ${projectDetail.current_stage === "legal_review" || projectDetail.current_stage === "final_approval" || projectDetail.current_stage === "signing" || projectDetail.current_stage === "completed"
                      ? html`
                          <div className="project-blocker-banner success" style=${{ marginBottom: "16px" }}>
                            <strong>采购已通过，当前项目处于：${stageText(projectDetail.current_stage)}</strong>
                            <div className="subtle" style=${{ marginTop: "6px" }}>
                              当前供应商：${projectDetail.vendor_name || "未选择"}。你可以继续查看时间线、法务结论和项目记录。
                            </div>
                          </div>
                        `
                      : null}
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
                          <div className="procurement-workbench-grid" style=${{ marginTop: "20px" }}>
                            <div className="panel procurement-upload-panel">
                              <div className="section-title-row">
                                <div>
                                  <h4>1. 上传供应商材料</h4>
                                  <div className="subtle">这里负责上传材料；上传成功后，系统会自动把解析出的供应商信息填到右侧区域。</div>
                                </div>
                              </div>
                              <div className="stack-list" style=${{ marginTop: "16px" }}>
                                ${uploadStatusText
                                  ? html`<div className="inline-alert info">${uploadStatusText}</div>`
                                  : null}
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
                                  <button className="btn primary" type="button" onClick=${runVendorMaterialAgent} disabled=${runningVendorMaterialAgent || (!vendorMaterialFiles.length && !hasPersistedMaterials)}>
                                    ${runningVendorMaterialAgent ? "系统处理中..." : vendorMaterialFiles.length ? "确认上传并解析" : "使用已保存材料继续解析"}
                                  </button>
                                </div>
                              </div>
                            </div>

                            <div className="panel procurement-form-panel">
                              <div className="section-title-row">
                                <div>
                                  <h4>2. 供应商基本信息</h4>
                                  <div className="subtle">系统会自动把材料解析成供应商基础资料，这里作为主要信息区展示给采购核对。</div>
                                </div>
                              </div>
                              <div className="business-form" style=${{ marginTop: "16px" }}>
                                <div className="business-form-grid">
                                  <label className="business-form-field">
                                    <span className="business-form-label">供应商名称</span>
                                    <input className=${vendorErrors.vendor_name || vendorFormErrors.vendor_name ? "field error" : "field"} placeholder="填写供应商名称" value=${vendorForm.vendor_name} onInput=${(e) => updateVendorField("vendor_name", e.target.value)} />
                                    ${(vendorErrors.vendor_name || vendorFormErrors.vendor_name) ? html`<small className="field-error-text">${vendorErrors.vendor_name || vendorFormErrors.vendor_name}</small>` : null}
                                  </label>
                                  <label className="business-form-field">
                                    <span className="business-form-label">来源平台</span>
                                    <input className=${vendorErrors.source_platform || vendorFormErrors.source_platform ? "field error" : "field"} placeholder="例如：官网 / 1688 / 招投标平台" value=${vendorForm.source_platform} onInput=${(e) => updateVendorField("source_platform", e.target.value)} />
                                    ${(vendorErrors.source_platform || vendorFormErrors.source_platform) ? html`<small className="field-error-text">${vendorErrors.source_platform || vendorFormErrors.source_platform}</small>` : null}
                                  </label>
                                  <label className="business-form-field full">
                                    <span className="business-form-label">来源链接</span>
                                    <input className=${vendorErrors.source_url || vendorFormErrors.source_url ? "field error" : "field"} placeholder="选填，建议填写官网或公开来源链接" value=${vendorForm.source_url} onInput=${(e) => updateVendorField("source_url", e.target.value)} />
                                    ${(vendorErrors.source_url || vendorFormErrors.source_url) ? html`<small className="field-error-text">${vendorErrors.source_url || vendorFormErrors.source_url}</small>` : null}
                                  </label>
                                  <label className="business-form-field">
                                    <span className="business-form-label">联系人</span>
                                    <input className="field" placeholder="例如：张三" value=${vendorForm.contact_name} onInput=${(e) => updateVendorField("contact_name", e.target.value)} />
                                  </label>
                                  <label className="business-form-field">
                                    <span className="business-form-label">联系邮箱</span>
                                    <input className=${vendorErrors.contact_email || vendorFormErrors.contact_email ? "field error" : "field"} placeholder="例如：vendor@example.com" value=${vendorForm.contact_email} onInput=${(e) => updateVendorField("contact_email", e.target.value)} />
                                    ${(vendorErrors.contact_email || vendorFormErrors.contact_email) ? html`<small className="field-error-text">${vendorErrors.contact_email || vendorFormErrors.contact_email}</small>` : null}
                                  </label>
                                  <label className="business-form-field full">
                                    <span className="business-form-label">联系电话</span>
                                    <input className="field" placeholder="例如：13800000000 / 400-800-9000" value=${vendorForm.contact_phone} onInput=${(e) => updateVendorField("contact_phone", e.target.value)} />
                                  </label>
                                  <label className="business-form-field full">
                                    <span className="business-form-label">供应商简介</span>
                                    <textarea className=${vendorErrors.profile_summary || vendorFormErrors.profile_summary ? "field error textarea-medium" : "field textarea-medium"} placeholder="说明公司背景、产品范围和关键能力" value=${vendorForm.profile_summary} onInput=${(e) => updateVendorField("profile_summary", e.target.value)}></textarea>
                                    ${(vendorErrors.profile_summary || vendorFormErrors.profile_summary) ? html`<small className="field-error-text">${vendorErrors.profile_summary || vendorFormErrors.profile_summary}</small>` : null}
                                  </label>
                                  <label className="business-form-field full">
                                    <span className="business-form-label">采购说明</span>
                                    <textarea className=${vendorErrors.procurement_notes || vendorFormErrors.procurement_notes ? "field error textarea-medium" : "field textarea-medium"} placeholder="填写采购原因、使用场景，以及为什么考虑这家供应商" value=${vendorForm.procurement_notes} onInput=${(e) => updateVendorField("procurement_notes", e.target.value)}></textarea>
                                    ${(vendorErrors.procurement_notes || vendorFormErrors.procurement_notes) ? html`<small className="field-error-text">${vendorErrors.procurement_notes || vendorFormErrors.procurement_notes}</small>` : null}
                                  </label>
                                </div>
                                <div className="split-fields">
                                  <div className="subtle">上传后系统会自动填充这里的内容，并在下一步给出审查助手判断。</div>
                                  <div className="subtle">${activeVendor?.id ? `当前已绑定供应商：${activeVendor.vendor_name || "-"}` : "当前还没有手动绑定供应商，首次通过审查后会自动绑定。"}</div>
                                </div>
                              </div>
                            </div>
                          </div>
                        `
                      : null}
                `
                : html`<div className="empty-box">请选择一个采购项目</div>`}
          </section>

          <section className="panel">
            <div className="section-title-row">
              <h3>3. 最终确认</h3>
            </div>
            ${projectDetail
              ? html`
                  <div className="stack-list">
                    ${candidateVendors.length
                      ? html`
                          <div className="stack-list">
                            ${candidateVendors.map((vendor) => html`
                              <button key=${vendor.id} className=${activeCandidateVendor?.id === vendor.id ? "project-list-item active" : "project-list-item"} onClick=${() => setActiveVendorId(vendor.id)}>
                                <div className="activity-main">
                                  <strong>${vendor.vendor_name}</strong>
                                  <div className="subtle">${vendor.source_platform || "手工录入"} / ${vendor.profile_summary || "暂无简介"}</div>
                                </div>
                                <div className="activity-meta">
                                  <span className="status-badge ${toneOf(vendor.status)}">${displayLabel(vendor.status)}</span>
                                </div>
                              </button>
                            `)}
                          </div>
                        `
                      : html`<div className="empty-box">当前还没有通过基础审查的候选供应商。先上传材料并完成自动审查。</div>`}

                    <div className="info-box">
                      <strong>${activeCandidateVendor ? "当前候选供应商" : "系统解析草稿"}</strong>
                      <div className="stack-list" style=${{ marginTop: "10px" }}>
                        <div className="subtle">供应商：${activeCandidateVendor?.vendor_name || vendorForm.vendor_name || "-"}</div>
                        <div className="subtle">来源：${activeCandidateVendor?.source_platform || vendorForm.source_platform || "-"} ${(activeCandidateVendor?.source_url || vendorForm.source_url) ? `/ ${activeCandidateVendor?.source_url || vendorForm.source_url}` : ""}</div>
                        <div className="subtle">联系人：${activeCandidateVendor?.contact_name || vendorForm.contact_name || "-"}</div>
                        <div className="subtle">联系邮箱：${activeCandidateVendor?.contact_email || vendorForm.contact_email || "-"}</div>
                        <div className="subtle">联系电话：${activeCandidateVendor?.contact_phone || vendorForm.contact_phone || "-"}</div>
                        <div className="subtle">简介：${activeCandidateVendor?.profile_summary || vendorForm.profile_summary || "暂无"}</div>
                        <div className="subtle">采购说明：${activeCandidateVendor?.procurement_notes || vendorForm.procurement_notes || "暂无说明"}</div>
                      </div>
                    </div>

                    <div className="info-box">
                      <strong>审查助手判断</strong>
                      ${procurementAssistantAssessment
                        ? html`
                            <div className="stack-list" style=${{ marginTop: "10px" }}>
                              <div className="button-row">
                                <span className="status-badge ${toneOf(procurementAssistantAssessment.recommendation)}">${displayLabel(procurementAssistantAssessment.recommendation)}</span>
                                ${procurementAssistantAssessment.legal_handoff_recommendation
                                  ? html`<span className="status-badge ${toneOf(procurementAssistantAssessment.legal_handoff_recommendation)}">${displayLabel(procurementAssistantAssessment.legal_handoff_recommendation)}</span>`
                                  : null}
                              </div>
                              <div className="subtle">${procurementAssistantAssessment.conclusion || procurementAssistantAssessment.summary}</div>
                              ${procurementBlockingReasons.length
                                ? html`
                                    <div className="stack-list">
                                      ${procurementBlockingReasons.map((item) => html`<div className="inline-alert danger" key=${item}>${item}</div>`)}
                                    </div>
                                  `
                                : null}
                              ${procurementMissingMaterials.length
                                ? html`
                                    <div className="stack-list">
                                      ${procurementMissingMaterials.slice(0, 4).map((item) => html`<div className="inline-alert warn" key=${item.key}>待补材料：${item.label}</div>`)}
                                    </div>
                                  `
                                : null}
                              ${procurementAssistantReview?.trace_id
                                ? html`<div className="subtle">最近一次审查 Trace：${procurementAssistantReview.trace_id.slice(0, 8)}</div>`
                                : null}
                            </div>
                          `
                        : html`<div className="subtle" style=${{ marginTop: "10px" }}>先去审查助手完成一次判断，再由采购决定是否上传给法务。</div>`}
                    </div>

                    <div className="button-row">
                      <button className="btn secondary" type="button" onClick=${openProcurementAssistant} disabled=${!projectDetail}>
                        前往审查助手
                      </button>
                      <button
                        className="btn primary"
                        type="button"
                        onClick=${submitCurrentVendorToLegal}
                        disabled=${!canSubmitToLegal}
                      >
                        确认并上传给法务
                      </button>
                    </div>
                  </div>
                `
              : html`<div className="empty-box">请选择一个采购项目</div>`}
          </section>
        </div>` : null}
      </div>
    `;
  }

  function renderLegalWorkspace() {
    const actions = new Set(projectDetail?.allowed_actions || []);
    const currentStageIndex = projectDetail ? projectStageProgressIndex(projectDetail.current_stage) : 0;
    const legalProjects = [...projects]
      .filter((item) => ["legal_review", "final_approval", "signing", "completed"].includes(item.current_stage))
      .sort((a, b) => legalProjectPriority(a) - legalProjectPriority(b));
    const legalAssistantAssessment =
      assistantTask?.kind === "legal_contract_review" && assistantTask?.projectId === projectDetail?.id
        ? assistantResult?.assessment || assistantTask?.latestAssessment || null
        : projectDetail?.latest_legal_review || null;
    const legalAssistantReview =
      assistantTask?.kind === "legal_contract_review" && assistantTask?.projectId === projectDetail?.id
        ? assistantResult?.review || null
        : null;
    const contractsReady = artifactIsReady(ourContractArtifact?.status) && artifactIsReady(counterpartyContractArtifact?.status);
    const readyForAssistant = legalReviewReady || contractsReady;
    const legalBlockers = projectDetail?.blocker_summary || [];
    const canEditLegalContracts = projectDetail?.current_stage === "legal_review" && projectDetail?.status === "active";

    return html`
      <div>
          <div className="topbar">
            <div>
              <h2>法务审核工作台</h2>
              <p>法务页面保持和采购类似的简洁流程：先上传两份采购合同，再点击“审查合同”，系统会自动跳转并直接给出审查结果。</p>
            </div>
          </div>
        ${error ? html`<div className="error" style=${{ marginBottom: "18px" }}>${error}</div>` : null}

        <section className="section-block">
          <div className="panel">
            <div className="section-title-row">
              <h3>法务项目</h3>
              <div className="subtle">${legalProjects.length} 个项目</div>
            </div>
            ${legalProjects.length
              ? html`
                  <div className="stack-list">
                    ${legalProjects.map((item) => html`
                      <button key=${item.id} className=${selectedProjectId === item.id ? "project-list-item active" : "project-list-item"} onClick=${() => setSelectedProjectId(item.id)}>
                        <div className="activity-main">
                          <strong>${item.title}</strong>
                          <div className="subtle">${item.department || "未标记部门"} / ${item.vendor_name || "待确认供应商"} / ${stageText(item.current_stage)}</div>
                        </div>
                        <div className="activity-meta">
                          <span className="status-badge ${toneOf(item.status)}">${displayLabel(item.status)}</span>
                        </div>
                      </button>
                    `)}
                  </div>
                `
              : html`<div className="empty-box">当前没有进入法务视角的项目。</div>`}
          </div>
        </section>

        ${selectedProjectId && projectDetail
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

        ${selectedProjectId && projectDetail
          ? html`
              <div className="projects-layout wide procurement-layout">
                <section className="panel">
                  ${loadingDetail
                    ? html`<div className="center-panel" style=${{ minHeight: "220px" }}><div className="loading-ring"></div></div>`
                    : html`
                        ${projectDetail.current_stage !== "legal_review"
                          ? html`
                              <div className="project-blocker-banner success" style=${{ marginBottom: "16px" }}>
                                <strong>该项目已经完成法务阶段，当前处于：${stageText(projectDetail.current_stage)}</strong>
                                <div className="subtle" style=${{ marginTop: "6px" }}>
                                  你可以继续查看合同材料、法务结论和审批记录。
                                </div>
                              </div>
                            `
                          : null}

                        <div className="info-box">
                          <strong>采购部上传的申请</strong>
                          <div className="stack-list" style=${{ marginTop: "10px" }}>
                            <div className="subtle">申请部门：${projectDetail.department || "-"}</div>
                            <div className="subtle">申请人：${projectDetail.requester_name || "-"}</div>
                            <div className="subtle">目标供应商：${projectDetail.vendor_name || selectedVendor?.vendor_name || "-"}</div>
                            <div className="subtle">采购摘要：${projectDetail.summary || "暂无说明"}</div>
                            <div className="subtle">业务价值：${projectDetail.business_value || "暂无说明"}</div>
                          </div>
                        </div>

                        <div className="stack-list" style=${{ marginTop: "20px" }}>
                          <div className="panel procurement-upload-panel">
                            <div className="section-title-row">
                              <div>
                                <h4>1. 上传两份采购合同</h4>
                                <div className="subtle">法务页面只保留最核心的合同上传区：我方采购合同和对方修改后的采购合同。当前建议上传 md / docx，选择文件后点击上传，成功后即可进入自动审查。</div>
                              </div>
                            </div>
                            <div className="stack-list" style=${{ marginTop: "16px" }}>
                              ${canEditLegalContracts
                                ? html`<div className="inline-alert info">当前项目正处于法务审核阶段，可以在这里上传两份合同。</div>`
                                : html`<div className="inline-alert warn">当前项目已不在“法务审核”阶段，所以这里只保留合同查看区；如需上传，请切换到待法务处理的项目。</div>`}
                              ${legalBlockers.length
                                ? html`
                                    <div className="stack-list">
                                      ${legalBlockers.slice(0, 4).map((item) => html`<div className="inline-alert warn" key=${item}>${item}</div>`)}
                                    </div>
                                  `
                                : null}

                              ${ourContractArtifact
                                ? html`
                                    <div className="info-box">
                                      <div className="section-title-row">
                                        <strong>${projectArtifactTitle(ourContractArtifact)}</strong>
                                        <span className="status-badge ${toneOf(ourContractArtifact.status)}">${displayLabel(ourContractArtifact.status)}</span>
                                      </div>
                                      <div className="stack-list" style=${{ marginTop: "12px" }}>
                                        <div className="subtle">${ourContractArtifact.notes || "作为法务审查的基准合同。"}</div>
                                        ${legalContractFiles[ourContractArtifact.id]
                                          ? html`<div className="subtle">已选择文件：${legalContractFiles[ourContractArtifact.id].name}</div>`
                                          : null}
                                        ${canEditLegalContracts
                                          ? html`
                                              <input
                                                className="field"
                                                type="file"
                                                accept=".md,.markdown,.docx"
                                                disabled=${!canEditLegalContracts}
                                                onChange=${(event) => handleLegalContractSelection(ourContractArtifact, event)}
                                              />
                                            `
                                          : null}
                                        ${uploadingLegalArtifactId === ourContractArtifact.id
                                          ? html`<div className="inline-alert info">正在上传，请稍候...</div>`
                                          : null}
                                        ${(legalUploadFeedback[ourContractArtifact.id] || (ourContractArtifact.document_id && artifactIsReady(ourContractArtifact.status)))
                                          ? html`
                                              <div className="inline-alert success">
                                                ${legalUploadFeedback[ourContractArtifact.id] || "我方采购合同已上传成功，可以查看合同内容。"}
                                              </div>
                                            `
                                          : null}
                                        <div className="button-row">
                                          ${canEditLegalContracts
                                            ? html`
                                                <button
                                                  className="btn ghost small"
                                                  type="button"
                                                  onClick=${() => uploadLegalArtifact(ourContractArtifact)}
                                                  disabled=${uploadingLegalArtifactId === ourContractArtifact.id}
                                                >
                                                  上传文件
                                                </button>
                                              `
                                            : null}
                                          ${ourContractArtifact.document_id
                                            ? html`
                                                <button
                                                  className="btn secondary small"
                                                  type="button"
                                                  onClick=${() => fetchLegalArtifactPreview(ourContractArtifact.id)}
                                                  disabled=${loadingLegalPreviewId === ourContractArtifact.id}
                                                >
                                                  ${loadingLegalPreviewId === ourContractArtifact.id ? "加载中..." : "查看合同内容"}
                                                </button>
                                              `
                                            : null}
                                        </div>
                                        ${legalArtifactPreviews[ourContractArtifact.id]?.text_content
                                          ? html`
                                              <div className="info-box" style=${{ marginTop: "8px", background: "rgba(255,255,255,0.72)" }}>
                                                <strong>合同内容预览</strong>
                                                <pre className="code-block compact" style=${{ marginTop: "10px", maxHeight: "260px", overflow: "auto" }}>
${legalArtifactPreviews[ourContractArtifact.id].text_content}
                                                </pre>
                                              </div>
                                            `
                                          : null}
                                      </div>
                                    </div>
                                  `
                                : html`<div className="inline-alert warn">缺少“我方采购合同”材料卡片，请先由采购或系统生成。</div>`}

                              ${counterpartyContractArtifact
                                ? html`
                                    <div className="info-box">
                                      <div className="section-title-row">
                                        <strong>${projectArtifactTitle(counterpartyContractArtifact)}</strong>
                                        <span className="status-badge ${toneOf(counterpartyContractArtifact.status)}">${displayLabel(counterpartyContractArtifact.status)}</span>
                                      </div>
                                      <div className="stack-list" style=${{ marginTop: "12px" }}>
                                        <div className="subtle">${counterpartyContractArtifact.notes || "作为法务红线对比版本。"}</div>
                                        ${legalContractFiles[counterpartyContractArtifact.id]
                                          ? html`<div className="subtle">已选择文件：${legalContractFiles[counterpartyContractArtifact.id].name}</div>`
                                          : null}
                                        ${canEditLegalContracts
                                          ? html`
                                              <input
                                                className="field"
                                                type="file"
                                                accept=".md,.markdown,.docx"
                                                disabled=${!canEditLegalContracts}
                                                onChange=${(event) => handleLegalContractSelection(counterpartyContractArtifact, event)}
                                              />
                                            `
                                          : null}
                                        ${uploadingLegalArtifactId === counterpartyContractArtifact.id
                                          ? html`<div className="inline-alert info">正在上传，请稍候...</div>`
                                          : null}
                                        ${(legalUploadFeedback[counterpartyContractArtifact.id] || (counterpartyContractArtifact.document_id && artifactIsReady(counterpartyContractArtifact.status)))
                                          ? html`
                                              <div className="inline-alert success">
                                                ${legalUploadFeedback[counterpartyContractArtifact.id] || "对方修改后的采购合同已上传成功，可以查看合同内容。"}
                                              </div>
                                            `
                                          : null}
                                        <div className="button-row">
                                          ${canEditLegalContracts
                                            ? html`
                                                <button
                                                  className="btn ghost small"
                                                  type="button"
                                                  onClick=${() => uploadLegalArtifact(counterpartyContractArtifact)}
                                                  disabled=${uploadingLegalArtifactId === counterpartyContractArtifact.id}
                                                >
                                                  上传文件
                                                </button>
                                              `
                                            : null}
                                          ${counterpartyContractArtifact.document_id
                                            ? html`
                                                <button
                                                  className="btn secondary small"
                                                  type="button"
                                                  onClick=${() => fetchLegalArtifactPreview(counterpartyContractArtifact.id)}
                                                  disabled=${loadingLegalPreviewId === counterpartyContractArtifact.id}
                                                >
                                                  ${loadingLegalPreviewId === counterpartyContractArtifact.id ? "加载中..." : "查看合同内容"}
                                                </button>
                                              `
                                            : null}
                                        </div>
                                        ${legalArtifactPreviews[counterpartyContractArtifact.id]?.text_content
                                          ? html`
                                              <div className="info-box" style=${{ marginTop: "8px", background: "rgba(255,255,255,0.72)" }}>
                                                <strong>合同内容预览</strong>
                                                <pre className="code-block compact" style=${{ marginTop: "10px", maxHeight: "260px", overflow: "auto" }}>
${legalArtifactPreviews[counterpartyContractArtifact.id].text_content}
                                                </pre>
                                              </div>
                                            `
                                          : null}
                                      </div>
                                    </div>
                                  `
                                : html`<div className="inline-alert warn">缺少“对方修改后的采购合同”材料卡片，请先补齐。</div>`}

                              ${readyForAssistant
                                ? html`<div className="inline-alert info">两份合同已齐备，点击“审查合同”后系统会自动跳转到审查助手并立即开始审查。</div>`
                                : html`<div className="inline-alert warn">请先补齐两份采购合同，系统才会开放法务审查。</div>`}

                              <div className="button-row">
                                <button className="btn primary" type="button" onClick=${openLegalAssistant} disabled=${!actions.has("review_legal")}>
                                  审查合同
                                </button>
                              </div>
                            </div>
                          </div>
                        </div>
                      `}
                </section>

                <section className="panel">
                  <div className="section-title-row">
                    <h3>3. 法务审查结论</h3>
                    ${legalAssistantReview?.trace_id ? html`<span className="api-chip">Trace ${legalAssistantReview.trace_id.slice(0, 8)}</span>` : null}
                  </div>

                  <div className="stack-list">
                    <div className="info-box">
                      <strong>当前审批动作</strong>
                      <div className="button-row" style=${{ marginTop: "10px" }}>
                        <button className="btn secondary" type="button" onClick=${openLegalAssistant} disabled=${!actions.has("review_legal") || !readyForAssistant}>
                          前往审查助手
                        </button>
                        <button className="btn primary" type="button" onClick=${() => runAction(`/projects/${projectDetail.id}/legal-decision`, { decision: "approve", reason: "法务审查通过，提交管理员签署。" })} disabled=${!actions.has("legal_approve")}>
                          提交签署
                        </button>
                        <button className="btn ghost" type="button" onClick=${() => runAction(`/projects/${projectDetail.id}/return-to-procurement`, { reason: "法务要求采购补充材料或重新处理合同条款。" })} disabled=${!actions.has("return_to_procurement")}>
                          退回采购
                        </button>
                      </div>
                    </div>

                    <${ReviewSummaryCard}
                      html=${html}
                      title="法务结构化审查"
                      review=${legalAssistantAssessment}
                    />

                    ${projectDetail.legal_handoff
                      ? html`
                          <div className="info-box">
                            <strong>合同材料状态</strong>
                            <div className="stack-list" style=${{ marginTop: "10px" }}>
                              <div className="activity-item">
                                <div className="activity-main">
                                  <strong>我方采购合同</strong>
                                  <div className="subtle">${projectDetail.legal_handoff.our_contract_notes || "作为我方基准合同。"}</div>
                                </div>
                                <div className="activity-meta">
                                  <span className="status-badge ${toneOf(projectDetail.legal_handoff.our_contract_status)}">${displayLabel(projectDetail.legal_handoff.our_contract_status)}</span>
                                </div>
                              </div>
                              <div className="activity-item">
                                <div className="activity-main">
                                  <strong>对方修改后的采购合同</strong>
                                  <div className="subtle">${projectDetail.legal_handoff.counterparty_contract_notes || "作为红线对比版本。"}</div>
                                </div>
                                <div className="activity-meta">
                                  <span className="status-badge ${toneOf(projectDetail.legal_handoff.counterparty_contract_status)}">${displayLabel(projectDetail.legal_handoff.counterparty_contract_status)}</span>
                                </div>
                              </div>
                            </div>
                          </div>
                        `
                      : null}
                  </div>
                </section>
              </div>

              <section className="section-block">
                <div className="section-title-row"><h3>项目时间线</h3></div>
                ${timeline.length
                  ? html`
                      <div className="timeline-list">
                        ${timeline.map((event) => html`
                          <article className="timeline-card" key=${`${event.kind}-${event.created_at}-${event.title}`}>
                            <div className="timeline-badge neutral">${event.kind}</div>
                            <div className="timeline-body">
                              <strong>${event.title}</strong>
                              <div className="subtle">${stageText(event.stage)} / ${event.created_at}</div>
                              <p>${event.summary}</p>
                            </div>
                          </article>
                        `)}
                      </div>
                    `
                  : html`<div className="empty-box">暂无时间线事件。</div>`}
              </section>
            `
          : html`
              <section className="section-block">
                <div className="panel">
                  <div className="empty-box">请选择一个法务项目后再开始处理。</div>
                </div>
              </section>
            `}
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

  if (currentUser.role === "legal") {
    return renderLegalWorkspace();
  }

  if (currentUser.role === "admin") {
    return renderAdminWorkspace();
  }

  const grouped = groupByStage(projects);

  return html`
    <div>
      <div className="topbar"><div><h2>采购项目</h2><p>围绕业务申请、采购筛选、法务审查与签署归档的多角色协同工作台。</p></div></div>
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
          ${projectDetail.blocker_summary.length
            ? html`<div className="project-blocker-banner"><strong>当前阻塞</strong><div className="stack-list">${projectDetail.blocker_summary.slice(0, 5).map((item) => html`<div className="inline-alert warn" key=${item}>${item}</div>`)}</div></div>`
            : html`<div className="project-blocker-banner success"><strong>${projectDetail.status === "cancelled" ? "项目已取消" : "当前阶段可继续推进"}</strong></div>`}
        </section>

        <div className="projects-layout wide">
          <section className="panel">
            <div className="section-title-row"><h3>当前阶段动作</h3><div className="button-row">${renderStageActions()}</div></div>
            ${projectDetail.current_stage === "procurement_sourcing"
              ? html`
                  <label className="label">AI 审查问题</label>
                  <textarea className="field textarea-large" value=${reviewQuery} onInput=${(e) => setReviewQuery(e.target.value)}></textarea>
                `
              : null}
            ${projectDetail.current_stage === "legal_review"
              ? html`
                  <div className="info-box" style=${{ marginTop: "16px" }}>
                    <strong>法务 mini 审查模式</strong>
                    <div className="subtle">系统会默认对比两份合同，聚焦责任限制、赔偿责任、解约、保密和争议解决等核心红线。</div>
                    ${legalReviewReady
                      ? html`<div className="inline-alert info" style=${{ marginTop: "10px" }}>两份合同已齐备，可以直接开始审查。</div>`
                      : html`<div className="inline-alert warn" style=${{ marginTop: "10px" }}>请先补齐我方采购合同和对方修改版合同。</div>`}
                  </div>
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
                      <div className="activity-main">
                        <strong>${projectArtifactTitle(artifact)}</strong>
                        <div className="subtle">${displayLabel(artifact.direction)} / ${displayLabel(artifact.status)}</div>
                        ${artifact.notes ? html`<div className="subtle">${artifact.notes}</div>` : null}
                      </div>
                      <div className="activity-meta"><span className="status-badge ${toneOf(artifact.status)}">${displayLabel(artifact.status)}</span>${!["provided", "approved"].includes(artifact.status) && projectDetail.status === "active" ? html`<button className="btn ghost small" onClick=${() => markArtifactProvided(artifact.id)}>${projectArtifactActionLabel(artifact)}</button>` : null}</div>
                    </div>
                  `)}</div>` : html`<div className="empty-box">当前阶段暂无材料要求。</div>`}
                  ${projectDetail.current_stage === "legal_review" && projectDetail.legal_handoff
                    ? html`
                        <div className="section-title-row" style=${{ marginTop: "20px" }}><h4>合同材料状态</h4></div>
                        <div className="stack-list">
                          <div className="activity-item">
                            <div className="activity-main">
                              <strong>我方采购合同</strong>
                              <div className="subtle">${projectDetail.legal_handoff.our_contract_notes || "作为法务对比基准文本。"}</div>
                            </div>
                            <div className="activity-meta">
                              <span className="status-badge ${toneOf(projectDetail.legal_handoff.our_contract_status)}">${displayLabel(projectDetail.legal_handoff.our_contract_status)}</span>
                            </div>
                          </div>
                          <div className="activity-item">
                            <div className="activity-main">
                              <strong>对方修改后的采购合同</strong>
                              <div className="subtle">${projectDetail.legal_handoff.counterparty_contract_notes || "作为红线对比文本。"}</div>
                            </div>
                            <div className="activity-meta">
                              <span className="status-badge ${toneOf(projectDetail.legal_handoff.counterparty_contract_status)}">${displayLabel(projectDetail.legal_handoff.counterparty_contract_status)}</span>
                            </div>
                          </div>
                        </div>
                      `
                    : null}
                `}
          </section>

          <section className="panel">
            <div className="section-title-row"><h3>候选供应商</h3></div>
            ${projectDetail.current_stage === "procurement_sourcing" && projectDetail.status === "active" ? html`
              <form className="stack-list" onSubmit=${createVendorManually}>
                <input className="field" placeholder="供应商名称" value=${vendorForm.vendor_name} onInput=${(e) => updateVendorField("vendor_name", e.target.value)} />
                <div className="split-fields">
                  <input className="field" placeholder="来源平台" value=${vendorForm.source_platform} onInput=${(e) => updateVendorField("source_platform", e.target.value)} />
                  <input className=${vendorFormErrors.source_url ? "field error" : "field"} placeholder="来源链接" value=${vendorForm.source_url} onInput=${(e) => updateVendorField("source_url", e.target.value)} />
                </div>
                ${vendorFormErrors.source_url ? html`<small className="field-error-text">${vendorFormErrors.source_url}</small>` : null}
                <div className="split-fields">
                  <input className="field" placeholder="联系人" value=${vendorForm.contact_name} onInput=${(e) => updateVendorField("contact_name", e.target.value)} />
                  <input className=${vendorFormErrors.contact_email ? "field error" : "field"} placeholder="联系邮箱" value=${vendorForm.contact_email} onInput=${(e) => updateVendorField("contact_email", e.target.value)} />
                </div>
                ${vendorFormErrors.contact_email ? html`<small className="field-error-text">${vendorFormErrors.contact_email}</small>` : null}
                <input className="field" placeholder="联系电话" value=${vendorForm.contact_phone} onInput=${(e) => updateVendorField("contact_phone", e.target.value)} />
                <textarea className="field textarea-medium" placeholder="公司简介与来源说明" value=${vendorForm.profile_summary} onInput=${(e) => updateVendorField("profile_summary", e.target.value)}></textarea>
                <textarea className="field textarea-medium" placeholder="采购说明" value=${vendorForm.procurement_notes} onInput=${(e) => updateVendorField("procurement_notes", e.target.value)}></textarea>
                <div className="button-row"><button className="btn secondary" type="submit">新增候选供应商</button></div>
              </form>
            ` : null}
            ${vendors.length ? html`<div className="stack-list" style=${{ marginTop: "16px" }}>${vendors.map((vendor) => html`
              <button key=${vendor.id} className=${activeVendor?.id === vendor.id ? "project-list-item active" : "project-list-item"} onClick=${() => setActiveVendorId(vendor.id)}>
                <div className="activity-main"><strong>${vendor.vendor_name}</strong><div className="subtle">${vendor.source_platform || "未填写来源平台"} / ${vendor.ai_recommendation ? displayLabel(vendor.ai_recommendation) : "尚未评审"}</div></div>
                <div className="activity-meta"><span className="status-badge ${toneOf(vendor.status)}">${displayLabel(vendor.status)}</span></div>
              </button>
            `)}</div>` : html`<div className="empty-box">还没有候选供应商。</div>`}

            ${showLegalWorkspace && projectDetail.legal_handoff
              ? html`
                  <div className="section-title-row" style=${{ marginTop: "20px" }}><h4>法务合同对比</h4></div>
                  <div className="stack-list">
                    <div className="activity-item">
                      <div className="activity-main">
                        <strong>我方采购合同</strong>
                        <div className="subtle">${projectDetail.legal_handoff.our_contract_notes || "尚未补充备注。"}</div>
                      </div>
                      <div className="activity-meta">
                        <span className="status-badge ${toneOf(projectDetail.legal_handoff.our_contract_status)}">${displayLabel(projectDetail.legal_handoff.our_contract_status)}</span>
                      </div>
                    </div>
                    <div className="activity-item">
                      <div className="activity-main">
                        <strong>对方修改后的采购合同</strong>
                        <div className="subtle">${projectDetail.legal_handoff.counterparty_contract_notes || "尚未补充备注。"}</div>
                      </div>
                      <div className="activity-meta">
                        <span className="status-badge ${toneOf(projectDetail.legal_handoff.counterparty_contract_status)}">${displayLabel(projectDetail.legal_handoff.counterparty_contract_status)}</span>
                      </div>
                    </div>
                  </div>
                `
              : null}

            <div className="section-title-row" style=${{ marginTop: "20px" }}><h4>${showLegalWorkspace ? "法务审查卡" : "审查摘要"}</h4></div>
            ${showLegalWorkspace
              ? html`<${ReviewSummaryCard} html=${html} title="法务结构化审查" review=${projectDetail.latest_legal_review} />`
              : html`<${ReviewSummaryCard} html=${html} title="供应商结构化审查" review=${activeVendor?.structured_review} />`}

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
