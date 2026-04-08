import { API_BASE_URL } from "./config.js";

function buildErrorMessage(status, text) {
  return text || `Request failed with status ${status}`;
}

async function request(path, init = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!response.ok) {
    throw new Error(buildErrorMessage(response.status, await response.text()));
  }
  return response.json();
}

export function apiGet(path) {
  return request(path);
}

export function apiPost(path, init) {
  return request(path, init);
}

export function apiPatch(path, body) {
  return request(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function loadStoredTaskIds() {
  return JSON.parse(localStorage.getItem("procureops-task-ids") || "[]");
}

export function rememberTaskId(taskId) {
  const merged = Array.from(new Set([...loadStoredTaskIds(), taskId])).slice(-20);
  localStorage.setItem("procureops-task-ids", JSON.stringify(merged));
  return merged;
}
