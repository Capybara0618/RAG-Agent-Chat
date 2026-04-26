import React, { useEffect, useState } from "https://esm.sh/react@18.3.1";

import { DEMO_FILES, DEMO_QUESTIONS, displayLabel, toneOf } from "./config.js";
import { apiGet, apiPost, openEventStream } from "./api.js";
import { ActivityList, StatCard } from "./components.js";

function formatCurrency(amount, currency) {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: currency || "CNY",
    maximumFractionDigits: 0,
  }).format(amount || 0);
}

export function OverviewPage({
  html,
  currentUser,
  sources,
  tasks,
  traces,
  cases,
  projects,
  setPage,
  openProjectWorkspace,
  setDraftQuestion,
}) {
  const safeSources = Array.isArray(sources) ? sources : [];
  const safeTasks = Array.isArray(tasks) ? tasks : [];
  const safeTraces = Array.isArray(traces) ? traces : [];
  const safeCases = Array.isArray(cases) ? cases : [];
  const safeProjects = Array.isArray(projects) ? projects : [];

  const indexedSources = safeSources.filter((item) => item.status === "indexed").length;
  const runningTasks = safeTasks.filter((item) => ["uploaded", "indexing"].includes(item.status)).length;
  const failedTraces = safeTraces.filter((item) => item.has_failure).length;
  const compareCases = safeCases.filter((item) => item.task_type === "compare").length;
  const activeProjects = safeProjects.filter((item) => item.status === "active").length;
  const procurementPendingProjects = safeProjects.filter((item) => item.status === "active" && item.current_stage === "procurement_sourcing");
  const businessDraftProjects = safeProjects.filter((item) => item.status === "active" && item.current_stage === "business_draft");
  const businessSubmittedToManagerProjects = safeProjects.filter((item) =>
    ["manager_review", "procurement_sourcing", "legal_review", "final_approval", "signing", "completed"].includes(item.current_stage) &&
    item.status !== "cancelled",
  );
  const managerPendingProjects = safeProjects.filter((item) => item.status === "active" && item.current_stage === "manager_review");
  const managerApprovedProjects = safeProjects.filter((item) =>
    ["procurement_sourcing", "legal_review", "final_approval", "signing", "completed"].includes(item.current_stage) &&
    item.status !== "cancelled",
  );
  const procurementLegalSubmittedProjects = safeProjects.filter((item) =>
    item.selected_vendor_id &&
    ["legal_review", "final_approval", "signing", "completed"].includes(item.current_stage) &&
    item.status !== "cancelled",
  );
  const legalPendingProjects = safeProjects.filter((item) => item.status === "active" && item.current_stage === "legal_review");
  const legalApprovedProjects = safeProjects.filter((item) =>
    item.selected_vendor_id &&
    ["final_approval", "signing", "completed"].includes(item.current_stage) &&
    item.status !== "cancelled",
  );

  if (currentUser?.role === "business") {
    return html`
      <div>
        <div className="topbar">
          <div>
            <h2>业务总览</h2>
            <p>这里只保留业务最常看的两类项目：正在起草的申请，以及已经提交给上级审批的项目。</p>
          </div>
        </div>

        <section className="section-block">
          <div className="projects-layout">
            <section className="panel">
              <div className="section-title-row">
                <h3>1. 正在起草的业务</h3>
                <div className="subtle">${businessDraftProjects.length} 个项目</div>
              </div>
              ${businessDraftProjects.length
                ? html`
                    <div className="stack-list">
                      ${businessDraftProjects.map((item) => html`
                        <div key=${item.id} className="activity-item">
                          <div className="activity-main">
                            <strong>${item.title}</strong>
                            <div className="subtle">${item.department || "未标注部门"} / ${formatCurrency(item.budget_amount, item.currency)} / ${displayLabel(item.current_stage)}</div>
                          </div>
                          <div className="activity-meta">
                            <span className="status-badge ${toneOf(item.status)}">${displayLabel(item.status)}</span>
                            <button className="btn ghost small" onClick=${() => openProjectWorkspace?.(item.id)}>查看详情</button>
                          </div>
                        </div>
                      `)}
                    </div>
                  `
                : html`<div className="empty-box">当前没有正在起草的业务申请。</div>`}
            </section>

            <section className="panel">
              <div className="section-title-row">
                <h3>2. 已交给上级审批</h3>
                <div className="subtle">${businessSubmittedToManagerProjects.length} 个项目</div>
              </div>
              ${businessSubmittedToManagerProjects.length
                ? html`
                    <div className="stack-list">
                      ${businessSubmittedToManagerProjects.map((item) => html`
                        <div key=${item.id} className="activity-item">
                          <div className="activity-main">
                            <strong>${item.title}</strong>
                            <div className="subtle">${item.department || "未标注部门"} / ${item.vendor_name || "待确认供应商"} / ${displayLabel(item.current_stage)}</div>
                          </div>
                          <div className="activity-meta">
                            <span className="status-badge ${toneOf(item.status)}">${displayLabel(item.status)}</span>
                            <button className="btn ghost small" onClick=${() => openProjectWorkspace?.(item.id)}>查看详情</button>
                          </div>
                        </div>
                      `)}
                    </div>
                  `
                : html`<div className="empty-box">当前还没有提交给上级审批的业务项目。</div>`}
            </section>
          </div>
        </section>
      </div>
    `;
  }

  if (currentUser?.role === "procurement") {
    return html`
      <div>
        <div className="topbar">
          <div>
            <h2>采购总览</h2>
            <p>这里只保留你当前最需要关注的两类项目。</p>
          </div>
        </div>

        <section className="section-block">
          <div className="projects-layout">
            <section className="panel">
              <div className="section-title-row">
                <h3>1. 业务部发起，待我审核</h3>
                <div className="subtle">${procurementPendingProjects.length} 个项目</div>
              </div>
              ${procurementPendingProjects.length
                ? html`
                    <div className="stack-list">
                      ${procurementPendingProjects.map((item) => html`
                        <div key=${item.id} className="activity-item">
                          <div className="activity-main">
                            <strong>${item.title}</strong>
                            <div className="subtle">${item.department || "未标注部门"} / ${item.vendor_name || "待确认供应商"} / ${displayLabel(item.current_stage)}</div>
                          </div>
                          <div className="activity-meta">
                            <span className="status-badge ${toneOf(item.status)}">${displayLabel(item.status)}</span>
                            <button className="btn ghost small" onClick=${() => openProjectWorkspace?.(item.id)}>进入采购执行</button>
                          </div>
                        </div>
                      `)}
                    </div>
                  `
                : html`<div className="empty-box">当前没有待你审核的采购项目。</div>`}
            </section>

            <section className="panel">
              <div className="section-title-row">
                <h3>2. 已通过并提交法务</h3>
                <div className="subtle">${procurementLegalSubmittedProjects.length} 个项目</div>
              </div>
              ${procurementLegalSubmittedProjects.length
                ? html`
                    <div className="stack-list">
                      ${procurementLegalSubmittedProjects.map((item) => html`
                        <div key=${item.id} className="activity-item">
                          <div className="activity-main">
                            <strong>${item.title}</strong>
                            <div className="subtle">${item.vendor_name || "已选供应商"} / ${displayLabel(item.current_stage)}</div>
                          </div>
                          <div className="activity-meta">
                            <span className="status-badge ${toneOf(item.status)}">${displayLabel(item.status)}</span>
                            <button className="btn ghost small" onClick=${() => openProjectWorkspace?.(item.id)}>查看记录</button>
                          </div>
                        </div>
                      `)}
                    </div>
                  `
                : html`<div className="empty-box">当前还没有已通过采购并提交法务的项目。</div>`}
            </section>
          </div>
        </section>
      </div>
    `;
  }

  if (currentUser?.role === "manager") {
    return html`
      <div>
        <div className="topbar">
          <div>
            <h2>上级总览</h2>
            <p>这里只保留上级最常看的两类项目：待审批业务，以及已经批准并交给采购推进的项目。</p>
          </div>
        </div>

        <section className="section-block">
          <div className="projects-layout">
            <section className="panel">
              <div className="section-title-row">
                <h3>1. 待我审批的业务</h3>
                <div className="subtle">${managerPendingProjects.length} 个项目</div>
              </div>
              ${managerPendingProjects.length
                ? html`
                    <div className="stack-list">
                      ${managerPendingProjects.map((item) => html`
                        <div key=${item.id} className="activity-item">
                          <div className="activity-main">
                            <strong>${item.title}</strong>
                            <div className="subtle">${item.department || "未标注部门"} / ${formatCurrency(item.budget_amount, item.currency)} / ${displayLabel(item.current_stage)}</div>
                          </div>
                          <div className="activity-meta">
                            <span className="status-badge ${toneOf(item.status)}">${displayLabel(item.status)}</span>
                            <button className="btn ghost small" onClick=${() => openProjectWorkspace?.(item.id)}>进入审批</button>
                          </div>
                        </div>
                      `)}
                    </div>
                  `
                : html`<div className="empty-box">当前没有待你审批的业务项目。</div>`}
            </section>

            <section className="panel">
              <div className="section-title-row">
                <h3>2. 已批准并交给采购</h3>
                <div className="subtle">${managerApprovedProjects.length} 个项目</div>
              </div>
              ${managerApprovedProjects.length
                ? html`
                    <div className="stack-list">
                      ${managerApprovedProjects.map((item) => html`
                        <div key=${item.id} className="activity-item">
                          <div className="activity-main">
                            <strong>${item.title}</strong>
                            <div className="subtle">${item.department || "未标注部门"} / ${item.vendor_name || "待确认供应商"} / ${displayLabel(item.current_stage)}</div>
                          </div>
                          <div className="activity-meta">
                            <span className="status-badge ${toneOf(item.status)}">${displayLabel(item.status)}</span>
                            <button className="btn ghost small" onClick=${() => openProjectWorkspace?.(item.id)}>查看详情</button>
                          </div>
                        </div>
                      `)}
                    </div>
                  `
                : html`<div className="empty-box">当前还没有已批准并进入采购流转的项目。</div>`}
            </section>
          </div>
        </section>
      </div>
    `;
  }

  if (currentUser?.role === "legal") {
    return html`
      <div>
        <div className="topbar">
          <div>
            <h2>法务总览</h2>
            <p>这里只保留法务最常处理的两类项目：采购提交来的待审合同，以及已经完成法务审批的项目记录。</p>
          </div>
        </div>

        <section className="section-block">
          <div className="projects-layout">
            <section className="panel">
              <div className="section-title-row">
                <h3>1. 采购部上传的申请</h3>
                <div className="subtle">${legalPendingProjects.length} 个项目</div>
              </div>
              ${legalPendingProjects.length
                ? html`
                    <div className="stack-list">
                      ${legalPendingProjects.map((item) => html`
                        <div key=${item.id} className="activity-item">
                          <div className="activity-main">
                            <strong>${item.title}</strong>
                            <div className="subtle">${item.department || "未标记部门"} / ${item.vendor_name || "待确认供应商"} / ${displayLabel(item.current_stage)}</div>
                          </div>
                          <div className="activity-meta">
                            <span className="status-badge ${toneOf(item.status)}">${displayLabel(item.status)}</span>
                            <button className="btn ghost small" onClick=${() => openProjectWorkspace?.(item.id)}>进入法务审核</button>
                          </div>
                        </div>
                      `)}
                    </div>
                  `
                : html`<div className="empty-box">当前没有待法务处理的采购合同。</div>`}
            </section>

            <section className="panel">
              <div className="section-title-row">
                <h3>2. 已通过的法务审批</h3>
                <div className="subtle">${legalApprovedProjects.length} 个项目</div>
              </div>
              ${legalApprovedProjects.length
                ? html`
                    <div className="stack-list">
                      ${legalApprovedProjects.map((item) => html`
                        <div key=${item.id} className="activity-item">
                          <div className="activity-main">
                            <strong>${item.title}</strong>
                            <div className="subtle">${item.vendor_name || "已选供应商"} / ${displayLabel(item.current_stage)}</div>
                          </div>
                          <div className="activity-meta">
                            <span className="status-badge ${toneOf(item.status)}">${displayLabel(item.status)}</span>
                            <button className="btn ghost small" onClick=${() => openProjectWorkspace?.(item.id)}>查看审批记录</button>
                          </div>
                        </div>
                      `)}
                    </div>
                  `
                : html`<div className="empty-box">当前还没有已完成法务审批的项目。</div>`}
            </section>
          </div>
        </section>
      </div>
    `;
  }

  return html`
    <div>
      <div className="topbar">
        <div>
          <h2>\u5e73\u53f0\u603b\u89c8</h2>
          <p>
            \u8fd9\u662f ${displayLabel(currentUser?.role)} \u7684\u5de5\u4f5c\u53f0\u5165\u53e3\u3002\u7cfb\u7edf\u53ea\u4f1a\u5c55\u793a\u4f60\u5f53\u524d\u89d2\u8272\u9700\u8981\u5904\u7406\u7684\u9879\u76ee\u4e0e\u6a21\u5757\u3002
          </p>
        </div>
      </div>

      <section className="hero-grid">
        <div className="hero-panel">
          <div className="eyebrow">\u5de5\u4f5c\u6d41\u9996\u9875</div>
          <h3>\u8ba9\u91c7\u8d2d\u3001\u6cd5\u52a1\u3001\u5b89\u5168\u90fd\u80fd\u4e00\u773c\u770b\u6e05\u9879\u76ee\u8fdb\u5ea6\u3001\u98ce\u9669\u548c\u4e0b\u4e00\u6b65</h3>
          <p>
            \u8fd9\u4e2a\u5e73\u53f0\u4e0d\u53ea\u662f\u95ee\u7b54\u3002\u5b83\u540c\u65f6\u627f\u8f7d\u4e86\u4f9b\u5e94\u5546\u51c6\u5165\u3001\u5b89\u5168\u8bc4\u5ba1\u3001\u5408\u540c\u7ea2\u7ebf\u5ba1\u67e5\u3001
            \u5ba1\u6279\u63a8\u8fdb\u548c Trace \u590d\u76d8\u80fd\u529b\u3002
          </p>
          <div className="hero-actions">
            <button className="btn primary" onClick=${() => setPage("projects")}>
              <i data-lucide="workflow" style=${{ width: "15px", height: "15px" }}></i>
              \u6253\u5f00\u5de5\u4f5c\u53f0
            </button>
            ${currentUser?.role === "admin"
              ? html`
                  <button className="btn secondary" onClick=${() => setPage("knowledge")}>
                    <i data-lucide="database" style=${{ width: "15px", height: "15px" }}></i>
                    \u7ba1\u7406\u77e5\u8bc6\u5e93
                  </button>
                `
              : null}
            ${currentUser?.role !== "business"
              ? html`
                  <button
                    className="btn ghost"
                    onClick=${() => {
                      setDraftQuestion(DEMO_QUESTIONS[1]);
                      setPage("assistant");
                    }}
                  >
                    <i data-lucide="git-compare-arrows" style=${{ width: "15px", height: "15px" }}></i>
                    \u76f4\u63a5\u8bd5\u7528\u5bf9\u6bd4\u5ba1\u67e5
                  </button>
                `
              : null}
          </div>
          <div className="hero-foot">
            <div className="helper-text">
              \u540c\u4e00\u4e2a\u9879\u76ee\u5728\u4e0d\u540c\u89d2\u8272\u4e0b\u4f1a\u770b\u5230\u4e0d\u540c\u4fe1\u606f\u7c92\u5ea6\uff0c\u8fd9\u91cc\u5c55\u793a\u7684\u90fd\u662f\u5f53\u524d\u8d26\u53f7\u53ef\u89c1\u5185\u5bb9\u3002
            </div>
          </div>
        </div>

        <div className="guide-panel">
          <div className="guide-step">
            <span className="guide-num">01</span>
            <div>
              <strong>\u5148\u5bfc\u5165\u91c7\u8d2d\u6587\u6863</strong>
              <p>\u4e0a\u4f20\u51c6\u5165\u5236\u5ea6\u3001\u6807\u51c6 MSA\u3001\u4f9b\u5e94\u5546\u7ea2\u7ebf\u7248\u672c\u3001\u5b89\u5168 SOP \u548c FAQ\u3002</p>
            </div>
          </div>
          <div className="guide-step">
            <span className="guide-num">02</span>
            <div>
              <strong>\u521b\u5efa\u91c7\u8d2d\u9879\u76ee</strong>
              <p>\u586b\u5199\u4f9b\u5e94\u5546\u3001\u9884\u7b97\u3001\u90e8\u95e8\u3001\u6570\u636e\u8303\u56f4\uff0c\u7cfb\u7edf\u4f1a\u81ea\u52a8\u521d\u59cb\u5316\u9636\u6bb5\u5f85\u529e\u3002</p>
            </div>
          </div>
          <div className="guide-step">
            <span className="guide-num">03</span>
            <div>
              <strong>\u8fd0\u884c AI \u5ba1\u67e5</strong>
              <p>\u5728\u9879\u76ee\u9875\u6216\u72ec\u7acb\u5ba1\u67e5\u52a9\u624b\u91cc\u53d1\u8d77\u95ee\u9898\uff0c\u7cfb\u7edf\u4f1a\u8fd4\u56de\u98ce\u9669\u3001\u5f15\u7528\u3001Trace \u548c\u4e0b\u4e00\u6b65\u5efa\u8bae\u3002</p>
            </div>
          </div>
        </div>
      </section>

      <section className="metrics-grid">
        <${StatCard}
          html=${html}
          title="\u77e5\u8bc6\u6e90"
          value=${safeSources.length}
          detail=${`\u5df2\u7d22\u5f15 ${indexedSources}`}
          tone="success"
          icon="database"
        />
        <${StatCard}
          html=${html}
          title="\u91c7\u8d2d\u9879\u76ee"
          value=${safeProjects.length}
          detail=${`${activeProjects} \u4e2a\u6b63\u5728\u63a8\u8fdb`}
          tone=${activeProjects ? "success" : "neutral"}
          icon="workflow"
        />
        <${StatCard}
          html=${html}
          title="\u7d22\u5f15\u4efb\u52a1"
          value=${safeTasks.length}
          detail=${runningTasks ? `${runningTasks} \u4e2a\u8fd0\u884c\u4e2d` : "\u65e0\u6b63\u5728\u8fd0\u884c\u7684\u4efb\u52a1"}
          tone=${runningTasks ? "warn" : "neutral"}
          icon="loader"
        />
        <${StatCard}
          html=${html}
          title="Trace / \u8bc4\u6d4b"
          value=${safeTraces.length}
          detail=${failedTraces ? `${failedTraces} \u6761\u5931\u8d25 Trace` : `${compareCases} \u9053\u5bf9\u6bd4\u7c7b\u9898\u76ee`}
          tone=${failedTraces ? "warn" : "neutral"}
          icon="shield-check"
        />
      </section>

      <section className="section-block">
        <div className="section-title-row"><h3>\u63a8\u8350\u8d77\u624b\u65b9\u5f0f</h3></div>
        <div className="guided-grid">
          <div className="guide-card accent">
            <div className="guide-tag">
              <i data-lucide="package" style=${{ width: "12px", height: "12px" }}></i>
              \u793a\u4f8b\u6587\u6863
            </div>
            <h4>\u53ef\u4ee5\u5148\u5bfc\u5165\u8fd9\u6279\u5185\u7f6e\u91c7\u8d2d\u8d44\u6599</h4>
            <div className="file-chip-list">
              ${DEMO_FILES.map(
                (item) => html`
                  <span className="file-chip" key=${item}>
                    <i data-lucide="file-text" style=${{ width: "11px", height: "11px" }}></i>
                    ${item}
                  </span>
                `,
              )}
            </div>
          </div>

          <div className="guide-card">
            <div className="guide-tag">
              <i data-lucide="message-circle-question" style=${{ width: "12px", height: "12px" }}></i>
              \u63a8\u8350\u95ee\u9898
            </div>
            <h4>\u4ece\u8fd9\u51e0\u4e2a\u95ee\u9898\u5f00\u59cb\u6700\u5bb9\u6613\u770b\u61c2\u7cfb\u7edf\u4f5c\u7528</h4>
            <div className="question-list">
              ${DEMO_QUESTIONS.map(
                (item) => html`
                  <button
                    key=${item}
                    className="question-item"
                    onClick=${() => {
                      setDraftQuestion(item);
                      setPage("assistant");
                    }}
                  >
                    ${item}
                  </button>
                `,
              )}
            </div>
          </div>
        </div>
      </section>

      <section className="section-block">
        <div className="section-title-row"><h3>\u6700\u8fd1\u6d3b\u52a8</h3></div>
        <div className="activity-grid">
          <div className="panel">
            <div className="section-title-row"><h4>\u6700\u8fd1\u9879\u76ee</h4></div>
            <${ActivityList}
              html=${html}
              items=${safeProjects.slice(0, 5).map((item) => ({
                ...item,
                title: item.title,
                subtitle: `${item.vendor_name} / ${displayLabel(item.current_stage)}`,
                status: item.risk_level,
              }))}
              emptyText="\u8fd8\u6ca1\u6709\u91c7\u8d2d\u9879\u76ee\uff0c\u53ef\u4ee5\u5148\u53bb\u201c\u91c7\u8d2d\u9879\u76ee\u201d\u9875\u9762\u521b\u5efa\u4e00\u4e2a\u3002"
              onPick=${() => setPage("projects")}
            />
          </div>

          <div className="panel">
            <div className="section-title-row"><h4>\u6700\u8fd1 Trace</h4></div>
            <${ActivityList}
              html=${html}
              items=${safeTraces.slice(0, 5)}
              emptyText="\u6682\u65f6\u6ca1\u6709 Trace \u8bb0\u5f55\uff0c\u8bf7\u5148\u53d1\u8d77\u4e00\u6b21\u5ba1\u67e5\u3002"
              onPick=${() => setPage("audit")}
            />
          </div>
        </div>
      </section>
    </div>
  `;
}

export function KnowledgePage({ html, sources, tasks, refreshAll, rememberTask }) {
  const safeSources = Array.isArray(sources) ? sources : [];
  const safeTasks = Array.isArray(tasks) ? tasks : [];
  const [file, setFile] = useState(null);
  const [allowedRoles, setAllowedRoles] = useState("employee,admin");
  const [tags, setTags] = useState("procurement,legal,security");
  const [remoteUrl, setRemoteUrl] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [taskDetail, setTaskDetail] = useState(null);
  const [deletingSourceId, setDeletingSourceId] = useState("");

  useEffect(() => {
    const taskId = taskDetail?.id;
    const taskStatus = taskDetail?.status;
    if (!taskId || ["indexed", "failed"].includes(taskStatus)) return undefined;
    let timer = null;
    let stream = null;

    const startPolling = () => {
      if (timer) return;
      timer = setInterval(async () => {
        try {
          const detail = await apiGet(`/knowledge/tasks/${taskId}`);
          setTaskDetail((current) => ({ ...current, ...detail }));
          if (["indexed", "failed"].includes(detail.status)) {
            clearInterval(timer);
            timer = null;
            refreshAll();
          }
        } catch (_) {
          clearInterval(timer);
          timer = null;
        }
      }, 1500);
    };

    if (typeof EventSource === "function") {
      try {
        stream = openEventStream(`/knowledge/tasks/${taskId}/stream`);
        stream.addEventListener("task", (event) => {
          const payload = JSON.parse(event.data || "{}");
          const nextTask = payload.task || {};
          setTaskDetail((current) => ({
            ...current,
            ...nextTask,
            stage: payload.stage || current?.stage || "",
            progress: payload.progress || current?.progress || null,
            message: payload.message || current?.message || "",
          }));
          if (["indexed", "failed"].includes(nextTask.status)) {
            stream?.close();
            refreshAll();
          }
        });
        stream.onerror = () => {
          stream?.close();
          stream = null;
          startPolling();
        };
      } catch (_) {
        startPolling();
      }
    } else {
      startPolling();
    }

    return () => {
      if (stream) stream.close();
      if (timer) clearInterval(timer);
    };
  }, [taskDetail?.id, taskDetail?.status, refreshAll]);

  async function handleUpload() {
    try {
      setLoading(true);
      setError("");
      const form = new FormData();
      if (file) form.append("file", file);
      if (remoteUrl.trim()) form.append("remote_url", remoteUrl.trim());
      form.append("allowed_roles", allowedRoles);
      form.append("tags", tags);
      const result = await apiPost("/knowledge/upload", { method: "POST", body: form });
      rememberTask(result.task_id);
      setTaskDetail({
        id: result.task_id,
        source_name: result.source.title,
        status: result.duplicate ? "indexed" : "uploaded",
        chunk_count: result.chunk_count || 0,
        stage: result.duplicate ? "indexed" : "uploaded",
        progress: null,
        message: result.duplicate ? "检测到重复文档，已直接复用现有索引。" : "文档已提交，等待开始索引。",
      });
      setFile(null);
      setRemoteUrl("");
      refreshAll();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleReindex() {
    try {
      setError("");
      const result = await apiPost("/knowledge/reindex", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document_ids: [] }),
      });
      result.task_ids.forEach(rememberTask);
      refreshAll();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleDeleteSource(source) {
    if (!source?.id) return;
    const tagSet = new Set(Array.isArray(source.tags) ? source.tags : []);
    if (tagSet.has("project_artifact")) {
      window.alert("项目合同工件不能在知识库总览中直接删除。");
      return;
    }
    const confirmed = window.confirm(`确定删除知识库文档《${source.title || "未命名文档"}》吗？`);
    if (!confirmed) return;
    try {
      setDeletingSourceId(source.id);
      setError("");
      const result = await apiPost("/knowledge/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document_ids: [source.id] }),
      });
      if (result.protected_titles?.length) {
        window.alert(`以下文档受保护，未删除：${result.protected_titles.join(" / ")}`);
      }
      refreshAll();
    } catch (err) {
      setError(err.message);
    } finally {
      setDeletingSourceId("");
    }
  }

  return html`
    <div>
      <div className="topbar">
        <div>
          <h2>\u77e5\u8bc6\u5e93\u4e0e\u7d22\u5f15\u4efb\u52a1</h2>
          <p>
            \u5728\u8fd9\u91cc\u4e0a\u4f20\u51c6\u5165\u5236\u5ea6\u3001\u6807\u51c6\u5408\u540c\u3001\u4f9b\u5e94\u5546\u7ea2\u7ebf\u7248\u672c\u3001SOP \u548c FAQ\uff0c
            \u7cfb\u7edf\u4f1a\u81ea\u52a8\u89e3\u6790\u3001\u5207\u5757\u5e76\u5efa\u7acb\u7d22\u5f15\u3002
          </p>
        </div>
      </div>

      <div className="knowledge-layout">
        <section className="panel upload-panel">
          <h3>\u4e0a\u4f20\u65b0\u77e5\u8bc6</h3>
          <label className="label">\u9009\u62e9\u6587\u4ef6</label>
          <input className="field" type="file" onChange=${(event) => setFile(event.target.files?.[0] || null)} />

          <label className="label">\u6216\u6293\u53d6\u7f51\u9875 URL</label>
          <input
            className="field"
            value=${remoteUrl}
            onInput=${(event) => setRemoteUrl(event.target.value)}
            placeholder="https://..."
          />

          <div className="split-fields">
            <div>
              <label className="label">\u53ef\u89c1\u89d2\u8272</label>
              <input className="field" value=${allowedRoles} onInput=${(event) => setAllowedRoles(event.target.value)} />
            </div>
            <div>
              <label className="label">\u6807\u7b7e</label>
              <input className="field" value=${tags} onInput=${(event) => setTags(event.target.value)} />
            </div>
          </div>

          <div className="button-row">
            <button className="btn primary" onClick=${handleUpload} disabled=${loading}>
              <i data-lucide=${loading ? "loader" : "upload"} style=${{ width: "15px", height: "15px" }}></i>
              ${loading ? "\u6b63\u5728\u63d0\u4ea4..." : "\u5f00\u59cb\u4e0a\u4f20"}
            </button>
            <button className="btn secondary" onClick=${handleReindex}>
              <i data-lucide="refresh-cw" style=${{ width: "15px", height: "15px" }}></i>
              \u5168\u91cf\u91cd\u5efa\u7d22\u5f15
            </button>
          </div>

          ${error ? html`<div className="error">${error}</div>` : null}

          ${taskDetail
            ? html`
                <div className="panel soft-panel" style=${{ marginTop: "18px" }}>
                  <div className="section-title-row"><h4>\u6700\u65b0\u4efb\u52a1</h4></div>
                  <div className="status-line">
                    <span className="status-badge ${toneOf(taskDetail.status)}">
                      ${displayLabel(taskDetail.status)}
                    </span>
                    <span className="api-chip">${taskDetail.id}</span>
                  </div>
                  <p className="muted" style=${{ marginTop: "10px" }}>
                    ${taskDetail.source_name || "\u672a\u77e5\u6587\u6863"} / \u5207\u5757 ${taskDetail.chunk_count || 0}
                  </p>
                  ${taskDetail.message
                    ? html`<p className="subtle" style=${{ marginTop: "8px" }}>${taskDetail.message}</p>`
                    : null}
                  ${taskDetail.progress?.total
                    ? html`
                        <p className="subtle" style=${{ marginTop: "6px" }}>
                          ${taskDetail.stage || "indexing"} / ${taskDetail.progress.current || 0} / ${taskDetail.progress.total}
                          ${taskDetail.progress.unit || ""}
                        </p>
                      `
                    : null}
                </div>
              `
            : null}
        </section>

        <section className="panel">
          <div className="section-title-row"><h3>\u77e5\u8bc6\u6e90\u5217\u8868</h3></div>
          ${safeSources.length
            ? html`
                <div className="stack-list">
                  ${safeSources.map(
                    (source) => html`
                      <div className="activity-item" key=${source.id}>
                        <div className="activity-main">
                          <strong>${source.title}</strong>
                          <div className="subtle">${source.source_type} / v${source.version}</div>
                          ${source.tags?.length ? html`<div className="subtle">标签：${source.tags.join(" / ")}</div>` : null}
                        </div>
                        <div className="activity-meta">
                          <span className="status-badge ${toneOf(source.status)}">
                            ${displayLabel(source.status)}
                          </span>
                          <button
                            className="btn ghost small"
                            style=${{ marginTop: "8px" }}
                            onClick=${() => handleDeleteSource(source)}
                            disabled=${deletingSourceId === source.id}
                          >
                            ${deletingSourceId === source.id ? "删除中..." : "删除文档"}
                          </button>
                        </div>
                      </div>
                    `,
                  )}
                </div>
              `
            : html`<div className="empty-box">\u8fd8\u6ca1\u6709\u5bfc\u5165\u4efb\u4f55\u77e5\u8bc6\u6587\u6863\u3002</div>`}
        </section>
      </div>

      <section className="section-block">
        <div className="section-title-row"><h3>\u6700\u8fd1\u7d22\u5f15\u4efb\u52a1</h3></div>
        <${ActivityList}
          html=${html}
          items=${safeTasks}
          emptyText="\u6682\u65f6\u6ca1\u6709\u7d22\u5f15\u4efb\u52a1\u8bb0\u5f55\u3002"
        />
      </section>
    </div>
  `;
}
