import React, { useEffect, useMemo, useState } from "https://esm.sh/react@18.3.1";

import { apiGet, apiPatch, apiPost } from "./api.js";
import {
  PROJECT_REVIEW_PRESETS,
  PROJECT_STAGE_ORDER,
  ROLE_OPTIONS,
  displayLabel,
  stageText,
  toneOf,
} from "./config.js";

function formatCurrency(amount, currency) {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: currency || "CNY",
    maximumFractionDigits: 0,
  }).format(amount || 0);
}

function stageGroups(projects) {
  return PROJECT_STAGE_ORDER.map((stage) => ({
    stage,
    items: projects.filter((project) => project.current_stage === stage),
  }));
}

export function ProjectsPage({ html, projects, refreshAll, onTraceCreated }) {
  const [selectedProjectId, setSelectedProjectId] = useState(projects[0]?.id || "");
  const [projectDetail, setProjectDetail] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState("");
  const [reviewRole, setReviewRole] = useState("employee");
  const [reviewQuery, setReviewQuery] = useState("");
  const [reviewLoading, setReviewLoading] = useState(false);
  const [createForm, setCreateForm] = useState({
    title: "",
    requester_name: "",
    department: "",
    vendor_name: "",
    category: "software",
    budget_amount: 0,
    currency: "CNY",
    summary: "",
    data_scope: "none",
  });

  useEffect(() => {
    if (!selectedProjectId && projects[0]?.id) {
      setSelectedProjectId(projects[0].id);
    }
  }, [projects, selectedProjectId]);

  useEffect(() => {
    if (!selectedProjectId) return;
    loadProject(selectedProjectId);
  }, [selectedProjectId]);

  useEffect(() => {
    if (projectDetail?.current_stage) {
      setReviewQuery(
        PROJECT_REVIEW_PRESETS[projectDetail.current_stage] ||
          "\u8bf7\u603b\u7ed3\u8fd9\u4e2a\u91c7\u8d2d\u9879\u76ee\u7684\u5f53\u524d\u9636\u6bb5\u963b\u585e\u9879\u3001\u98ce\u9669\u548c\u4e0b\u4e00\u6b65\u5efa\u8bae\u3002",
      );
    }
  }, [projectDetail?.current_stage]);

  const currentTasks = useMemo(
    () => projectDetail?.tasks?.filter((task) => task.stage === projectDetail.current_stage) || [],
    [projectDetail],
  );

  const currentArtifacts = useMemo(
    () =>
      projectDetail?.artifacts?.filter(
        (artifact) => artifact.stage === projectDetail.current_stage,
      ) || [],
    [projectDetail],
  );

  async function loadProject(projectId) {
    try {
      setLoadingDetail(true);
      setError("");
      const [detail, timelineItems] = await Promise.all([
        apiGet(`/projects/${projectId}`),
        apiGet(`/projects/${projectId}/timeline`),
      ]);
      setProjectDetail(detail);
      setTimeline(timelineItems);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingDetail(false);
    }
  }

  async function createProject(event) {
    event.preventDefault();
    try {
      setError("");
      const created = await apiPost("/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...createForm,
          budget_amount: Number(createForm.budget_amount || 0),
        }),
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
        data_scope: "none",
      });
      await refreshAll();
      setSelectedProjectId(created.id);
    } catch (err) {
      setError(err.message);
    }
  }

  async function updateTask(taskId, status) {
    if (!projectDetail) return;
    try {
      await apiPatch(`/projects/${projectDetail.id}/tasks/${taskId}`, { status });
      await loadProject(projectDetail.id);
      await refreshAll();
    } catch (err) {
      setError(err.message);
    }
  }

  async function updateArtifact(artifactId, status) {
    if (!projectDetail) return;
    try {
      await apiPatch(`/projects/${projectDetail.id}/artifacts/${artifactId}`, { status });
      await loadProject(projectDetail.id);
      await refreshAll();
    } catch (err) {
      setError(err.message);
    }
  }

  async function advanceProject() {
    if (!projectDetail) return;
    try {
      await apiPost(`/projects/${projectDetail.id}/advance`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      await loadProject(projectDetail.id);
      await refreshAll();
    } catch (err) {
      setError(err.message);
    }
  }

  async function runProjectReview() {
    if (!projectDetail || !reviewQuery.trim()) return;
    try {
      setReviewLoading(true);
      setError("");
      const result = await apiPost(`/projects/${projectDetail.id}/review/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: reviewQuery, user_role: reviewRole, top_k: 6 }),
      });
      setProjectDetail(result.project);
      setTimeline(await apiGet(`/projects/${projectDetail.id}/timeline`));
      onTraceCreated(result.review.trace_id);
      await refreshAll();
    } catch (err) {
      setError(err.message);
    } finally {
      setReviewLoading(false);
    }
  }

  const grouped = stageGroups(projects);

  return html`
    <div>
      <div className="topbar">
        <div>
          <h2>\u91c7\u8d2d\u9879\u76ee</h2>
          <p>
            \u8fd9\u4e2a\u9875\u9762\u4e0d\u53ea\u770b\u5355\u4e2a\u9879\u76ee\uff0c\u8fd8\u4f1a\u663e\u793a\u6574\u4e2a\u91c7\u8d2d\u6d41\u7a0b\u5f53\u524d\u5361\u5728\u54ea\u4e00\u6b65\u3002
            \u4f60\u53ef\u4ee5\u521b\u5efa\u65b0\u9879\u76ee\uff0c\u8865\u5145\u5f85\u529e\u4e0e\u6750\u6599\uff0c\u5e76\u5728\u5f53\u524d\u9636\u6bb5\u8fd0\u884c AI \u5ba1\u67e5\u3002
          </p>
        </div>
      </div>

      ${error ? html`<div className="error" style=${{ marginBottom: "18px" }}>${error}</div>` : null}

      <section className="section-block">
        <div className="section-title-row"><h3>\u9636\u6bb5\u603b\u89c8</h3></div>
        <div className="stage-board">
          ${grouped.map(
            (group) => html`
              <div className="stage-column" key=${group.stage}>
                <div className="stage-column-head">
                  <strong>${stageText(group.stage)}</strong>
                  <span>${group.items.length}</span>
                </div>
                <div className="stage-column-body">
                  ${group.items.length
                    ? group.items.map(
                        (project) => html`
                          <button
                            key=${project.id}
                            className=${selectedProjectId === project.id ? "stage-card active" : "stage-card"}
                            onClick=${() => setSelectedProjectId(project.id)}
                          >
                            <strong>${project.title}</strong>
                            <div className="subtle">${project.vendor_name || "\u672a\u586b\u5199\u4f9b\u5e94\u5546"}</div>
                            <div className="status-line">
                              <span className="status-badge ${toneOf(project.risk_level)}">
                                ${displayLabel(project.risk_level)}
                              </span>
                            </div>
                          </button>
                        `,
                      )
                    : html`<div className="empty-box compact">\u6682\u65e0\u9879\u76ee</div>`}
                </div>
              </div>
            `,
          )}
        </div>
      </section>

      <div className="projects-layout">
        <section className="panel">
          <div className="section-title-row"><h3>\u521b\u5efa\u65b0\u9879\u76ee</h3></div>
          <form className="stack-list" onSubmit=${createProject}>
            <input
              className="field"
              placeholder="\u9879\u76ee\u540d\u79f0"
              value=${createForm.title}
              onInput=${(e) => setCreateForm({ ...createForm, title: e.target.value })}
            />
            <div className="split-fields">
              <input
                className="field"
                placeholder="\u53d1\u8d77\u4eba"
                value=${createForm.requester_name}
                onInput=${(e) => setCreateForm({ ...createForm, requester_name: e.target.value })}
              />
              <input
                className="field"
                placeholder="\u6240\u5c5e\u90e8\u95e8"
                value=${createForm.department}
                onInput=${(e) => setCreateForm({ ...createForm, department: e.target.value })}
              />
            </div>
            <div className="split-fields">
              <input
                className="field"
                placeholder="\u4f9b\u5e94\u5546\u540d\u79f0"
                value=${createForm.vendor_name}
                onInput=${(e) => setCreateForm({ ...createForm, vendor_name: e.target.value })}
              />
              <input
                className="field"
                placeholder="\u91c7\u8d2d\u7c7b\u522b"
                value=${createForm.category}
                onInput=${(e) => setCreateForm({ ...createForm, category: e.target.value })}
              />
            </div>
            <div className="split-fields">
              <input
                className="field"
                type="number"
                placeholder="\u9884\u7b97\u91d1\u989d"
                value=${createForm.budget_amount}
                onInput=${(e) => setCreateForm({ ...createForm, budget_amount: e.target.value })}
              />
              <input
                className="field"
                placeholder="\u5e01\u79cd"
                value=${createForm.currency}
                onInput=${(e) => setCreateForm({ ...createForm, currency: e.target.value })}
              />
            </div>
            <input
              className="field"
              placeholder="\u6570\u636e\u8303\u56f4\uff08none / customer_data / internal_data\uff09"
              value=${createForm.data_scope}
              onInput=${(e) => setCreateForm({ ...createForm, data_scope: e.target.value })}
            />
            <textarea
              className="field textarea-medium"
              placeholder="\u9879\u76ee\u80cc\u666f\u4e0e\u91c7\u8d2d\u76ee\u7684"
              value=${createForm.summary}
              onInput=${(e) => setCreateForm({ ...createForm, summary: e.target.value })}
            ></textarea>
            <div className="button-row">
              <button className="btn primary" type="submit">\u521b\u5efa\u9879\u76ee</button>
            </div>
          </form>
        </section>

        <section className="panel">
          <div className="section-title-row"><h3>\u9879\u76ee\u5217\u8868</h3></div>
          ${projects.length
            ? html`
                <div className="stack-list">
                  ${projects.map(
                    (project) => html`
                      <button
                        key=${project.id}
                        className=${selectedProjectId === project.id ? "project-list-item active" : "project-list-item"}
                        onClick=${() => setSelectedProjectId(project.id)}
                      >
                        <div className="activity-main">
                          <strong>${project.title}</strong>
                          <div className="subtle">
                            ${project.vendor_name} / ${stageText(project.current_stage)} /
                            ${formatCurrency(project.budget_amount, project.currency)}
                          </div>
                        </div>
                        <div className="activity-meta">
                          <span className="status-badge ${toneOf(project.risk_level)}">
                            ${displayLabel(project.risk_level)}
                          </span>
                        </div>
                      </button>
                    `,
                  )}
                </div>
              `
            : html`<div className="empty-box">\u6682\u65f6\u8fd8\u6ca1\u6709\u91c7\u8d2d\u9879\u76ee\u3002</div>`}
        </section>
      </div>

      ${loadingDetail
        ? html`<div className="center-panel" style=${{ minHeight: "220px" }}><div className="loading-ring"></div></div>`
        : projectDetail
          ? html`
              <section className="section-block">
                <div className="section-title-row">
                  <h3>${projectDetail.title}</h3>
                  <div className="button-row">
                    <span className="status-badge ${toneOf(projectDetail.risk_level)}">
                      ${displayLabel(projectDetail.risk_level)}
                    </span>
                    <span className="status-badge neutral">${stageText(projectDetail.current_stage)}</span>
                  </div>
                </div>
                <div className="project-meta-grid">
                  <div className="mini-metric">
                    <span className="mini-label">\u4f9b\u5e94\u5546</span>
                    <strong>${projectDetail.vendor_name || "-"}</strong>
                  </div>
                  <div className="mini-metric">
                    <span className="mini-label">\u53d1\u8d77\u4eba</span>
                    <strong>${projectDetail.requester_name || "-"}</strong>
                  </div>
                  <div className="mini-metric">
                    <span className="mini-label">\u90e8\u95e8</span>
                    <strong>${projectDetail.department || "-"}</strong>
                  </div>
                  <div className="mini-metric">
                    <span className="mini-label">\u9884\u7b97</span>
                    <strong>${formatCurrency(projectDetail.budget_amount, projectDetail.currency)}</strong>
                  </div>
                </div>
                <div className="stage-rail">
                  ${projectDetail.stages.map(
                    (stage) => html`
                      <div className=${stage.status === "active" ? "stage-chip active" : "stage-chip"}>
                        <span>${stageText(stage.stage)}</span>
                      </div>
                    `,
                  )}
                </div>
              </section>

              <div className="projects-layout wide">
                <section className="panel">
                  <div className="section-title-row">
                    <h3>\u9636\u6bb5\u63a8\u8fdb</h3>
                    <button className="btn secondary" onClick=${advanceProject}>\u63a8\u8fdb\u5230\u4e0b\u4e00\u9636\u6bb5</button>
                  </div>

                  ${projectDetail.blocker_summary.length
                    ? html`
                        <div className="stack-list">
                          ${projectDetail.blocker_summary.map(
                            (item) => html`<div className="inline-alert warn" key=${item}>${item}</div>`,
                          )}
                        </div>
                      `
                    : html`<div className="empty-box">\u5f53\u524d\u9636\u6bb5\u6ca1\u6709\u663e\u5f0f\u963b\u585e\u9879\u3002</div>`}

                  <div className="section-title-row" style=${{ marginTop: "20px" }}><h4>\u5f53\u524d\u9636\u6bb5\u5f85\u529e</h4></div>
                  ${currentTasks.length
                    ? html`
                        <div className="stack-list">
                          ${currentTasks.map(
                            (task) => html`
                              <div className="activity-item" key=${task.id}>
                                <div className="activity-main">
                                  <strong>${task.title}</strong>
                                  <div className="subtle">${displayLabel(task.assignee_role)} / ${task.task_type}</div>
                                </div>
                                <div className="activity-meta">
                                  <span className="status-badge ${toneOf(task.status)}">
                                    ${displayLabel(task.status)}
                                  </span>
                                  ${task.status !== "done"
                                    ? html`
                                        <button className="btn ghost small" onClick=${() => updateTask(task.id, "done")}>
                                          \u6807\u8bb0\u5b8c\u6210
                                        </button>
                                      `
                                    : null}
                                </div>
                              </div>
                            `,
                          )}
                        </div>
                      `
                    : html`<div className="empty-box">\u5f53\u524d\u9636\u6bb5\u6682\u65e0\u5f85\u529e\u4efb\u52a1\u3002</div>`}

                  <div className="section-title-row" style=${{ marginTop: "20px" }}><h4>\u5f53\u524d\u9636\u6bb5\u6750\u6599</h4></div>
                  ${currentArtifacts.length
                    ? html`
                        <div className="stack-list">
                          ${currentArtifacts.map(
                            (artifact) => html`
                              <div className="activity-item" key=${artifact.id}>
                                <div className="activity-main">
                                  <strong>${artifact.title}</strong>
                                  <div className="subtle">${artifact.artifact_type}</div>
                                </div>
                                <div className="activity-meta">
                                  <span className="status-badge ${toneOf(artifact.status)}">
                                    ${displayLabel(artifact.status)}
                                  </span>
                                  ${!["provided", "approved"].includes(artifact.status)
                                    ? html`
                                        <button
                                          className="btn ghost small"
                                          onClick=${() => updateArtifact(artifact.id, "provided")}
                                        >
                                          \u6807\u8bb0\u5df2\u63d0\u4f9b
                                        </button>
                                      `
                                    : null}
                                </div>
                              </div>
                            `,
                          )}
                        </div>
                      `
                    : html`<div className="empty-box">\u5f53\u524d\u9636\u6bb5\u6682\u65e0\u6302\u8f7d\u6750\u6599\u8981\u6c42\u3002</div>`}
                </section>

                <section className="panel">
                  <div className="section-title-row"><h3>\u9879\u76ee\u7ea7 AI \u5ba1\u67e5</h3></div>
                  <label className="label">\u5ba1\u67e5\u89d2\u8272</label>
                  <select className="field" value=${reviewRole} onChange=${(event) => setReviewRole(event.target.value)}>
                    ${ROLE_OPTIONS.map(
                      (item) => html`<option key=${item.value} value=${item.value}>${item.label}</option>`,
                    )}
                  </select>

                  <label className="label">\u5ba1\u67e5\u95ee\u9898</label>
                  <textarea
                    className="field textarea-large"
                    value=${reviewQuery}
                    onInput=${(event) => setReviewQuery(event.target.value)}
                  ></textarea>

                  <div className="button-row">
                    <button className="btn primary" onClick=${runProjectReview} disabled=${reviewLoading}>
                      ${reviewLoading ? "\u6b63\u5728\u8fd0\u884c..." : "\u8fd0\u884c\u9879\u76ee\u5ba1\u67e5"}
                    </button>
                  </div>

                  <div className="section-title-row" style=${{ marginTop: "20px" }}><h4>\u98ce\u9669\u63d0\u793a</h4></div>
                  ${projectDetail.risks.length
                    ? html`
                        <div className="stack-list">
                          ${projectDetail.risks.slice(0, 6).map(
                            (risk) => html`
                              <div className="activity-item" key=${risk.id}>
                                <div className="activity-main">
                                  <strong>${risk.risk_type}</strong>
                                  <div className="subtle">${risk.summary}</div>
                                </div>
                                <div className="activity-meta">
                                  <span className="status-badge ${toneOf(risk.severity)}">
                                    ${displayLabel(risk.severity)}
                                  </span>
                                </div>
                              </div>
                            `,
                          )}
                        </div>
                      `
                    : html`<div className="empty-box">\u8fd8\u6ca1\u6709\u98ce\u9669\u8bb0\u5f55\u3002</div>`}
                </section>
              </div>

              <section className="section-block">
                <div className="section-title-row"><h3>\u9879\u76ee\u65f6\u95f4\u7ebf</h3></div>
                ${timeline.length
                  ? html`
                      <div className="timeline-list">
                        ${timeline.map(
                          (event) => html`
                            <article className="timeline-card" key=${`${event.kind}-${event.created_at}-${event.title}`}>
                              <div className="timeline-badge neutral">${event.kind}</div>
                              <div className="timeline-body">
                                <strong>${event.title}</strong>
                                <div className="subtle">${stageText(event.stage)} / ${event.created_at}</div>
                                <p>${event.summary}</p>
                              </div>
                            </article>
                          `,
                        )}
                      </div>
                    `
                  : html`<div className="empty-box">\u6682\u65f6\u8fd8\u6ca1\u6709\u9879\u76ee\u65f6\u95f4\u7ebf\u4e8b\u4ef6\u3002</div>`}
              </section>
            `
          : null}
    </div>
  `;
}
