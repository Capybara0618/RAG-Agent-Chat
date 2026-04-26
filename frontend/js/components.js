import React, { useEffect } from "https://esm.sh/react@18.3.1";
import { API_BASE_URL, DEMO_QUESTIONS, displayLabel, toneOf } from "./config.js";

const NAV_ICONS = {
  overview: "layout-dashboard",
  projects: "workflow",
  knowledge: "database",
  assistant: "message-square-text",
  audit: "shield-check",
};

export function useLucide(deps = []) {
  useEffect(() => {
    if (window.lucide) window.lucide.createIcons();
  }, deps);
}

export function StatCard({ html, title, value, detail, tone = "neutral", icon = "" }) {
  return html`
    <article className="stat-card">
      ${icon ? html`<div className="stat-icon"><i data-lucide=${icon}></i></div>` : null}
      <div className="eyebrow">${title}</div>
      <div className="stat-value">${value}</div>
      <div className="status-badge ${tone}">${detail}</div>
    </article>
  `;
}

export function Layout({ html, page, setPage, navItems, currentUser, onLogout, children }) {
  useLucide([page, children]);

  return html`
    <div className="shell">
      <aside className="sidebar">
        <div className="brand-card">
          <div className="brand-icon"><i data-lucide="briefcase-business"></i></div>
          <div className="eyebrow">ProcureOps Flow</div>
          <h1>\u91c7\u8d2d\u5ba1\u67e5\u4e0e\u63a8\u8fdb\u5e73\u53f0</h1>
          <p>
            \u628a\u4f9b\u5e94\u5546\u51c6\u5165\u3001\u5b89\u5168\u8bc4\u5ba1\u3001\u5408\u540c\u7ea2\u7ebf\u5ba1\u67e5\u3001\u5ba1\u6279\u63a8\u8fdb\u548c
            AI \u95ee\u7b54\u653e\u5728\u540c\u4e00\u4e2a\u5de5\u4f5c\u53f0\u91cc\uff0c\u8ba9\u91c7\u8d2d\u3001\u6cd5\u52a1\u3001\u5b89\u5168\u4e00\u773c\u770b\u6e05\u9879\u76ee\u8d70\u5230\u54ea\u4e00\u6b65\u3002
          </p>
        </div>

        ${currentUser
          ? html`
              <div className="side-note">
                <div className="eyebrow">当前账号</div>
                <strong>${currentUser.display_name}</strong>
                <div className="subtle">${displayLabel(currentUser.role)} / ${currentUser.department || "未设置部门"}</div>
                <div className="button-row" style=${{ marginTop: "12px" }}>
                  <button className="btn ghost small" onClick=${onLogout}>退出登录</button>
                </div>
              </div>
            `
          : null}

        <nav className="nav-list">
          ${(navItems || []).map(
            (item) => html`
              <button
                key=${item.id}
                className=${page === item.id ? "nav-item active" : "nav-item"}
                onClick=${() => setPage(item.id)}
              >
                <i data-lucide=${NAV_ICONS[item.id] || "circle"}></i>
                <div className="nav-content">
                  <span className="nav-title">${item.title}</span>
                  <span className="nav-desc">${item.description}</span>
                </div>
              </button>
            `,
          )}
        </nav>

        <div className="side-note">
          <div className="eyebrow">\u5feb\u901f\u4f53\u9a8c</div>
          <div className="helper-stack">
            ${DEMO_QUESTIONS.slice(0, 3).map((item) => html`<div key=${item}>${item}</div>`)}
          </div>
          <div className="api-chip">
            <i data-lucide="server" style=${{ width: "12px", height: "12px" }}></i>
            ${API_BASE_URL}
          </div>
        </div>
      </aside>

      <main className="main">${children}</main>
    </div>
  `;
}

export function ActivityList({ html, items, emptyText, onPick }) {
  if (!items.length) {
    return html`<div className="empty-box">${emptyText}</div>`;
  }

  return html`
    <div className="stack-list">
      ${items.map(
        (item) => html`
          <div className="activity-item" key=${item.id || item.trace_id}>
            <div className="activity-main">
              <strong>${item.title || item.source_name || item.query}</strong>
              <div className="subtle">
                ${item.subtitle || displayLabel(item.task_mode || item.intent) || item.id || item.trace_id}
              </div>
            </div>
            <div className="activity-meta">
              ${item.status
                ? html`
                    <span className="status-badge ${toneOf(item.status)}">
                      ${displayLabel(item.status)}
                    </span>
                  `
                : null}
              ${item.next_action
                ? html`
                    <span className="status-badge ${toneOf(item.next_action)}">
                      ${displayLabel(item.next_action)}
                    </span>
                  `
                : null}
              ${onPick
                ? html`
                    <button className="btn ghost small" onClick=${() => onPick(item)}>
                      <i data-lucide="external-link" style=${{ width: "13px", height: "13px" }}></i>
                      \u67e5\u770b
                    </button>
                  `
                : null}
            </div>
          </div>
        `,
      )}
    </div>
  `;
}
