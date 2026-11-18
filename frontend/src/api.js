export const API_BASE = "http://127.0.0.1:8000";

export async function fetchApi(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const isFormData = options.body instanceof FormData;
  const headers = isFormData
    ? { ...options.headers }
    : { "Content-Type": "application/json", ...options.headers };

  const res = await fetch(url, {
    ...options,
    headers,
  });
  if (!res.ok) {
    let errMsg = `Error ${res.status}`;
    try {
      const data = await res.json();
      errMsg = data.detail || JSON.stringify(data);
    } catch (_) {
      errMsg = await res.text();
    }
    throw new Error(errMsg);
  }
  return res.json();
}

export const api = {
  getHealth: () => fetchApi("/health"),
  getPulpoStatus: () => fetchApi("/pulpo/status"),
  getStatsSummary: () => fetchApi("/stats/summary"),
  getJobStatus: (jobId) => fetchApi(`/jobs/${jobId}`),
  writeTitles: (summary, hook) =>
    fetchApi("/pulpo/write-titles", {
      method: "POST",
      body: JSON.stringify({ summary, hook }),
    }),

  // Projects
  createProject: (url, title, sourceType) =>
    fetchApi("/projects", {
      method: "POST",
      body: JSON.stringify({ url, title, source_type: sourceType }),
    }),
  uploadProjectFile: (file, title) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("title", title || file.name);
    return fetchApi("/projects/upload", { method: "POST", body: fd });
  },
  listProjects: () => fetchApi("/projects"),
  getProject: (id) => fetchApi(`/projects/${id}`),
  deleteProject: (id) => fetchApi(`/projects/${id}`, { method: "DELETE" }),
  analyzeProject: (id) => fetchApi(`/projects/${id}/analyze`, { method: "POST" }),
  getMoments: (projectId) => fetchApi(`/projects/${projectId}/moments`),
  getTranscript: (projectId) => fetchApi(`/projects/${projectId}/transcript`),

  // Clips
  createClip: (data) => fetchApi("/clips", { method: "POST", body: JSON.stringify(data) }),
  listClips: (projectId) => fetchApi(projectId ? `/clips?project_id=${projectId}` : "/clips"),
  getClip: (id) => fetchApi(`/clips/${id}`),
  updateClip: (id, data) => fetchApi(`/clips/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteClip: (id) => fetchApi(`/clips/${id}`, { method: "DELETE" }),
  renderClip: (id) => fetchApi(`/clips/${id}/render`, { method: "POST" }),

  // Studio Motion Graphics
  createStudioVideo: (topic, style, voiceName) =>
    fetchApi("/studio", {
      method: "POST",
      body: JSON.stringify({ topic, style, voice_name: voiceName }),
    }),
  renderStudioVideo: (id) => fetchApi(`/studio/${id}/render`, { method: "POST" }),
  listStudioVideos: () => fetchApi("/studio"),

  // Accounts & Centralized OAuth
  listAccounts: () => fetchApi("/accounts"),
  getOAuthConfigStatus: () => fetchApi("/oauth/config-status"),
  saveOAuthCredentials: (data) =>
    fetchApi("/oauth/credentials", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getMetaOAuthStart: () => fetchApi("/oauth/meta/start"),
  getTikTokOAuthStart: () => fetchApi("/oauth/tiktok/start"),
  verifyMetaToken: (accessToken) =>
    fetchApi("/accounts/verify-meta", {
      method: "POST",
      body: JSON.stringify({ access_token: accessToken }),
    }),
  verifyTikTokToken: (accessToken) =>
    fetchApi("/accounts/verify-tiktok", {
      method: "POST",
      body: JSON.stringify({ access_token: accessToken }),
    }),
  verifyExistingAccount: (id) => fetchApi(`/accounts/${id}/verify`, { method: "POST" }),
  deleteAccount: (id) => fetchApi(`/accounts/${id}`, { method: "DELETE" }),

  // Posts
  createPost: (data) => fetchApi("/posts", { method: "POST", body: JSON.stringify(data) }),
  listPosts: () => fetchApi("/posts"),

  // Higgsfield Cinematic Studio
  getHiggsfieldStatus: () => fetchApi("/higgsfield/status"),
  generateCinematicBroll: (prompt, motion, durationSec) =>
    fetchApi("/higgsfield/generate-broll", {
      method: "POST",
      body: JSON.stringify({
        prompt,
        camera: { motion, speed: 1.0, strength: 0.8 },
        aspect_ratio: "9:16",
        duration_sec: durationSec || 4.0,
      }),
    }),
};
