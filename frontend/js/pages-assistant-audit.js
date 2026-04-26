import React, { useEffect, useState } from "https://esm.sh/react@18.3.1";
import { DEMO_QUESTIONS, displayLabel, toneOf } from "./config.js";
import { apiGet, apiPost } from "./api.js";

function StatusBadge({ html, value }) {
  if (!value) return null;
  return html`<span className="status-badge ${toneOf(value)}">${displayLabel(value)}</span>`;
}

function ReviewSummaryCard({ html, title, assessment }) {
  if (!assessment) return null;
  const isProcurementReview = assessment.review_kind === "procurement_agent_review";
  return html`
    <div className="info-box">
      <strong>${title}</strong>
      <div className="stack-list" style=${{ marginTop: "10px" }}>
        <div className="subtle">${assessment.fit_reason || assessment.summary || "-"}</div>
        ${isProcurementReview && assessment.blocking_issues?.length
          ? html`
              <div>
                <strong>不适配或待警惕的点</strong>
                <div className="stack-list" style=${{ marginTop: "8px" }}>
                  ${assessment.blocking_issues.map((item) => html`<div className="inline-alert info" key=${item}>${item}</div>`)}
                </div>
              </div>
            `
          : null}
        ${isProcurementReview && assessment.risk_flags?.length
          ? html`
              <div>
                <strong>风险提示</strong>
                <div className="stack-list" style=${{ marginTop: "8px" }}>
                  ${assessment.risk_flags.map((item) => html`<div className="inline-alert warn" key=${item}>${item}</div>`)}
                </div>
              </div>
            `
          : null}
        ${assessment.missing_materials?.length
          ? html`
              <div>
                <strong>缺失信息</strong>
                <div className="stack-list" style=${{ marginTop: "8px" }}>
                  ${assessment.missing_materials.map((item) => html`<div key=${item}>${item}</div>`)}
                </div>
              </div>
            `
          : null}
        ${assessment.check_items?.length
          ? html`
              <div className="stack-list">
                ${assessment.check_items.map((item) => html`
                  <div className="activity-item" key=${`${item.label}-${item.status}`}>
                    <div className="activity-main">
                      <strong>${item.label}</strong>
                      <div className="subtle">${item.detail}</div>
                    </div>
                    <div className="activity-meta">
                      <${StatusBadge} html=${html} value=${item.status} />
                    </div>
                  </div>
                `)}
              </div>
            `
          : null}
      </div>
    </div>
  `;
}

function EvidencePanel({ html, citations }) {
  if (!citations?.length) {
    return html`<div className="empty-box compact">暂无引用证据。</div>`;
  }
  return html`
    <div className="stack-list">
      ${citations.map((citation, index) => html`
        <div className="info-box" key=${`${citation.document_title || "doc"}-${citation.location || index}`}>
          <strong>${citation.document_title || "未命名文档"}</strong>
          <div className="subtle">${citation.location || "-"}</div>
          <div style=${{ marginTop: "8px" }}>${citation.snippet || "-"}</div>
        </div>
      `)}
    </div>
  `;
}

function ToolTracePanel({ html, toolCalls }) {
  if (!toolCalls?.length) return null;
  return html`
    <div className="info-box">
      <strong>工具调用轨迹</strong>
      <div className="stack-list" style=${{ marginTop: "10px" }}>
        ${toolCalls.map((item, index) => html`
          <div className="activity-item" key=${`${item.tool_name || "tool"}-${index}`}>
            <div className="activity-main">
              <strong>${item.tool_name || "tool"}</strong>
              <div className="subtle">${item.purpose || item.output_summary || item.input_summary || "-"}</div>
            </div>
          </div>
        `)}
      </div>
    </div>
  `;
}

function RequirementPanel({ html, checks }) {
  if (!checks?.length) return null;
  return html`
    <div className="info-box">
      <strong>预检与缺失项</strong>
      <div className="stack-list" style=${{ marginTop: "10px" }}>
        ${checks.map((item) => html`
          <div className="activity-item" key=${item.key || item.label}>
            <div className="activity-main">
              <strong>${item.label}</strong>
              <div className="subtle">${item.detail || "-"}</div>
            </div>
            <div className="activity-meta">
              <${StatusBadge} html=${html} value=${item.status} />
            </div>
          </div>
        `)}
      </div>
    </div>
  `;
}

function ProcurementTaskCard({ html, task }) {
  const draft = task?.vendorDraft || {};
  return html`
    <div className="info-box">
      <strong>供应商核心字段</strong>
      <div className="stack-list" style=${{ marginTop: "10px" }}>
        <div className="subtle">供应商：${draft.vendor_name || "-"}</div>
        <div className="subtle">来源链接：${draft.source_url || "未填写"}</div>
        <div className="subtle">联系邮箱：${draft.contact_email || "未填写"}</div>
        <div className="subtle">报价/预计合作金额：${Number(draft.quoted_amount || 0) > 0 ? `${Number(draft.quoted_amount || 0).toLocaleString("zh-CN")} CNY` : "未填写"}</div>
        <div className="subtle">处理公司/客户数据：${draft.handles_company_data ? "是" : "否"}</div>
        <div className="subtle">需要系统对接：${draft.requires_system_integration ? "是" : "否"}</div>
        <div className="subtle">产品/服务简介：${draft.profile_summary || "未填写"}</div>
        <div className="subtle">采购说明：${draft.procurement_notes || "未填写"}</div>
      </div>
    </div>
  `;
}

function LegalTaskCard({ html, task }) {
  return html`
    <div className="info-box">
      <strong>法务审查任务</strong>
      <div className="stack-list" style=${{ marginTop: "10px" }}>
        <div className="subtle">项目：${task?.projectTitle || "-"}</div>
        <div className="subtle">供应商：${task?.vendorName || "-"}</div>
        <div className="subtle">审查说明：${task?.query || "按默认法务审查模板执行"}</div>
      </div>
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

  const isProcurementMode = assistantTask?.kind === "procurement_vendor_review";
  const isLegalMode = assistantTask?.kind === "legal_contract_review";

  useEffect(() => {
    if (!agentFocus && assistantTask?.focusPoints) {
      setAgentFocus(assistantTask.focusPoints);
    }
  }, [assistantTask?.focusPoints]);

  async function runGenericAssistant() {
    try {
      setLoading(true);
      setError("");
      const payload = await apiPost("/chat/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: draftQuestion || "",
          user_role: currentUser?.role || "admin",
          top_k: 5,
          task_mode: "knowledge_qa",
        }),
      });
      setAssistantResult?.(payload);
      if (payload.trace_id) onTraceCreated?.(payload.trace_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function runProcurementAgentReview() {
    if (!assistantTask?.projectId || !assistantTask?.vendorDraft) return;
    try {
      setLoading(true);
      setError("");
      const payload = await apiPost(`/projects/${assistantTask.projectId}/procurement-agent-review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...assistantTask.vendorDraft,
          focus_points: agentFocus || assistantTask.focusPoints || "",
          top_k: 5,
        }),
      });
      setAssistantResult?.(payload);
      setAssistantTask?.((current) => ({
        ...(current || {}),
        focusPoints: agentFocus || current?.focusPoints || "",
      }));
      if (payload.review?.trace_id) onTraceCreated?.(payload.review.trace_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function runLegalReview() {
    if (!assistantTask?.projectId) return;
    try {
      setLoading(true);
      setError("");
      const payload = await apiPost(`/projects/${assistantTask.projectId}/legal/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: agentFocus || assistantTask.query || "",
          top_k: 5,
        }),
      });
      setAssistantResult?.(payload);
      if (payload.review?.trace_id) onTraceCreated?.(payload.review.trace_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function submitLegalDecision(decision) {
    if (!assistantTask?.projectId) return;
    try {
      setLoading(true);
      setError("");
      await apiPost(`/projects/${assistantTask.projectId}/legal-decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          decision,
          actor_role: "legal",
          reason: decision === "approve" ? "法务审查通过，提交管理员签署。" : "法务审查认为当前合同条件不宜继续推进。",
        }),
      });
      setAssistantResult?.(null);
      onNavigate?.("projects");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!assistantTask?.autorun || loading || assistantResult) return;
    if (isProcurementMode) {
      setAssistantTask?.((current) => (current ? { ...current, autorun: false } : current));
      runProcurementAgentReview();
      return;
    }
    if (isLegalMode) {
      setAssistantTask?.((current) => (current ? { ...current, autorun: false } : current));
      runLegalReview();
    }
  }, [assistantTask?.autorun, assistantResult, isProcurementMode, isLegalMode, loading]);

  if (isProcurementMode) {
    return html`
      <div>
        <div className="section-title-row">
          <h3>供应商匹配审查助手</h3>
          <button className="btn ghost small" onClick=${() => onNavigate?.("projects")}>返回采购执行</button>
        </div>

        <div className="knowledge-layout" style=${{ marginTop: "20px" }}>
          <section className="panel">
            <div className="stack-list">
              <div className="info-box">
                <strong>当前项目</strong>
                <div className="stack-list" style=${{ marginTop: "10px" }}>
                  <div className="subtle">项目名称：${assistantTask?.projectTitle || "-"}</div>
                  <div className="subtle">项目编号：${assistantTask?.projectId || "-"}</div>
                </div>
              </div>
              <${ProcurementTaskCard} html=${html} task=${assistantTask} />
              <label className="label">采购关注点</label>
              <textarea
                className="field textarea-medium"
                value=${agentFocus}
                onInput=${(event) => setAgentFocus(event.target.value)}
                placeholder="选填，例如：重点关注预算匹配、数据处理、系统对接复杂度等。"
              ></textarea>
              <div className="button-row">
                <button className="btn primary" onClick=${runProcurementAgentReview} disabled=${loading}>
                  ${loading ? "审查中..." : "重新审查当前供应商"}
                </button>
              </div>
              ${error ? html`<div className="error">${error}</div>` : null}
            </div>
          </section>

          <section className="panel">
            <div className="section-title-row">
              <h3>审查结果</h3>
              ${assistantResult?.review?.trace_id ? html`<span className="api-chip">Trace ${assistantResult.review.trace_id.slice(0, 8)}</span>` : null}
            </div>
            ${assistantResult
              ? html`
                  <div className="stack-list">
                    <${ReviewSummaryCard} html=${html} title="供应商适配度结论" assessment=${assistantResult.assessment} />
                    <${RequirementPanel} html=${html} checks=${assistantResult.requirement_checks} />
                    <div className="info-box">
                      <strong>Agent 原始回答</strong>
                      <div className="answer-box" style=${{ marginTop: "10px" }}>${assistantResult.review?.answer || "-"}</div>
                    </div>
                    <${EvidencePanel} html=${html} citations=${assistantResult.review?.citations || []} />
                    <${ToolTracePanel} html=${html} toolCalls=${assistantResult.review?.tool_calls || []} />
                  </div>
                `
              : html`<div className="empty-box">两侧字段补齐后，系统会自动生成供应商适配度结论。</div>`}
          </section>
        </div>
      </div>
    `;
  }

  if (isLegalMode) {
    const assessment = assistantResult?.assessment || assistantTask?.latestAssessment || null;
    return html`
      <div>
        <div className="section-title-row">
          <h3>法务合同审查助手</h3>
          <button className="btn ghost small" onClick=${() => onNavigate?.("projects")}>返回法务工作台</button>
        </div>

        <div className="knowledge-layout" style=${{ marginTop: "20px" }}>
          <section className="panel">
            <div className="stack-list">
              <${LegalTaskCard} html=${html} task=${assistantTask} />
              <label className="label">审查关注点</label>
              <textarea
                className="field textarea-medium"
                value=${agentFocus || assistantTask?.query || ""}
                onInput=${(event) => setAgentFocus(event.target.value)}
                placeholder="例如：重点关注责任限制、赔偿责任、解约条件、保密义务。"
              ></textarea>
              <div className="button-row">
                <button className="btn primary" onClick=${runLegalReview} disabled=${loading}>
                  ${loading ? "审查中..." : "重新审查合同"}
                </button>
              </div>
              ${assessment
                ? html`
                    <div className="button-row">
                      <button className="btn primary" onClick=${() => submitLegalDecision("approve")} disabled=${loading}>提交签署</button>
                      <button className="btn secondary" onClick=${() => submitLegalDecision("return")} disabled=${loading}>退回采购</button>
                    </div>
                  `
                : null}
              ${error ? html`<div className="error">${error}</div>` : null}
            </div>
          </section>

          <section className="panel">
            <div className="section-title-row">
              <h3>审查结果</h3>
              ${assistantResult?.review?.trace_id ? html`<span className="api-chip">Trace ${assistantResult.review.trace_id.slice(0, 8)}</span>` : null}
            </div>
            ${assessment
              ? html`
                  <div className="stack-list">
                    <${ReviewSummaryCard} html=${html} title="法务结构化结论" assessment=${assessment} />
                    ${assistantResult?.review?.answer
                      ? html`
                          <div className="info-box">
                            <strong>Agent 原始回答</strong>
                            <div className="answer-box" style=${{ marginTop: "10px" }}>${assistantResult.review.answer}</div>
                          </div>
                        `
                      : null}
                    <${EvidencePanel} html=${html} citations=${assistantResult?.review?.citations || []} />
                    <${ToolTracePanel} html=${html} toolCalls=${assistantResult?.review?.tool_calls || []} />
                  </div>
                `
              : html`<div className="empty-box">上传两份合同后，系统会自动开始法务条款审查。</div>`}
          </section>
        </div>
      </div>
    `;
  }

  return html`
    <div>
      <div className="section-title-row">
        <h3>知识审查助手</h3>
      </div>

      <div className="knowledge-layout" style=${{ marginTop: "20px" }}>
        <section className="panel">
          <div className="stack-list">
            <strong>推荐问题</strong>
            <div className="stack-list">
              ${DEMO_QUESTIONS.map((item) => html`
                <button className="question-card" key=${item} onClick=${() => setDraftQuestion?.(item)}>${item}</button>
              `)}
            </div>

            <label className="label">输入问题</label>
            <textarea
              className="field textarea-medium"
              value=${draftQuestion || ""}
              onInput=${(event) => setDraftQuestion?.(event.target.value)}
              placeholder="输入一个和采购、法务或流程制度有关的问题。"
            ></textarea>

            <div className="button-row">
              <button className="btn primary" onClick=${runGenericAssistant} disabled=${loading}>
                ${loading ? "查询中..." : "开始查询"}
              </button>
            </div>
            ${error ? html`<div className="error">${error}</div>` : null}
          </div>
        </section>

        <section className="panel">
          <div className="section-title-row">
            <h3>回答结果</h3>
            ${assistantResult?.trace_id ? html`<span className="api-chip">Trace ${assistantResult.trace_id.slice(0, 8)}</span>` : null}
          </div>
          ${assistantResult
            ? html`
                <div className="stack-list">
                  <div className="info-box">
                    <strong>模型回答</strong>
                    <div className="answer-box" style=${{ marginTop: "10px" }}>${assistantResult.answer || "-"}</div>
                  </div>
                  <${EvidencePanel} html=${html} citations=${assistantResult.citations || []} />
                </div>
              `
            : html`<div className="empty-box">输入问题后即可看到带引用的回答。</div>`}
        </section>
      </div>
    </div>
  `;
}

export function AuditPage({ html, traces, latestTraceId, refreshAll }) {
  const [traceId, setTraceId] = useState(latestTraceId || "");
  const [traceDetail, setTraceDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadTrace(targetId) {
    if (!targetId) return;
    try {
      setLoading(true);
      setError("");
      const payload = await apiGet(`/trace/${targetId}`);
      setTraceDetail(payload);
      setTraceId(targetId);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (latestTraceId && latestTraceId !== traceId) {
      loadTrace(latestTraceId);
      return;
    }
    if (!traceId && traces?.[0]?.trace_id) {
      loadTrace(traces[0].trace_id);
    }
  }, [latestTraceId, traces?.[0]?.trace_id]);

  return html`
    <div>
      <div className="section-title-row">
        <h3>审计评测</h3>
        <button className="btn ghost small" onClick=${refreshAll}>刷新</button>
      </div>

      <div className="knowledge-layout" style=${{ marginTop: "20px" }}>
        <section className="panel">
          <strong>最近 Trace</strong>
          <div className="stack-list" style=${{ marginTop: "12px" }}>
            ${(traces || []).length
              ? traces.map((item) => html`
                  <button
                    className=${traceId === item.trace_id ? "project-list-item active" : "project-list-item"}
                    key=${item.trace_id}
                    onClick=${() => loadTrace(item.trace_id)}
                  >
                    <div className="activity-main">
                      <strong>${displayLabel(item.task_mode || item.intent)}</strong>
                      <div className="subtle">${item.query}</div>
                    </div>
                    <div className="activity-meta">
                      <${StatusBadge} html=${html} value=${item.next_action} />
                    </div>
                  </button>
                `)
              : html`<div className="empty-box">当前没有可查看的 Trace。</div>`}
          </div>
        </section>

        <section className="panel">
          <div className="section-title-row">
            <h3>Trace 详情</h3>
            ${traceDetail?.trace_id ? html`<span className="api-chip">Trace ${traceDetail.trace_id.slice(0, 8)}</span>` : null}
          </div>
          ${loading
            ? html`<div className="empty-box">正在加载 Trace 详情...</div>`
            : error
              ? html`<div className="error">${error}</div>`
              : traceDetail
                ? html`
                    <div className="stack-list">
                      <div className="info-box">
                        <strong>基础信息</strong>
                        <div className="stack-list" style=${{ marginTop: "10px" }}>
                          <div className="subtle">任务模式：${displayLabel(traceDetail.task_mode || traceDetail.intent)}</div>
                          <div className="subtle">下一步动作：${displayLabel(traceDetail.next_action)}</div>
                          <div className="subtle">置信度：${traceDetail.confidence}</div>
                          <div className="subtle">Query：${traceDetail.query}</div>
                        </div>
                      </div>
                      <div className="info-box">
                        <strong>最终回答</strong>
                        <div className="answer-box" style=${{ marginTop: "10px" }}>${traceDetail.final_answer || "-"}</div>
                      </div>
                      ${traceDetail.steps?.length
                        ? html`
                            <div className="info-box">
                              <strong>执行步骤</strong>
                              <div className="stack-list" style=${{ marginTop: "10px" }}>
                                ${traceDetail.steps.map((step, index) => html`
                                  <div className="activity-item" key=${`${step.node_name || "step"}-${index}`}>
                                    <div className="activity-main">
                                      <strong>${step.node_name || `step-${index + 1}`}</strong>
                                      <div className="subtle">${step.summary || step.detail || "-"}</div>
                                    </div>
                                  </div>
                                `)}
                              </div>
                            </div>
                          `
                        : null}
                      <div className="info-box">
                        <strong>调试摘要</strong>
                        <pre className="code-block compact">${JSON.stringify(traceDetail.debug_summary || {}, null, 2)}</pre>
                      </div>
                    </div>
                  `
                : html`<div className="empty-box">请选择一条 Trace 查看详情。</div>`}
        </section>
      </div>
    </div>
  `;
}
