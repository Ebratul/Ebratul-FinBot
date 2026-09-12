const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function getAuthToken() {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("finbot_token");
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = headers["Content-Type"] || "application/json";
  }

  const token = getAuthToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  const contentType = response.headers.get("content-type") || "";
  const raw = await response.text();
  const data = raw && contentType.includes("application/json")
    ? JSON.parse(raw)
    : raw ? { message: raw } : {};

  if (!response.ok) {
    throw new Error(data.detail || data.message || "Request failed");
  }
  return data;
}

export async function login(username, password) {
  const data = await request("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  window.localStorage.setItem("finbot_token", data.token);
  return data.user;
}

export function logout() {
  if (typeof window !== "undefined") window.localStorage.removeItem("finbot_token");
}

export function getMe() { return request("/api/auth/me"); }
export function askAgent(query, sessionId) {
  return request("/api/agent", {
    method: "POST",
    body: JSON.stringify({ query, session_id: sessionId }),
  });
}
export function getChatSessions() { return request("/api/chat/sessions"); }
export function getChatHistory(sessionId) {
  return request(`/api/chat/sessions/${encodeURIComponent(sessionId)}`);
}
export function listUsers() { return request("/api/admin/users"); }
export function createUser(username, password, role, display_name) {
  return request("/api/admin/users", {
    method: "POST",
    body: JSON.stringify({ username, password, role, display_name }),
  });
}
export function deleteUser(userId) {
  return request(`/api/admin/users/${encodeURIComponent(userId)}`, { method: "DELETE" });
}
export function updateUserRole(userId, role) {
  return request(`/api/admin/users/${encodeURIComponent(userId)}/role`, {
    method: "PUT",
    body: JSON.stringify({ role }),
  });
}
export function listRoles() { return request("/api/admin/roles"); }
export function listDocuments() { return request("/api/admin/documents"); }
export function uploadDocument(file, collection) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("collection", collection);
  return request("/api/admin/documents/upload", { method: "POST", body: formData });
}
export function deleteDocument(collection, filename) {
  return request(
    `/api/admin/documents/${encodeURIComponent(collection)}/${encodeURIComponent(filename)}`,
    { method: "DELETE" },
  );
}
export function getEvaluationDataset() { return request("/api/evaluation/dataset"); }
export function runEvaluation(sampleSize) {
  const query = sampleSize ? `?sample_size=${encodeURIComponent(sampleSize)}` : "";
  return request(`/api/evaluation/run${query}`, { method: "POST" });
}
export function getLatestEvaluationResults() {
  return request("/api/evaluation/results");
}
