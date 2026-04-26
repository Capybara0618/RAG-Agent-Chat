import { API_BASE_URL } from "./config.js";

const AUTH_TOKEN_KEY = "procureops-auth-token";

function buildErrorMessage(status, text) {
  return text || `Request failed with status ${status}`;
}

function buildHeaders(initHeaders = {}) {
  const headers = new Headers(initHeaders);
  const token = getAuthToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return headers;
}

async function request(path, init = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: buildHeaders(init.headers || {}),
  });
  if (!response.ok) {
    if (response.status === 401) {
      clearAuthToken();
    }
    throw new Error(buildErrorMessage(response.status, await response.text()));
  }
  return response.json();
}

export function getAuthToken() {
  return sessionStorage.getItem(AUTH_TOKEN_KEY) || "";
}

export function storeAuthToken(token) {
  sessionStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function clearAuthToken() {
  sessionStorage.removeItem(AUTH_TOKEN_KEY);
}

export function clearStoredTaskIds() {
  localStorage.removeItem("procureops-task-ids");
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

export function openEventStream(path) {
  const url = new URL(`${API_BASE_URL}${path}`);
  const token = getAuthToken();
  if (token) {
    url.searchParams.set("token", token);
  }
  return new EventSource(url.toString());
}

export function loadStoredTaskIds() {
  return JSON.parse(localStorage.getItem("procureops-task-ids") || "[]");
}

export function rememberTaskId(taskId) {
  const merged = Array.from(new Set([...loadStoredTaskIds(), taskId])).slice(-20);
  localStorage.setItem("procureops-task-ids", JSON.stringify(merged));
  return merged;
}
