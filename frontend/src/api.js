const API_BASE = "http://127.0.0.1:8000";

export async function fetchApi(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`API Error ${res.status}: ${errorText}`);
  }
  return res.json();
}

export const api = {
  getHealth: () => fetchApi("/health"),
  getPulpoStatus: () => fetchApi("/pulpo/status"),
  getStatsSummary: () => fetchApi("/stats/summary"),
  
  // Projects
  createProject: (url, title, sourceType) => fetchApi("/projects", {
    method: "POST",
    body: JSON.stringify({ url, title, source_type: sourceType })
  }),
  listProjects: () => fetchApi("/projects"),
  getProject: (id) => fetchApi(`/projects/${id}`),
  analyzeProject: (id) => fetchApi(`/projects/${id}/analyze`, { method: "POST" }),
  getMoments: (projectId) => fetchApi(`/projects/${projectId}/moments`),

  // Clips
  createClip: (data) => fetchApi("/clips", { method: "POST", body: JSON.stringify(data) }),
  listClips: (projectId) => fetchApi(projectId ? `/clips?project_id=${projectId}` : "/clips"),
  getClip: (id) => fetchApi(`/clips/${id}`),
  updateClip: (id, data) => fetchApi(`/clips/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  renderClip: (id) => fetchApi(`/clips/${id}/render`, { method: "POST" }),

  // Studio
  createStudioVideo: (topic, style) => fetchApi("/studio", {
    method: "POST",
    body: JSON.stringify({ topic, style })
  }),
  listStudioVideos: () => fetchApi("/studio"),

  // Accounts & Posts
  listAccounts: () => fetchApi("/accounts"),
  connectAccount: (data) => fetchApi("/accounts", { method: "POST", body: JSON.stringify(data) }),
  createPost: (data) => fetchApi("/posts", { method: "POST", body: JSON.stringify(data) }),
  listPosts: () => fetchApi("/posts"),
};
