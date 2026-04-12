import React, { useEffect, useMemo, useState } from "https://esm.sh/react@18.3.1";
import { createRoot } from "https://esm.sh/react-dom@18.3.1/client";
import htm from "https://esm.sh/htm@3.1.1";

import {
  apiGet,
  apiPost,
  clearAuthToken,
  clearStoredTaskIds,
  getAuthToken,
  loadStoredTaskIds,
  rememberTaskId,
  storeAuthToken,
} from "./api.js";
import { DEMO_ACCOUNTS, DEMO_QUESTIONS, navItemsFor } from "./config.js";
import { Layout } from "./components.js";
import { AssistantPage, AuditPage } from "./pages-assistant-audit.js";
import { KnowledgePage, OverviewPage } from "./pages-overview-knowledge.js";
import { ProjectsPage } from "./pages-projects.js";

const html = htm.bind(React.createElement);

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
      return html`
        <${ProjectsPage}
          html=${html}
          projects=${projects}
          currentUser=${currentUser}
          refreshAll=${refreshAll}
          onNavigate=${setPage}
          setDraftQuestion=${setDraftQuestion}
          assistantTask=${assistantTask}
          setAssistantTask=${setAssistantTask}
          setAssistantResult=${setAssistantResult}
          onTraceCreated=${(traceId) => setLatestTraceId(traceId)}
        />
      `;
    }

    if (page === "assistant" && currentUser.role !== "business") {
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

createRoot(document.getElementById("root")).render(html`<${App} />`);
