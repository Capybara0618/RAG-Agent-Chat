import React, { useEffect, useMemo, useRef, useState } from "https://esm.sh/react@18.3.1";

import { DEMO_QUESTIONS, displayLabel, toneOf } from "./config.js";
import { apiGet, apiPost } from "./api.js";

function StructuredReviewPanel({ html, title, review }) {
  if (!review) {
    return html`<div className="empty-box">当前还没有可展示的结构化审查结果。</div>`;
  }

  return html`
    <div className="stack-list">
      <div className="info-box">
        <strong>${title}</strong>
        <p className="muted">${review.summary}</p>
        <div className="button-row">
          <span className="status-badge ${toneOf(review.recommendation)}">${displayLabel(review.recommendation)}</span>
          <span className="status-badge neutral">${review.conclusion}</span>
          ${review.next_step ? html`<span className="status-badge neutral">${review.next_step}</span>` : null}
        </div>
      </div>

      ${review.legal_handoff_recommendation
        ? html`
            <div className="info-box">
              <strong>法务流转建议</strong>
              <div className="button-row" style=${{ marginTop: "10px" }}>
                <span className="status-badge ${toneOf(review.legal_handoff_recommendation)}">
                  ${displayLabel(review.legal_handoff_recommendation)}
                </span>
              </div>
              ${review.legal_handoff_reason ? html`<p className="muted">${review.legal_handoff_reason}</p>` : null}
            </div>
          `
        : null}

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
              <strong>风险点</strong>
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
    </div>
  `;
}

function EvidencePanel({ html, citations }) {
  if (!citations?.length) {
    return html`<div className="empty-box compact">当前还没有可展示的引用证据。</div>`;
  }

  return html`
    <div className="citation-grid">
      ${citations.map(
        (citation) => html`
          <article className="citation-card" key=${`${citation.document_id}-${citation.location}`}>
            <strong>${citation.document_title}</strong>
            <div className="subtle">${citation.location}</div>
            <p>${citation.snippet}</p>
            ${citation.score ? html`<div className="mono">相关度 ${citation.score}</div>` : null}
          </article>
        `,
      )}
    </div>
  `;
}

function MaterialPanel({ html, summary, warnings, materials }) {
  if (!summary && !warnings?.length && !materials?.length) {
    return null;
  }

  return html`
    <div className="info-box">
      <strong>材料解析</strong>
      ${summary ? html`<div className="subtle" style=${{ marginTop: "10px" }}>${summary}</div>` : null}
      ${warnings?.length
        ? html`
            <div className="stack-list" style=${{ marginTop: "10px" }}>
              ${warnings.map((item) => html`<div className="inline-alert warn" key=${item}>${item}</div>`)}
            </div>
          `
        : null}
      ${materials?.length
        ? html`
            <div className="stack-list" style=${{ marginTop: "12px" }}>
              ${materials.map((item) => html`
                <div className="activity-item" key=${`${item.name}-${item.source_type}`}>
                  <div className="activity-main">
                    <strong>${item.name}</strong>
                    <div className="subtle">${item.source_type} / ${item.char_count} chars</div>
                    <div className="subtle">${item.excerpt}</div>
                    ${item.text
                      ? html`
                          <details style=${{ marginTop: "8px" }}>
                            <summary className="subtle">View parsed text</summary>
                            <pre className="code-block compact">${item.text}</pre>
                          </details>
                        `
                      : null}
                  </div>
                </div>
              `)}
            </div>
          `
        : null}
    </div>
  `;
}

function LegalReviewPanel({ html, review }) {
  if (!review) {
    return html`<div className="empty-box">当前还没有法务结构化审查结果。</div>`;
  }

  return html`
    <div className="stack-list">
      <div className="info-box">
        <strong>法务结构化审查</strong>
        <div className="subtle" style=${{ marginTop: "10px" }}>${review.summary || review.conclusion}</div>
        <div className="button-row" style=${{ marginTop: "10px" }}>
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

      ${review.clause_gaps?.length
        ? html`
            <div className="info-box">
              <strong>问题条款</strong>
              <div className="stack-list" style=${{ marginTop: "10px" }}>
                ${review.clause_gaps.map((item) => html`<div className="inline-alert warn" key=${item}>${item}</div>`)}
              </div>
            </div>
          `
        : null}

      ${review.blocking_issues?.length
        ? html`
            <div className="info-box">
              <strong>审查提示</strong>
              <div className="stack-list" style=${{ marginTop: "10px" }}>
                ${review.blocking_issues.map((item) => html`<div className="inline-alert info" key=${item}>${item}</div>`)}
              </div>
            </div>
          `
        : null}

      ${review.risk_flags?.length
        ? html`
            <div className="info-box">
              <strong>风险点</strong>
              <div className="stack-list" style=${{ marginTop: "10px" }}>
                ${review.risk_flags.map((item) => html`<div className="inline-alert warn" key=${item}>${item}</div>`)}
              </div>
            </div>
          `
        : null}

      ${review.open_questions?.length
        ? html`
            <div className="info-box">
              <strong>待补问题</strong>
              <div className="stack-list" style=${{ marginTop: "10px" }}>
                ${review.open_questions.map((item) => html`<div key=${item}>${item}</div>`)}
              </div>
            </div>
          `
        : null}

      ${review.evidence?.length
        ? html`
            <div className="info-box">
              <strong>引用依据</strong>
              <div className="stack-list" style=${{ marginTop: "10px" }}>
                ${review.evidence.map((item, index) => html`
                  <div className="activity-item" key=${`${item.document_title || "evidence"}-${item.location || index}-${index}`}>
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
    </div>
  `;
}

export function AssistantPage({
  html,
  currentUser,
  draftQuestion,
  setDraftQuestion,
  assistantTask,
  setAssistantTask,
  assistantResult,
  setAssistantResult,
  onNavigate,
  onTraceCreated,
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [agentFocus, setAgentFocus] = useState("");
  const previousTaskKeyRef = useRef("");

  const isProcurementAgentMode = currentUser?.role === "procurement" && assistantTask?.kind === "procurement_vendor_review";
  const isLegalAgentMode = currentUser?.role === "legal" && assistantTask?.kind === "legal_contract_review";
  const hasUploadedMaterials = Array.isArray(assistantTask?.uploadedFiles) && assistantTask.uploadedFiles.length > 0;
  const genericCitations = assistantResult?.citations || [];
  const agentCitations = assistantResult?.review?.citations || [];
  const extractedMaterials = assistantResult?.extracted_materials || assistantTask?.extractedMaterials || [];
  const extractionSummary = assistantResult?.extraction_summary || assistantTask?.extractionSummary || "";
  const extractionWarnings = assistantResult?.warnings || assistantTask?.warnings || [];
  const supplierProfile = assistantResult?.supplier_profile || assistantTask?.supplierProfile || null;
  const materialGate = assistantResult?.material_gate || assistantTask?.materialGate || null;
  const requirementChecks = assistantResult?.requirement_checks || assistantTask?.requirementChecks || [];
  const supplierDossier = assistantResult?.supplier_dossier || assistantTask?.supplierDossier || null;
  const legalAssessment = assistantResult?.assessment || assistantTask?.latestAssessment || null;

  useEffect(() => {
    const nextTaskKey = `${assistantTask?.kind || "generic"}:${assistantTask?.projectId || ""}:${assistantTask?.linkedVendorId || ""}`;
    if (!previousTaskKeyRef.current) {
      previousTaskKeyRef.current = nextTaskKey;
      return;
    }
    if (previousTaskKeyRef.current !== nextTaskKey) {
      setError("");
      if (!isProcurementAgentMode && !isLegalAgentMode) setAgentFocus("");
      if (setAssistantResult) setAssistantResult(null);
      previousTaskKeyRef.current = nextTaskKey;
    }
  }, [assistantTask?.kind, assistantTask?.projectId, assistantTask?.linkedVendorId, isProcurementAgentMode, isLegalAgentMode, setAssistantResult]);

  useEffect(() => {
    if (!isProcurementAgentMode || agentFocus || !assistantTask?.focusPoints) return;
    setAgentFocus(assistantTask.focusPoints);
  }, [assistantTask?.focusPoints, agentFocus, isProcurementAgentMode]);

  useEffect(() => {
    if (!isLegalAgentMode || agentFocus || !assistantTask?.query) return;
    setAgentFocus(assistantTask.query);
  }, [assistantTask?.query, agentFocus, isLegalAgentMode]);

  async function submitSingleAnswer() {
    const question = draftQuestion.trim();
    if (!question) return;

    try {
      setLoading(true);
      setError("");
      const payload = await apiPost("/chat/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: question,
          top_k: 5,
          session_id: null,
        }),
      });
      if (setAssistantResult) setAssistantResult(payload);
      onTraceCreated(payload.trace_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function runProcurementAgentReview() {
    if (!assistantTask?.projectId) return;

    try {
      setLoading(true);
      setError("");

      if (hasUploadedMaterials) {
        const formData = new FormData();
        assistantTask.uploadedFiles.forEach((file) => formData.append("files", file));
        formData.append("focus_points", agentFocus);
        formData.append("top_k", "6");
        const payload = await apiPost(`/projects/${assistantTask.projectId}/procurement-agent-run`, {
          method: "POST",
          body: formData,
        });
        if (setAssistantResult) setAssistantResult(payload);
        if (setAssistantTask) {
          setAssistantTask({
            ...assistantTask,
            vendorDraft: payload.vendor_draft,
            extractionSummary: payload.extraction_summary,
            extractedMaterials: payload.extracted_materials || [],
            warnings: payload.warnings || [],
            supplierProfile: payload.supplier_profile || null,
            materialGate: payload.material_gate || null,
            requirementChecks: payload.requirement_checks || [],
            supplierDossier: payload.supplier_dossier || null,
            focusPoints: agentFocus,
          });
        }
        onTraceCreated(payload.review.trace_id);
        return;
      }

      const payload = await apiPost(`/projects/${assistantTask.projectId}/procurement-agent-review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...assistantTask.vendorDraft,
          supplier_profile: supplierProfile,
          focus_points: agentFocus,
          top_k: 6,
        }),
      });
      if (setAssistantResult) setAssistantResult(payload);
      if (setAssistantTask) {
        setAssistantTask({
          ...assistantTask,
          supplierProfile,
          materialGate: payload.material_gate || assistantTask?.materialGate || null,
          requirementChecks: payload.requirement_checks || assistantTask?.requirementChecks || [],
          supplierDossier: payload.supplier_dossier || assistantTask?.supplierDossier || null,
          focusPoints: agentFocus,
        });
      }
      onTraceCreated(payload.review.trace_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function runLegalAgentReview() {
    if (!assistantTask?.projectId) return;

    try {
      setLoading(true);
      setError("");
      const payload = await apiPost(`/projects/${assistantTask.projectId}/legal/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: agentFocus?.trim?.() || assistantTask?.query || "",
          user_role: "legal",
          top_k: 6,
        }),
      });
      if (setAssistantResult) setAssistantResult(payload);
      if (setAssistantTask) {
        setAssistantTask({
          ...assistantTask,
          query: agentFocus?.trim?.() || assistantTask?.query || "",
          latestAssessment: payload.assessment || null,
        });
      }
      onTraceCreated(payload.review.trace_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function submitLegalApproval() {
    if (!assistantTask?.projectId) return;

    try {
      setLoading(true);
      setError("");
      await apiPost(`/projects/${assistantTask.projectId}/legal-decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          decision: "approve",
          reason: "法务审查通过，提交管理员签署。",
        }),
      });
      if (setAssistantTask) setAssistantTask(null);
      if (setAssistantResult) setAssistantResult(null);
      window.alert("法务已审查通过，项目已提交给管理员签署。");
      if (onNavigate) onNavigate("projects");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!isProcurementAgentMode || !hasUploadedMaterials || assistantResult || loading) return;
    runProcurementAgentReview();
  }, [assistantResult, hasUploadedMaterials, isProcurementAgentMode, loading]);

  useEffect(() => {
    if (!isLegalAgentMode || !assistantTask?.autorun || assistantResult || loading) return;
    if (setAssistantTask) {
      setAssistantTask((currentTask) => {
        if (!currentTask || currentTask.kind !== "legal_contract_review") return currentTask;
        return { ...currentTask, autorun: false };
      });
    }
    runLegalAgentReview();
  }, [assistantResult, assistantTask?.autorun, isLegalAgentMode, loading, setAssistantTask]);

  if (currentUser?.role === "procurement" && !isProcurementAgentMode) {
    return html`
      <div>
        <div className="topbar">
          <div>
            <h2>供应商 Agent 审查</h2>
            <p>从采购执行页面带入当前项目和供应商材料后，系统会自动完成一轮审查。</p>
          </div>
        </div>

        <div className="center-panel" style=${{ maxWidth: "760px" }}>
          <div className="empty-box">当前没有待执行的供应商审查任务。请先回到采购执行页面上传材料或带入供应商草稿。</div>
          <div className="button-row" style=${{ marginTop: "16px" }}>
            <button className="btn primary" onClick=${() => onNavigate && onNavigate("projects")}>返回采购执行</button>
          </div>
        </div>
      </div>
    `;
  }

  if (currentUser?.role === "legal" && !isLegalAgentMode) {
    return html`
        <div>
          <div className="topbar">
            <div>
              <h2>法务审查助手</h2>
              <p>请先从法务审核工作台带入一个合同审查任务。系统收到任务后会自动开始法务 Agent 审查。</p>
            </div>
          </div>

        <div className="center-panel" style=${{ maxWidth: "760px" }}>
          <div className="empty-box">当前没有待执行的法务合同审查任务。请先回到法务审核工作台确认两份合同材料。</div>
          <div className="button-row" style=${{ marginTop: "16px" }}>
            <button className="btn primary" onClick=${() => onNavigate && onNavigate("projects")}>返回法务审核</button>
          </div>
        </div>
      </div>
    `;
  }

  if (isProcurementAgentMode) {
    return html`
      <div>
        <div className="topbar">
          <div>
            <h2>供应商 Agent 审查</h2>
            <p>系统会结合项目背景、供应商材料和本地知识库，自动给出准入判断、风险提示和法务流转建议。</p>
          </div>
        </div>

        <div className="assistant-layout">
          <section className="panel">
            <div className="section-title-row">
              <h3>审查任务</h3>
              <button className="btn ghost small" onClick=${() => onNavigate && onNavigate("projects")}>返回采购执行</button>
            </div>

            <div className="info-box">
              <strong>当前项目</strong>
              <div className="stack-list" style=${{ marginTop: "10px" }}>
                <div className="subtle">项目名称：${assistantTask.projectTitle || "-"}</div>
                <div className="subtle">项目编号：${assistantTask.projectId || "-"}</div>
              </div>
            </div>

            <div className="info-box">
              <strong>供应商草稿</strong>
              <div className="stack-list" style=${{ marginTop: "10px" }}>
                <div className="subtle">供应商：${assistantTask.vendorDraft?.vendor_name || "-"}</div>
                <div className="subtle">来源平台：${assistantTask.vendorDraft?.source_platform || "-"}</div>
                <div className="subtle">来源链接：${assistantTask.vendorDraft?.source_url || "未提供"}</div>
                <div className="subtle">简介：${assistantTask.vendorDraft?.profile_summary || "未填写"}</div>
                <div className="subtle">采购说明：${assistantTask.vendorDraft?.procurement_notes || "未填写"}</div>
              </div>
            </div>

            <${MaterialPanel}
              html=${html}
              summary=${extractionSummary}
              warnings=${extractionWarnings}
              materials=${extractedMaterials}
            />

            <label className="label">补充关注点</label>
            <textarea
              className="field textarea-medium"
              value=${agentFocus}
              onInput=${(event) => setAgentFocus(event.target.value)}
              placeholder="可选，例如：重点关注客户数据、跨境传输或合同红线。"
            ></textarea>

            <div className="info-box">
              <strong>Agent 会自动完成</strong>
              <div className="stack-list" style=${{ marginTop: "10px" }}>
                <div>1. 解析供应商材料并抽取关键信息</div>
                <div>2. 检索准入制度、审批矩阵和合规知识</div>
                <div>3. 判断是否建议继续推进和是否建议转法务</div>
                <div>4. 输出风险点、缺失材料和下一步动作</div>
              </div>
            </div>

            <div className="button-row">
              <button className="btn primary" onClick=${runProcurementAgentReview} disabled=${loading}>
                ${loading ? "正在执行 Agent 审查..." : hasUploadedMaterials ? "重新运行材料审查" : "开始 Agent 审查"}
              </button>
              <button className="btn ghost" onClick=${() => setAssistantTask && setAssistantTask(null)} disabled=${loading}>
                清空当前任务
              </button>
            </div>
            ${error ? html`<div className="error">${error}</div>` : null}
          </section>

          <section className="panel">
            <div className="section-title-row">
              <h3>审查结果</h3>
              ${assistantResult?.review?.trace_id ? html`<span className="api-chip">Trace ${assistantResult.review.trace_id.slice(0, 8)}</span>` : null}
            </div>

            ${assistantResult
              ? html`
                  <div className="review-summary-grid">
                    <div className="mini-metric">
                      <div className="eyebrow">问题类型</div>
                      <div className="review-summary-value">${displayLabel(assistantResult.review.intent)}</div>
                    </div>
                    <div className="mini-metric">
                      <div className="eyebrow">系统动作</div>
                      <div className="review-summary-value ${toneOf(assistantResult.review.next_action)}">
                        ${displayLabel(assistantResult.review.next_action)}
                      </div>
                    </div>
                    <div className="mini-metric">
                      <div className="eyebrow">置信度</div>
                      <div className="review-summary-value">${assistantResult.review.confidence}</div>
                    </div>
                    <div className="mini-metric">
                      <div className="eyebrow">准入建议</div>
                      <div className="review-summary-value ${toneOf(assistantResult.assessment.recommendation)}">
                        ${displayLabel(assistantResult.assessment.recommendation)}
                      </div>
                    </div>
                  </div>

                  <${StructuredReviewPanel}
                    html=${html}
                    title="采购 Agent 结构化结论"
                    review=${assistantResult.assessment}
                  />

                  ${materialGate
                    ? html`
                        <div className="info-box">
                          <strong>材料闸门</strong>
                          <div className="stack-list" style=${{ marginTop: "10px" }}>
                            <div className="button-row">
                              <span className="status-badge ${toneOf(materialGate.decision === "pass" ? "pass" : "fail")}">
                                ${materialGate.decision === "pass" ? "已通过" : "未通过"}
                              </span>
                              ${materialGate.relevance_score != null ? html`<span className="status-badge neutral">相关度 ${materialGate.relevance_score}</span>` : null}
                            </div>
                            ${materialGate.matched_material_types?.length ? html`<div className="subtle">识别材料类型：${materialGate.matched_material_types.join(" / ")}</div>` : null}
                            ${materialGate.blocking_reasons?.length
                              ? html`
                                  <div className="stack-list">
                                    ${materialGate.blocking_reasons.map((item) => html`<div className="inline-alert danger" key=${item}>${item}</div>`)}
                                  </div>
                                `
                              : html`<div className="subtle">材料已满足进入制度审查的基本门槛。</div>`}
                          </div>
                        </div>
                      `
                    : null}

                  ${requirementChecks?.length
                    ? html`
                        <div className="info-box">
                          <strong>必备材料清单</strong>
                          <div className="stack-list" style=${{ marginTop: "10px" }}>
                            ${requirementChecks.map((item) => html`
                              <div className="activity-item" key=${item.key}>
                                <div className="activity-main">
                                  <strong>${item.label}</strong>
                                  <div className="subtle">${item.detail}</div>
                                  ${item.evidence_titles?.length ? html`<div className="subtle">证据：${item.evidence_titles.join(" / ")}</div>` : null}
                                </div>
                                <div className="activity-meta">
                                  <span className="status-badge ${toneOf(item.status === "missing" ? "fail" : item.status === "not_required" ? "info" : item.status)}">
                                    ${item.status === "missing" ? "缺失" : item.status === "not_required" ? "暂不要求" : displayLabel(item.status)}
                                  </span>
                                </div>
                              </div>
                            `)}
                          </div>
                        </div>
                      `
                    : null}

                  ${supplierDossier
                    ? html`
                        <div className="info-box">
                          <strong>供应商 Dossier</strong>
                          <div className="stack-list" style=${{ marginTop: "10px" }}>
                            <div className="subtle">供应商：${supplierDossier.vendor_name || "-"}</div>
                            <div className="subtle">主体名称：${supplierDossier.legal_entity || "未识别"}</div>
                            <div className="subtle">服务模型：${supplierDossier.service_model || "未识别"}</div>
                            <div className="subtle">数据接触级别：${supplierDossier.data_access_level || "unknown"}</div>
                            <div className="subtle">部署/存储区域：${supplierDossier.hosting_region || "未说明"}</div>
                            <div className="subtle">分包安排：${supplierDossier.subprocessor_signal || "unknown"}</div>
                            <div className="subtle">Դ${supplierDossier.source_urls?.join(" / ") || "δṩ"}</div>
                          </div>
                        </div>
                      `
                    : null}

                  <div className="info-box">
                    <strong>Agent 原始回答</strong>
                    <div className="answer-box" style=${{ marginTop: "10px" }}>${assistantResult.review.answer}</div>
                  </div>

                  <div className="info-box">
                    <strong>引用证据</strong>
                    <${EvidencePanel} html=${html} citations=${agentCitations} />
                  </div>

                  ${assistantResult.review.tool_calls?.length
                    ? html`
                        <div className="info-box">
                          <strong>工具调用轨迹</strong>
                          <div className="stack-list" style=${{ marginTop: "10px" }}>
                            ${assistantResult.review.tool_calls.map((item) => html`
                              <div className="activity-item" key=${`${item.tool_name}-${item.input_summary}`}>
                                <div className="activity-main">
                                  <strong>${item.tool_name}</strong>
                                  <div className="subtle">${item.purpose || "未填写工具用途"}</div>
                                  ${item.input_summary ? html`<div className="subtle">输入：${item.input_summary}</div>` : null}
                                  ${item.output_summary ? html`<div className="subtle">输出：${item.output_summary}</div>` : null}
                                </div>
                                <div className="activity-meta">
                                  <span className="status-badge ${toneOf(item.status === "success" ? "pass" : item.status === "warn" ? "pending" : "fail")}">
                                    ${item.status === "success" ? "成功" : item.status === "warn" ? "告警" : "失败"}
                                  </span>
                                </div>
                              </div>
                            `)}
                          </div>
                        </div>
                      `
                    : null}

                  <div className="info-box">
                    <strong>Agent 调试摘要</strong>
                    <pre className="code-block compact">${JSON.stringify(assistantResult.review.debug_summary || {}, null, 2)}</pre>
                  </div>
                `
              : html`
                  <div className="empty-box">
                    运行完成后，这里会展示结构化结论、风险点、缺失材料和是否建议转法务。
                  </div>
                `}
          </section>
        </div>
      </div>
    `;
  }

  if (isLegalAgentMode) {
    return html`
        <div>
          <div className="topbar">
            <div>
              <h2>法务审查助手</h2>
              <p>系统会基于两份采购合同做红线对比，自动输出结构化法务结论，供法务最终人工通过或退回采购。</p>
            </div>
          </div>

        <div className="assistant-layout">
          <section className="panel">
            <div className="section-title-row">
              <h3>审查任务</h3>
              <button className="btn ghost small" onClick=${() => onNavigate && onNavigate("projects")}>返回法务审核</button>
            </div>

            <div className="info-box">
              <strong>当前项目</strong>
              <div className="stack-list" style=${{ marginTop: "10px" }}>
                <div className="subtle">项目名称：${assistantTask.projectTitle || "-"}</div>
                <div className="subtle">项目编号：${assistantTask.projectId || "-"}</div>
                <div className="subtle">目标供应商：${assistantTask.vendorName || "-"}</div>
              </div>
            </div>

            <div className="info-box">
              <strong>合同材料状态</strong>
              <div className="stack-list" style=${{ marginTop: "10px" }}>
                <div className="subtle">我方采购合同：${displayLabel(assistantTask.legalHandoff?.our_contract_status || "missing")}</div>
                <div className="subtle">对方修改后的采购合同：${displayLabel(assistantTask.legalHandoff?.counterparty_contract_status || "missing")}</div>
              </div>
            </div>

            <label className="label">审查指令</label>
            <textarea
              className="field textarea-medium"
              value=${agentFocus}
              onInput=${(event) => setAgentFocus(event.target.value)}
              placeholder="默认会对比两份采购合同的红线条款，也可以在这里补充关注点。"
            ></textarea>

            <div className="info-box">
              <strong>Agent 会自动完成</strong>
              <div className="stack-list" style=${{ marginTop: "10px" }}>
                <div>1. 对比我方采购合同和对方修改版合同</div>
                <div>2. 聚焦责任限制、赔偿责任、解约、保密、争议解决等核心红线</div>
                <div>3. 输出结构化风险、问题条款、证据引用和建议动作</div>
                <div>4. 将最终是否通过留给法务人工决策</div>
              </div>
            </div>

            <div className="button-row">
              <button className="btn primary" onClick=${runLegalAgentReview} disabled=${loading}>
                ${loading ? "正在运行法务审查..." : legalAssessment ? "重新审查合同" : "开始合同审查"}
              </button>
              <button className="btn ghost" onClick=${() => setAssistantTask && setAssistantTask(null)} disabled=${loading}>
                清空当前任务
              </button>
            </div>
            ${error ? html`<div className="error">${error}</div>` : null}
          </section>

          <section className="panel">
            <div className="section-title-row">
              <h3>审查结果</h3>
              ${assistantResult?.review?.trace_id ? html`<span className="api-chip">Trace ${assistantResult.review.trace_id.slice(0, 8)}</span>` : null}
            </div>

            ${legalAssessment
              ? html`
                  <div className="review-summary-grid">
                    <div className="mini-metric">
                      <div className="eyebrow">风险等级</div>
                      <div className="review-summary-value ${toneOf(legalAssessment.risk_level)}">${displayLabel(legalAssessment.risk_level)}</div>
                    </div>
                    <div className="mini-metric">
                      <div className="eyebrow">建议动作</div>
                      <div className="review-summary-value ${toneOf(legalAssessment.decision_suggestion)}">${displayLabel(legalAssessment.decision_suggestion)}</div>
                    </div>
                    <div className="mini-metric">
                      <div className="eyebrow">审查建议</div>
                      <div className="review-summary-value ${toneOf(legalAssessment.recommendation)}">${displayLabel(legalAssessment.recommendation)}</div>
                    </div>
                    <div className="mini-metric">
                      <div className="eyebrow">模型动作</div>
                      <div className="review-summary-value ${toneOf(assistantResult?.review?.next_action)}">${displayLabel(assistantResult?.review?.next_action)}</div>
                    </div>
                  </div>

                  <${LegalReviewPanel} html=${html} review=${legalAssessment} />

                  ${assistantResult?.review?.answer
                    ? html`
                        <div className="info-box">
                          <strong>Agent 原始回答</strong>
                          <div className="answer-box" style=${{ marginTop: "10px" }}>${assistantResult.review.answer}</div>
                        </div>
                      `
                    : null}

                  <div className="info-box">
                    <strong>引用证据</strong>
                    <${EvidencePanel} html=${html} citations=${agentCitations} />
                  </div>

                   ${assistantResult?.review?.debug_summary
                     ? html`
                         <div className="info-box">
                           <strong>Agent 调试摘要</strong>
                           <pre className="code-block compact">${JSON.stringify(assistantResult.review.debug_summary || {}, null, 2)}</pre>
                         </div>
                       `
                     : null}

                   <div className="button-row">
                     <button className="btn primary" onClick=${submitLegalApproval} disabled=${loading}>
                       提交签署
                     </button>
                     <button className="btn ghost" onClick=${() => onNavigate && onNavigate("projects")} disabled=${loading}>
                       返回法务工作台
                     </button>
                   </div>
                 `
               : html`
                   <div className="empty-box">
                     ${loading ? "系统正在自动审查两份合同，稍候这里会直接出现结构化法务结论。" : "运行合同审查后，这里会显示结构化法务结论、问题条款、引用依据以及建议动作。"}
                  </div>
                `}
          </section>
        </div>
      </div>
    `;
  }

  return html`
    <div>
      <div className="topbar">
        <div>
          <h2>审查助手</h2>
          <p>这里是单次问答模式。每次发送都会独立生成一个答案，不保留多轮上下文。</p>
        </div>
      </div>

      <div className="assistant-layout">
        <section className="panel">
          <div className="section-title-row">
            <h3>提问面板</h3>
          </div>

          <label className="label">当前角色</label>
          <div className="field" style=${{ display: "flex", alignItems: "center" }}>
            ${displayLabel(currentUser?.role)}
          </div>

          <label className="label" style=${{ marginTop: "16px" }}>快捷问题</label>
          <div className="question-grid">
            ${DEMO_QUESTIONS.map(
              (item) => html`
                <button className="question-card" key=${item} onClick=${() => setDraftQuestion(item)}>
                  ${item}
                </button>
              `,
            )}
          </div>

          <label className="label" style=${{ marginTop: "18px" }}>问题</label>
          <textarea
            className="field textarea-medium"
            value=${draftQuestion}
            onInput=${(event) => setDraftQuestion(event.target.value)}
            placeholder="例如：在正式签署前，这个项目还缺哪些审批或归档动作？"
          ></textarea>

          <div className="button-row">
            <button className="btn primary" onClick=${submitSingleAnswer} disabled=${loading || !draftQuestion.trim()}>
              ${loading ? "ɴ..." : "ɵδ"}
            </button>
          </div>
          ${error ? html`<div className="error">${error}</div>` : null}
        </section>

        <section className="panel">
          <div className="section-title-row">
            <h3>本轮结果</h3>
            ${assistantResult?.trace_id ? html`<span className="api-chip">Trace ${assistantResult.trace_id.slice(0, 8)}</span>` : null}
          </div>

          ${assistantResult
            ? html`
                <div className="review-summary-grid">
                  <div className="mini-metric">
                    <div className="eyebrow">问题类型</div>
                    <div className="review-summary-value">${displayLabel(assistantResult.intent)}</div>
                  </div>
                  <div className="mini-metric">
                    <div className="eyebrow">系统动作</div>
                    <div className="review-summary-value ${toneOf(assistantResult.next_action)}">
                      ${displayLabel(assistantResult.next_action)}
                    </div>
                  </div>
                  <div className="mini-metric">
                    <div className="eyebrow">置信度</div>
                    <div className="review-summary-value">${assistantResult.confidence}</div>
                  </div>
                  <div className="mini-metric">
                    <div className="eyebrow">结果形态</div>
                    <div className="review-summary-value">${assistantResult.next_action === "answer" ? "ֱӲο" : "Ҫ˹"}</div>
                  </div>
                </div>

                <div className="info-box">
                  <strong>回答</strong>
                  <div className="answer-box" style=${{ marginTop: "10px" }}>${assistantResult.answer}</div>
                </div>

                <div className="info-box">
                  <strong>引用证据</strong>
                  <${EvidencePanel} html=${html} citations=${genericCitations} />
                </div>

                <div className="info-box">
                  <strong>调试摘要</strong>
                  <pre className="code-block compact">${JSON.stringify(assistantResult.debug_summary || {}, null, 2)}</pre>
                </div>
              `
            : html`
                <div className="empty-box">
                  发出问题后，这里会展示单次回答、引用证据和调试摘要。
                </div>
              `}
        </section>
      </div>
    </div>
  `;
}

export function AuditPage({ html, traces, latestTraceId, refreshAll }) {
  const [traceId, setTraceId] = useState(latestTraceId || "");
  const [traceDetail, setTraceDetail] = useState(null);
  const [traceError, setTraceError] = useState("");
  const [traceQuery, setTraceQuery] = useState("");
  const [evalResult, setEvalResult] = useState(null);
  const [evalError, setEvalError] = useState("");

  useEffect(() => {
    if (latestTraceId) setTraceId(latestTraceId);
  }, [latestTraceId]);

  const filteredTraces = useMemo(() => {
    const keyword = traceQuery.trim().toLowerCase();
    if (!keyword) return traces;
    return traces.filter((item) =>
      `${item.query} ${item.intent} ${item.next_action}`.toLowerCase().includes(keyword),
    );
  }, [traceQuery, traces]);

  async function loadTrace() {
    try {
      setTraceError("");
      setTraceDetail(await apiGet(`/trace/${traceId}`));
    } catch (err) {
      setTraceError(err.message);
    }
  }

  async function runEval() {
    try {
      setEvalError("");
      const result = await apiPost("/eval/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case_ids: [], task_types: [], required_roles: [], knowledge_domains: [] }),
      });
      setEvalResult(result);
      refreshAll();
    } catch (err) {
      setEvalError(err.message);
    }
  }

  return html`
    <div>
      <div className="topbar">
        <div>
          <h2>Trace 与评测</h2>
          <p>在这里查看单次审查的执行链路，也可以运行离线评测观察召回、引用与异常情况。</p>
        </div>
      </div>

      <div className="audit-grid">
        <section className="panel">
          <h3>Trace 查询</h3>
          <div className="toolbar">
            <div style=${{ flex: 1 }}>
              <label className="label">Trace ID</label>
              <input className="field" value=${traceId} onInput=${(event) => setTraceId(event.target.value)} />
            </div>
            <button className="btn primary" onClick=${loadTrace} style=${{ alignSelf: "flex-end" }}>
              加载 Trace
            </button>
          </div>
          ${traceError ? html`<div className="error">${traceError}</div>` : null}

          <div className="section-title-row" style=${{ marginTop: "20px" }}>
            <h4>最近 Trace</h4>
          </div>
          <input
            className="field"
            value=${traceQuery}
            onInput=${(event) => setTraceQuery(event.target.value)}
            placeholder="按问题、意图或动作搜索"
          />
          <div className="list-gap"></div>
          ${filteredTraces.length
            ? html`
                <div className="stack-list">
                  ${filteredTraces.slice(0, 8).map(
                    (trace) => html`
                      <div className="activity-item" key=${trace.trace_id}>
                        <div className="activity-main">
                          <strong>${trace.query}</strong>
                          <div className="subtle">${displayLabel(trace.intent) || "未知意图"}</div>
                        </div>
                        <div className="activity-meta">
                          <span className="status-badge ${toneOf(trace.next_action)}">
                            ${displayLabel(trace.next_action) || "未知动作"}
                          </span>
                          <button className="btn ghost small" onClick=${() => setTraceId(trace.trace_id)}>
                            选中
                          </button>
                        </div>
                      </div>
                    `,
                  )}
                </div>
              `
            : html`<div className="empty-box">暂时没有可匹配的 Trace 记录。</div>`}
        </section>

        <section className="panel">
          <h3>评测中心</h3>
          <p className="muted">运行默认评测集，检查问答在采购场景中的召回、引用覆盖率和安全性表现。</p>
          <div className="button-row">
            <button className="btn primary" onClick=${runEval}>运行评测</button>
          </div>
          ${evalError ? html`<div className="error">${evalError}</div>` : null}
          ${evalResult
            ? html`
                <div className="metric-cluster">
                  ${Object.entries(evalResult.metrics || {}).map(
                    ([key, value]) => html`
                      <div className="mini-metric" key=${key}>
                        <span className="mini-label">${key}</span>
                        <strong>${value}</strong>
                      </div>
                    `,
                  )}
                </div>
              `
            : html`
                <div className="empty-box" style=${{ marginTop: "16px" }}>
                  还没有运行评测，点击上方按钮即可生成指标。
                </div>
              `}
        </section>
      </div>

      <section className="section-block">
        <div className="section-title-row"><h3>Trace 详情</h3></div>
        ${traceDetail
          ? html`
              <div className="trace-layout">
                <div className="panel">
                  <div className="status-line">
                    <span className="status-badge neutral">${displayLabel(traceDetail.intent)}</span>
                    <span className="status-badge ${toneOf(traceDetail.next_action)}">
                      ${displayLabel(traceDetail.next_action)}
                    </span>
                    <span className="api-chip">置信度 ${traceDetail.confidence}</span>
                  </div>
                  <div className="answer-box" style=${{ marginTop: "16px" }}>
                    ${traceDetail.final_answer}
                  </div>
                </div>
                <div className="panel">
                  <h4>调试摘要</h4>
                  <pre className="code-block">${JSON.stringify(traceDetail.debug_summary || {}, null, 2)}</pre>
                </div>
              </div>
              <div className="section-title-row" style=${{ marginTop: "20px" }}><h4>节点时间线</h4></div>
              <div className="timeline-list">
                ${(traceDetail.steps || []).map(
                  (step) => html`
                    <article className="timeline-card" key=${`${step.node_name}-${step.created_at}`}>
                      <div className="timeline-badge ${step.success ? "success" : "danger"}">
                        ${step.node_name}
                      </div>
                      <div className="timeline-body">
                        <div className="subtle">耗时 ${step.latency_ms} ms</div>
                        <p><strong>输入：</strong>${step.input_summary}</p>
                        <p><strong>输出：</strong>${step.output_summary}</p>
                      </div>
                    </article>
                  `,
                )}
              </div>
            `
          : html`
              <div className="empty-box">
                输入 Trace ID 后点击“加载 Trace”，这里会显示整次审查的节点过程。
              </div>
            `}
      </section>
    </div>
  `;
}
