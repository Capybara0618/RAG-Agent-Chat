import React, { useEffect, useMemo, useState } from "https://esm.sh/react@18.3.1";
import { createRoot } from "https://esm.sh/react-dom@18.3.1/client";
import htm from "https://esm.sh/htm@3.1.1";

const MODULE_VERSION = "20260419a";

import {
  apiGet,
  apiPost,
  clearAuthToken,
  clearStoredTaskIds,
  getAuthToken,
  loadStoredTaskIds,
  rememberTaskId,
  storeAuthToken,
} from "./api.js?v=20260419a";
import { DEMO_ACCOUNTS, DEMO_QUESTIONS, navItemsFor } from "./config.js?v=20260419a";
import { Layout } from "./components.js?v=20260419a";
import { KnowledgePage, OverviewPage } from "./pages-overview-knowledge.js?v=20260419a";

const html = htm.bind(React.createElement);

class RootErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("Root render failed", error, info);
  }

  render() {
    if (this.state.error) {
      return html`
        <div className="center-panel" style=${{ maxWidth: "960px" }}>
          <h2>页面渲染失败</h2>
          <p className="muted">${String(this.state.error?.message || this.state.error)}</p>
          <pre className="code-block" style=${{ whiteSpace: "pre-wrap", textAlign: "left" }}>${String(this.state.error?.stack || "")}</pre>
        </div>
      `;
    }
    return this.props.children;
  }
}

function LoginPage({ html, accounts, onLogin }) {
  const [form, setForm] = useState({ username: "business", password: "business" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    try {
      setLoading(true);
      setError("");
      await onLogin(form);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return html`
    <div className="center-panel" style=${{ maxWidth: "960px" }}>
      <h2>登录采购协同平台</h2>
      <p className="muted">不同角色登录后只会看到自己应该处理的页面和项目数据。演示账号的用户名和密码相同。</p>
      <div className="knowledge-layout" style=${{ marginTop: "20px" }}>
        <section className="panel">
          <h3>账号登录</h3>
          <form className="stack-list" onSubmit=${submit}>
            <div>
              <label className="label">用户名</label>
              <input className="field" value=${form.username} onInput=${(event) => setForm({ ...form, username: event.target.value })} />
            </div>
            <div>
              <label className="label">密码</label>
              <input className="field" type="password" value=${form.password} onInput=${(event) => setForm({ ...form, password: event.target.value })} />
            </div>
            ${error ? html`<div className="error">${error}</div>` : null}
            <div className="button-row">
              <button className="btn primary" type="submit" disabled=${loading}>${loading ? "登录中..." : "登录"}</button>
            </div>
          </form>
        </section>

        <section className="panel">
          <h3>演示账号</h3>
          <div className="stack-list">
            ${(accounts || DEMO_ACCOUNTS).map(
              (account) => html`
                <button
                  key=${account.username}
                  className="project-list-item"
                  onClick=${() => setForm({ username: account.username, password: account.password || account.username })}
                >
                  <div className="activity-main">
                    <strong>${account.label || account.display_name}</strong>
                    <div className="subtle">${account.username} / ${account.password || account.username}</div>
                  </div>
                </button>
              `,
            )}
          </div>
        </section>
      </div>
    </div>
  `;
}

function App() {
  const [page, setPage] = useState("overview");
  const [projectNavigationRequest, setProjectNavigationRequest] = useState(null);
  const [currentUser, setCurrentUser] = useState(null);
  const [demoAccounts, setDemoAccounts] = useState(DEMO_ACCOUNTS);
  const [sources, setSources] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [traces, setTraces] = useState([]);
  const [cases, setCases] = useState([]);
  const [projects, setProjects] = useState([]);
  const [latestTraceId, setLatestTraceId] = useState("");
  const [draftQuestion, setDraftQuestion] = useState(DEMO_QUESTIONS[1]);
  const [assistantTask, setAssistantTask] = useState(null);
  const [assistantResult, setAssistantResult] = useState(null);
  const [projectsPageComponent, setProjectsPageComponent] = useState(null);
  const [projectsPageError, setProjectsPageError] = useState("");
  const [assistantPageComponent, setAssistantPageComponent] = useState(null);
  const [auditPageComponent, setAuditPageComponent] = useState(null);
  const [assistantModuleError, setAssistantModuleError] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const navItems = useMemo(() => navItemsFor(currentUser?.role), [currentUser]);

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
    if (!currentUser) return;
    try {
      if (!silent) setLoading(true);
      setError("");

      if (currentUser.role === "admin") {
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
      } else {
        const projectData = await apiGet("/projects");
        setProjects(projectData);
        setSources([]);
        setTasks([]);
        setTraces([]);
        setCases([]);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      if (!silent) setLoading(false);
    }
  }

  async function bootstrap() {
    try {
      setLoading(true);
      const accounts = await apiGet("/auth/demo-accounts");
      setDemoAccounts(accounts.map((item) => ({ ...item, password: item.username, label: item.display_name })));
    } catch (_) {
      setDemoAccounts(DEMO_ACCOUNTS);
    }

    if (!getAuthToken()) {
      setCurrentUser(null);
      setLoading(false);
      return;
    }

    try {
      const me = await apiGet("/auth/me");
      setCurrentUser(me);
    } catch (_) {
      clearAuthToken();
      setCurrentUser(null);
    } finally {
      setLoading(false);
    }
  }

  async function handleLogin(credentials) {
    const payload = await apiPost("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(credentials),
    });
    storeAuthToken(payload.token);
    setCurrentUser(payload.user);
    setPage(navItemsFor(payload.user.role)[0]?.id || "overview");
  }

  async function handleLogout() {
    try {
      await apiPost("/auth/logout", { method: "POST" });
    } catch (_) {
      // token cleanup still happens locally
    }
    clearAuthToken();
    setCurrentUser(null);
    setProjects([]);
    setSources([]);
    setTasks([]);
    setTraces([]);
    setCases([]);
    setLatestTraceId("");
    setDraftQuestion(DEMO_QUESTIONS[1]);
    setAssistantTask(null);
    setAssistantResult(null);
    setProjectNavigationRequest(null);
    setError("");
    clearStoredTaskIds();
    setPage("overview");
    setLoading(false);
  }

  function rememberTask(taskId) {
    rememberTaskId(taskId);
    loadTasks();
  }

  useEffect(() => {
    bootstrap();
  }, []);

  useEffect(() => {
    if (!currentUser) return;
    const allowedPages = navItemsFor(currentUser.role).map((item) => item.id);
    if (!allowedPages.includes(page)) {
      setPage(allowedPages[0] || "overview");
    }
    refreshAll();
  }, [currentUser]);

  useEffect(() => {
    if (page !== "projects") return;
    if (projectsPageComponent || projectsPageError) return;
    let cancelled = false;
    import(`./pages-projects.js?v=${MODULE_VERSION}`)
      .then((module) => {
        if (cancelled) return;
        setProjectsPageComponent(() => module.ProjectsPage);
      })
      .catch((err) => {
        if (cancelled) return;
        setProjectsPageError(err?.message || String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [page, projectsPageComponent, projectsPageError]);

  useEffect(() => {
    if (!["assistant", "audit"].includes(page)) return;
    if ((page === "assistant" && assistantPageComponent) || (page === "audit" && auditPageComponent) || assistantModuleError) return;
    let cancelled = false;
    import(`./pages-assistant-audit.js?v=${MODULE_VERSION}`)
      .then((module) => {
        if (cancelled) return;
        setAssistantPageComponent(() => module.AssistantPage);
        setAuditPageComponent(() => module.AuditPage);
      })
      .catch((err) => {
        if (cancelled) return;
        setAssistantModuleError(err?.message || String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [page, assistantPageComponent, auditPageComponent, assistantModuleError]);

  function openProjectWorkspace(projectId) {
    if (!projectId) return;
    setProjectNavigationRequest({ projectId, nonce: Date.now() });
    setPage("projects");
  }

  function renderPage() {
    if (!currentUser) {
      return html`<${LoginPage} html=${html} accounts=${demoAccounts} onLogin=${handleLogin} />`;
    }

    if (loading) {
      return html`
        <div className="center-panel">
          <div className="loading-ring"></div>
          <h3>正在加载角色工作台</h3>
          <p className="muted">系统正在按当前账号身份加载你可见的项目和功能模块。</p>
        </div>
      `;
    }

    if (error) {
      return html`
        <div className="center-panel">
          <h3>页面初始化失败</h3>
          <p className="muted">${error}</p>
          <div className="button-row">
            <button className="btn primary" onClick=${refreshAll}>重新加载</button>
          </div>
        </div>
      `;
    }

    if (page === "knowledge" && currentUser.role === "admin") {
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
      if (projectsPageError) {
        return html`
          <div className="center-panel">
            <h3>采购执行页加载失败</h3>
            <p className="muted">${projectsPageError}</p>
          </div>
        `;
      }
      if (!projectsPageComponent) {
        return html`
          <div className="center-panel">
            <div className="loading-ring"></div>
            <h3>正在加载采购执行页</h3>
          </div>
        `;
      }
      const ProjectsPage = projectsPageComponent;
      return html`
        <${ProjectsPage}
          html=${html}
          projects=${projects}
          currentUser=${currentUser}
          refreshAll=${refreshAll}
          onNavigate=${setPage}
          setDraftQuestion=${setDraftQuestion}
          assistantTask=${assistantTask}
          assistantResult=${assistantResult}
          setAssistantTask=${setAssistantTask}
          setAssistantResult=${setAssistantResult}
          projectNavigationRequest=${projectNavigationRequest}
          onTraceCreated=${(traceId) => setLatestTraceId(traceId)}
        />
      `;
    }

    if (page === "assistant" && currentUser.role !== "business") {
      if (assistantModuleError) {
        return html`
          <div className="center-panel">
            <h3>审查助手加载失败</h3>
            <p className="muted">${assistantModuleError}</p>
          </div>
        `;
      }
      if (!assistantPageComponent) {
        return html`
          <div className="center-panel">
            <div className="loading-ring"></div>
            <h3>正在加载审查助手</h3>
          </div>
        `;
      }
      const AssistantPage = assistantPageComponent;
      return html`
        <${AssistantPage}
          html=${html}
          currentUser=${currentUser}
          draftQuestion=${draftQuestion}
          setDraftQuestion=${setDraftQuestion}
          assistantTask=${assistantTask}
          setAssistantTask=${setAssistantTask}
          assistantResult=${assistantResult}
          setAssistantResult=${setAssistantResult}
          onNavigate=${setPage}
          onTraceCreated=${(traceId) => {
            setLatestTraceId(traceId);
            if (currentUser.role === "admin") refreshAll({ silent: true });
          }}
        />
      `;
    }

    if (page === "audit" && currentUser.role === "admin") {
      if (assistantModuleError) {
        return html`
          <div className="center-panel">
            <h3>审计页面加载失败</h3>
            <p className="muted">${assistantModuleError}</p>
          </div>
        `;
      }
      if (!auditPageComponent) {
        return html`
          <div className="center-panel">
            <div className="loading-ring"></div>
            <h3>正在加载审计页面</h3>
          </div>
        `;
      }
      const AuditPage = auditPageComponent;
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
        currentUser=${currentUser}
        sources=${sources}
        tasks=${tasks}
        traces=${traces}
        cases=${cases}
        projects=${projects}
        setPage=${setPage}
        openProjectWorkspace=${openProjectWorkspace}
        setDraftQuestion=${setDraftQuestion}
      />
    `;
  }

  if (!currentUser) {
    return renderPage();
  }

  return html`
    <${Layout}
      html=${html}
      page=${page}
      setPage=${setPage}
      navItems=${navItems}
      currentUser=${currentUser}
      onLogout=${handleLogout}
    >
      ${renderPage()}
    </${Layout}>
  `;
}

createRoot(document.getElementById("root")).render(html`<${RootErrorBoundary}><${App} /></${RootErrorBoundary}>`);
