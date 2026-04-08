import React, { useEffect, useMemo, useState } from "https://esm.sh/react@18.3.1";

import { DEMO_QUESTIONS, ROLE_OPTIONS, displayLabel, toneOf } from "./config.js";
import { apiGet, apiPost } from "./api.js";

export function AssistantPage({ html, draftQuestion, setDraftQuestion, onTraceCreated }) {
  const [role, setRole] = useState("employee");
  const [sessionId, setSessionId] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit() {
    try {
      setLoading(true);
      setError("");
      setResult(null);
      const payload = await apiPost("/chat/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: draftQuestion,
          user_role: role,
          top_k: 5,
          session_id: sessionId || null,
        }),
      });
      setSessionId(payload.session_id);
      setResult(payload);
      onTraceCreated(payload.trace_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const citations = result?.citations || [];

  return html`
    <div>
      <div className="topbar">
        <div>
          <h2>\u5ba1\u67e5\u52a9\u624b</h2>
          <p>
            \u9002\u5408\u505a\u5355\u6b21\u5ba1\u67e5\u95ee\u7b54\u3002\u4f60\u53ef\u4ee5\u76f4\u63a5\u95ee\u51c6\u5165\u6e05\u5355\u3001\u5b89\u5168\u8bc4\u5ba1\u3001\u5408\u540c\u7ea2\u7ebf\u5bf9\u6bd4\u548c\u5ba1\u6279\u8def\u5f84\u95ee\u9898\uff0c\u53f3\u4fa7\u4f1a\u8fd4\u56de\u7b54\u6848\u3001\u5f15\u7528\u548c\u8c03\u8bd5\u4fe1\u606f\u3002
          </p>
        </div>
      </div>

      <div className="assistant-layout">
        <section className="panel">
          <h3>\u8f93\u5165\u5ba1\u67e5\u95ee\u9898</h3>
          <label className="label">\u5f53\u524d\u89d2\u8272</label>
          <select className="field" value=${role} onChange=${(event) => setRole(event.target.value)}>
            ${ROLE_OPTIONS.map(
              (item) => html`<option key=${item.value} value=${item.value}>${item.label}</option>`,
            )}
          </select>

          <label className="label">\u95ee\u9898\u5185\u5bb9</label>
          <textarea
            className="field textarea-large"
            value=${draftQuestion}
            onInput=${(event) => setDraftQuestion(event.target.value)}
          ></textarea>

          <div className="button-row">
            <button className="btn primary" onClick=${submit} disabled=${loading || !draftQuestion.trim()}>
              <i data-lucide=${loading ? "loader" : "play"} style=${{ width: "15px", height: "15px" }}></i>
              ${loading ? "\u6b63\u5728\u5ba1\u67e5..." : "\u5f00\u59cb\u5ba1\u67e5"}
            </button>
          </div>

          ${error ? html`<div className="error">${error}</div>` : null}

          <div className="question-grid">
            ${DEMO_QUESTIONS.map(
              (item) => html`
                <button className="question-card" key=${item} onClick=${() => setDraftQuestion(item)}>
                  ${item}
                </button>
              `,
            )}
          </div>
        </section>

        <section className="panel result-panel">
          <h3>\u5ba1\u67e5\u7ed3\u679c</h3>
          ${loading
            ? html`
                <div className="empty-box">
                  <div className="loading-ring" style=${{ margin: "0 auto 14px" }}></div>
                  <div>\u7cfb\u7edf\u6b63\u5728\u68c0\u7d22\u91c7\u8d2d\u77e5\u8bc6\u5e93\u5e76\u751f\u6210\u5ba1\u67e5\u56de\u590d...</div>
                </div>
              `
            : result
              ? html`
                  <div className="status-line">
                    <span className="status-badge neutral">${displayLabel(result.intent)}</span>
                    <span className="status-badge ${toneOf(result.next_action)}">
                      ${displayLabel(result.next_action)}
                    </span>
                    <span className="api-chip">\u7f6e\u4fe1\u5ea6 ${result.confidence}</span>
                  </div>
                  <div className="answer-box">${result.answer || "\u6682\u65e0\u56de\u590d\u5185\u5bb9"}</div>

                  <div className="section-title-row" style=${{ marginTop: "20px" }}>
                    <h4>\u5f15\u7528\u8bc1\u636e</h4>
                  </div>
                  ${citations.length
                    ? html`
                        <div className="citation-grid">
                          ${citations.map(
                            (citation) => html`
                              <article className="citation-card" key=${`${citation.document_id}-${citation.location}`}>
                                <strong>${citation.document_title}</strong>
                                <div className="subtle">${citation.location}</div>
                                <p>${citation.snippet}</p>
                                <div className="mono">\u76f8\u5173\u5ea6 ${citation.score}</div>
                              </article>
                            `,
                          )}
                        </div>
                      `
                    : html`
                        <div className="empty-box">
                          \u8fd9\u6b21\u56de\u590d\u6682\u65f6\u6ca1\u6709\u8fd4\u56de\u53ef\u7528\u5f15\u7528\uff0c\u8fd9\u901a\u5e38\u610f\u5473\u7740\u8bc1\u636e\u4e0d\u8db3\u6216\u9700\u8981\u8865\u5145\u6587\u6863\u3002
                        </div>
                      `}
                `
              : html`
                  <div className="empty-box">
                    \u5de6\u4fa7\u8f93\u5165\u95ee\u9898\u540e\u70b9\u51fb\u201c\u5f00\u59cb\u5ba1\u67e5\u201d\uff0c\u53f3\u4fa7\u4f1a\u5728\u8fd9\u91cc\u663e\u793a\u56de\u590d\u3001\u5f15\u7528\u548c\u8c03\u8bd5\u4fe1\u606f\u3002
                  </div>
                `}
        </section>
      </div>

      ${result
        ? html`
            <section className="section-block">
              <div className="section-title-row"><h3>\u8c03\u8bd5\u6458\u8981</h3></div>
              <div className="debug-grid">
                <div className="panel">
                  <h4>\u68c0\u7d22\u8ba1\u5212</h4>
                  <pre className="code-block">${JSON.stringify(
                    result.debug_summary?.retrieval_plan || {},
                    null,
                    2,
                  )}</pre>
                </div>
                <div className="panel">
                  <h4>\u68c0\u7d22\u6267\u884c</h4>
                  <pre className="code-block">${JSON.stringify(
                    result.debug_summary?.retrieval || {},
                    null,
                    2,
                  )}</pre>
                </div>
                <div className="panel">
                  <h4>\u5bf9\u6bd4\u4e0e\u5f15\u7528\u6821\u9a8c</h4>
                  <pre className="code-block">${JSON.stringify(
                    {
                      comparison: result.debug_summary?.comparison_view || {},
                      verification: result.debug_summary?.verification || {},
                    },
                    null,
                    2,
                  )}</pre>
                </div>
              </div>
            </section>
          `
        : null}
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
          <h2>Trace \u4e0e\u8bc4\u6d4b</h2>
          <p>
            \u5728\u8fd9\u91cc\u67e5\u770b\u5355\u6b21\u5ba1\u67e5\u7684\u5168\u90e8\u6267\u884c\u8fc7\u7a0b\uff0c\u4e5f\u53ef\u4ee5\u8fd0\u884c\u79bb\u7ebf\u8bc4\u6d4b\uff0c\u770b\u7cfb\u7edf\u7684\u53ec\u56de\u3001\u5f15\u7528\u548c\u5f02\u5e38\u60c5\u51b5\u3002
          </p>
        </div>
      </div>

      <div className="audit-grid">
        <section className="panel">
          <h3>Trace \u67e5\u8be2</h3>
          <div className="toolbar">
            <div style=${{ flex: 1 }}>
              <label className="label">Trace ID</label>
              <input className="field" value=${traceId} onInput=${(event) => setTraceId(event.target.value)} />
            </div>
            <button className="btn primary" onClick=${loadTrace} style=${{ alignSelf: "flex-end" }}>
              \u52a0\u8f7d Trace
            </button>
          </div>
          ${traceError ? html`<div className="error">${traceError}</div>` : null}

          <div className="section-title-row" style=${{ marginTop: "20px" }}>
            <h4>\u6700\u8fd1 Trace</h4>
          </div>
          <input
            className="field"
            value=${traceQuery}
            onInput=${(event) => setTraceQuery(event.target.value)}
            placeholder="\u6309\u95ee\u9898\u3001\u610f\u56fe\u6216\u52a8\u4f5c\u641c\u7d22"
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
                          <div className="subtle">${displayLabel(trace.intent) || "\u672a\u77e5\u610f\u56fe"}</div>
                        </div>
                        <div className="activity-meta">
                          <span className="status-badge ${toneOf(trace.next_action)}">
                            ${displayLabel(trace.next_action) || "\u672a\u77e5\u52a8\u4f5c"}
                          </span>
                          <button className="btn ghost small" onClick=${() => setTraceId(trace.trace_id)}>
                            \u9009\u4e2d
                          </button>
                        </div>
                      </div>
                    `,
                  )}
                </div>
              `
            : html`<div className="empty-box">\u6682\u65f6\u6ca1\u6709\u53ef\u5339\u914d\u7684 Trace \u8bb0\u5f55\u3002</div>`}
        </section>

        <section className="panel">
          <h3>\u8bc4\u6d4b\u4e2d\u5fc3</h3>
          <p className="muted">
            \u8fd0\u884c\u9ed8\u8ba4\u8bc4\u6d4b\u96c6\uff0c\u68c0\u67e5\u95ee\u7b54\u5728\u91c7\u8d2d\u573a\u666f\u4e0b\u7684\u53ec\u56de\u3001\u5f15\u7528\u8986\u76d6\u7387\u548c\u5b89\u5168\u6027\u8868\u73b0\u3002
          </p>
          <div className="button-row">
            <button className="btn primary" onClick=${runEval}>\u8fd0\u884c\u8bc4\u6d4b</button>
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
                  \u8fd8\u6ca1\u6709\u8fd0\u884c\u8bc4\u6d4b\uff0c\u70b9\u51fb\u4e0a\u65b9\u6309\u94ae\u5373\u53ef\u751f\u6210\u6307\u6807\u3002
                </div>
              `}
        </section>
      </div>

      <section className="section-block">
        <div className="section-title-row"><h3>Trace \u8be6\u60c5</h3></div>
        ${traceDetail
          ? html`
              <div className="trace-layout">
                <div className="panel">
                  <div className="status-line">
                    <span className="status-badge neutral">${displayLabel(traceDetail.intent)}</span>
                    <span className="status-badge ${toneOf(traceDetail.next_action)}">
                      ${displayLabel(traceDetail.next_action)}
                    </span>
                    <span className="api-chip">\u7f6e\u4fe1\u5ea6 ${traceDetail.confidence}</span>
                  </div>
                  <div className="answer-box" style=${{ marginTop: "16px" }}>
                    ${traceDetail.final_answer}
                  </div>
                </div>
                <div className="panel">
                  <h4>\u8c03\u8bd5\u6458\u8981</h4>
                  <pre className="code-block">${JSON.stringify(traceDetail.debug_summary || {}, null, 2)}</pre>
                </div>
              </div>
              <div className="section-title-row" style=${{ marginTop: "20px" }}><h4>\u8282\u70b9\u65f6\u95f4\u7ebf</h4></div>
              <div className="timeline-list">
                ${(traceDetail.steps || []).map(
                  (step) => html`
                    <article className="timeline-card" key=${`${step.node_name}-${step.created_at}`}>
                      <div className="timeline-badge ${step.success ? "success" : "danger"}">
                        ${step.node_name}
                      </div>
                      <div className="timeline-body">
                        <div className="subtle">\u8017\u65f6 ${step.latency_ms} ms</div>
                        <p><strong>\u8f93\u5165\uff1a</strong>${step.input_summary}</p>
                        <p><strong>\u8f93\u51fa\uff1a</strong>${step.output_summary}</p>
                      </div>
                    </article>
                  `,
                )}
              </div>
            `
          : html`
              <div className="empty-box">
                \u8f93\u5165 Trace ID \u540e\u70b9\u51fb\u201c\u52a0\u8f7d Trace\u201d\uff0c\u8fd9\u91cc\u4f1a\u663e\u793a\u6574\u6b21\u5ba1\u67e5\u7684\u8282\u70b9\u8fc7\u7a0b\u3002
              </div>
            `}
      </section>
    </div>
  `;
}
