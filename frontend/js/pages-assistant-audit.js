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
  const genericCitations = assistantResult?.citations || [];
  const agentCitations = assistantResult?.review?.citations || [];

  useEffect(() => {
    const nextTaskKey = `${assistantTask?.kind || "generic"}:${assistantTask?.projectId || ""}:${assistantTask?.linkedVendorId || ""}`;
    if (!previousTaskKeyRef.current) {
      previousTaskKeyRef.current = nextTaskKey;
      return;
    }
    if (previousTaskKeyRef.current !== nextTaskKey) {
      setError("");
      if (!isProcurementAgentMode) {
        setAgentFocus("");
      }
      if (setAssistantResult) setAssistantResult(null);
      previousTaskKeyRef.current = nextTaskKey;
    }
  }, [assistantTask?.kind, assistantTask?.projectId, assistantTask?.linkedVendorId, isProcurementAgentMode, setAssistantResult]);

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
      const payload = await apiPost(`/projects/${assistantTask.projectId}/procurement-agent-review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...assistantTask.vendorDraft,
          focus_points: agentFocus,
          top_k: 6,
        }),
      });
      if (setAssistantResult) setAssistantResult(payload);
      onTraceCreated(payload.review.trace_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  if (currentUser?.role === "procurement" && !isProcurementAgentMode) {
    return html`
      <div>
        <div className="topbar">
          <div>
            <h2>供应商 Agent 审查</h2>
            <p>采购助手已改成任务驱动模式。请先从采购执行页面带入当前项目和供应商草稿，再在这里启动一轮自动审查。</p>
          </div>
        </div>

        <div className="center-panel" style=${{ maxWidth: "760px" }}>
          <div className="empty-box">
            当前没有待执行的供应商审查任务。回到采购执行页面，填写好供应商信息后点击“带着这些信息去审查助手”即可。
          </div>
          <div className="button-row" style=${{ marginTop: "16px" }}>
            <button className="btn primary" onClick=${() => onNavigate && onNavigate("projects")}>返回采购执行</button>
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
            <p>这里不再是普通问答框。系统会自动读取当前项目和供应商草稿，主动执行一轮准入审查，再给出是否建议绑定、风险点和待补材料。</p>
          </div>
        </div>

        <div className="assistant-layout">
          <section className="panel">
            <div className="section-title-row">
              <h3>审查任务</h3>
              <button className="btn ghost small" onClick=${() => onNavigate && onNavigate("projects")}>
                返回采购执行
              </button>
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

            <label className="label">补充关注点</label>
            <textarea
              className="field textarea-medium"
              value=${agentFocus}
              onInput=${(event) => setAgentFocus(event.target.value)}
              placeholder="可选，例如：重点关注客户数据处理、SaaS 交付能力、是否还缺安全材料。"
            ></textarea>

            <div className="info-box">
              <strong>Agent 会自动做什么</strong>
              <div className="stack-list" style=${{ marginTop: "10px" }}>
                <div>1. 读取当前项目背景和供应商草稿</div>
                <div>2. 检索本地供应商准入制度与采购流程知识库</div>
                <div>3. 判断是否建议继续绑定该供应商</div>
                <div>4. 输出风险点、待补材料和下一步动作</div>
              </div>
            </div>

            <div className="button-row">
              <button className="btn primary" onClick=${runProcurementAgentReview} disabled=${loading}>
                ${loading ? "正在执行 Agent 审查..." : "开始 Agent 审查"}
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
                      <div className="eyebrow">推荐结论</div>
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

                  <div className="info-box">
                    <strong>Agent 原始回答</strong>
                    <div className="answer-box" style=${{ marginTop: "10px" }}>${assistantResult.review.answer}</div>
                  </div>

                  <div className="info-box">
                    <strong>引用证据</strong>
                    <${EvidencePanel} html=${html} citations=${agentCitations} />
                  </div>

                  <div className="info-box">
                    <strong>Agent 调试摘要</strong>
                    <pre className="code-block compact">${JSON.stringify(assistantResult.review.debug_summary || {}, null, 2)}</pre>
                  </div>
                `
              : html`
                  <div className="empty-box">
                    点击左侧“开始 Agent 审查”后，这里会展示结构化准入结论、风险点、待补问题和引用证据。
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
          <p>这里已经切回单次问答模式。每次发送都会独立生成一个答案，不再保留多轮会话上下文。</p>
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
            placeholder="例如：正式签署前，这个项目还缺哪些审批或归档动作？"
          ></textarea>

          <div className="button-row">
            <button className="btn primary" onClick=${submitSingleAnswer} disabled=${loading || !draftQuestion.trim()}>
              ${loading ? "正在生成答案..." : "生成单次答案"}
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
                    <div className="review-summary-value">${assistantResult.next_action === "answer" ? "可直接参考" : "需人工补充"}</div>
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
          <p>
            在这里查看单次审查的全部执行过程，也可以运行离线评测，看系统的召回、引用和异常情况。
          </p>
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
          <p className="muted">
            运行默认评测集，检查问答在采购场景下的召回、引用覆盖率和安全性表现。
          </p>
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
