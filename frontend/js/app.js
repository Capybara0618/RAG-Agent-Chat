import React, { useEffect, useState } from "https://esm.sh/react@18.3.1";
import { createRoot } from "https://esm.sh/react-dom@18.3.1/client";
import htm from "https://esm.sh/htm@3.1.1";

import { apiGet, loadStoredTaskIds, rememberTaskId } from "./api.js";
import { DEMO_QUESTIONS } from "./config.js";
import { Layout } from "./components.js";
import { AssistantPage, AuditPage } from "./pages-assistant-audit.js";
import { KnowledgePage, OverviewPage } from "./pages-overview-knowledge.js";
import { ProjectsPage } from "./pages-projects.js";

const html = htm.bind(React.createElement);

function App() {
  const [page, setPage] = useState("overview");
  const [sources, setSources] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [traces, setTraces] = useState([]);
  const [cases, setCases] = useState([]);
  const [projects, setProjects] = useState([]);
  const [latestTraceId, setLatestTraceId] = useState("");
  const [draftQuestion, setDraftQuestion] = useState(DEMO_QUESTIONS[1]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadTasks() {
    const taskIds = loadStoredTaskIds();
    const details = await Promise.all(
      taskIds.map(async (taskId) => {
        try {
          return await apiGet(`/knowledge/tasks/${taskId}`);
        } catch (_) {
          return null;
        }
      }),
    );
    setTasks(details.filter(Boolean).reverse());
  }

  async function refreshAll(options = {}) {
    const { silent = false } = options;
    try {
      if (!silent) setLoading(true);
      setError("");
      const [sourceData, traceData, caseData, projectData] = await Promise.all([
        apiGet("/knowledge/sources"),
        apiGet("/trace/search?limit=12"),
        apiGet("/eval/cases"),
        apiGet("/projects"),
      ]);
      setSources(sourceData);
      setTraces(traceData.items || traceData);
      setCases(caseData);
      setProjects(projectData);
      await loadTasks();
    } catch (err) {
      setError(err.message);
    } finally {
      if (!silent) setLoading(false);
    }
  }

  function rememberTask(taskId) {
    rememberTaskId(taskId);
    loadTasks();
  }

  useEffect(() => {
    refreshAll();
  }, []);

  function renderPage() {
    if (loading) {
      return html`
        <div className="center-panel">
          <div className="loading-ring"></div>
          <h3>\u6b63\u5728\u52a0\u8f7d\u5e73\u53f0\u72b6\u6001</h3>
          <p className="muted">
            \u7cfb\u7edf\u6b63\u5728\u540c\u6b65\u77e5\u8bc6\u5e93\u3001Trace\u3001\u8bc4\u6d4b\u9898\u96c6\u548c\u91c7\u8d2d\u9879\u76ee\u5217\u8868\u3002
          </p>
        </div>
      `;
    }

    if (error) {
      return html`
        <div className="center-panel">
          <h3>\u5e73\u53f0\u521d\u59cb\u5316\u5931\u8d25</h3>
          <p className="muted">${error}</p>
          <div className="button-row">
            <button className="btn primary" onClick=${refreshAll}>\u91cd\u65b0\u52a0\u8f7d</button>
          </div>
        </div>
      `;
    }

    if (page === "knowledge") {
      return html`
        <${KnowledgePage}
          html=${html}
          sources=${sources}
          tasks=${tasks}
          refreshAll=${refreshAll}
          rememberTask=${rememberTask}
        />
      `;
    }

    if (page === "projects") {
      return html`
        <${ProjectsPage}
          html=${html}
          projects=${projects}
          refreshAll=${refreshAll}
          onTraceCreated=${(traceId) => setLatestTraceId(traceId)}
        />
      `;
    }

    if (page === "assistant") {
      return html`
        <${AssistantPage}
          html=${html}
          draftQuestion=${draftQuestion}
          setDraftQuestion=${setDraftQuestion}
          onTraceCreated=${(traceId) => {
            setLatestTraceId(traceId);
            refreshAll({ silent: true });
          }}
        />
      `;
    }

    if (page === "audit") {
      return html`
        <${AuditPage}
          html=${html}
          traces=${traces}
          latestTraceId=${latestTraceId}
          refreshAll=${refreshAll}
        />
      `;
    }

    return html`
      <${OverviewPage}
        html=${html}
        sources=${sources}
        tasks=${tasks}
        traces=${traces}
        cases=${cases}
        projects=${projects}
        setPage=${setPage}
        setDraftQuestion=${setDraftQuestion}
      />
    `;
  }

  return html`
    <${Layout} html=${html} page=${page} setPage=${setPage}>
      ${renderPage()}
    </${Layout}>
  `;
}

createRoot(document.getElementById("root")).render(html`<${App} />`);
