import axios from "axios";

const API_BASE = import.meta.env.DEV ? "" : "";

export const api = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
});

// Attach access token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Auto-refresh on 401
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config;
    if (err.response?.status === 401 && !original._retry) {
      original._retry = true;
      const refresh = localStorage.getItem("refresh_token");
      if (refresh) {
        try {
          const { data } = await axios.post("/auth/refresh", { refresh_token: refresh });
          localStorage.setItem("access_token", data.access_token);
          localStorage.setItem("refresh_token", data.refresh_token);
          original.headers.Authorization = `Bearer ${data.access_token}`;
          return api(original);
        } catch {
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
          window.location.href = "/login";
        }
      } else {
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);

// Typed API helpers
export const authApi = {
  login: (username: string, password: string) =>
    api.post("/auth/login", { username, password }),
  logout: (refresh_token: string) =>
    api.post("/auth/logout", { refresh_token }),
  me: () => api.get("/auth/me"),
};

export const incidentsApi = {
  list: (params?: Record<string, string | number>) =>
    api.get("/api/incidents", { params }),
  get: (id: number) => api.get(`/api/incidents/${id}`),
  resolve: (id: number) => api.patch(`/api/incidents/${id}/resolve`),
  stats: (hours = 24) => api.get("/api/stats", { params: { hours } }),
  heatmap: (hours = 24) => api.get("/api/heatmap", { params: { hours } }),
  hourlyHeatmap: (hours = 168) =>
    api.get("/api/analytics/hourly-heatmap", { params: { hours } }),
};

export const zonesApi = {
  list: () => api.get("/api/zones"),
  get: (id: number) => api.get(`/api/zones/${id}`),
  create: (data: object) => api.post("/api/zones", data),
  update: (id: number, data: object) => api.patch(`/api/zones/${id}`, data),
  delete: (id: number) => api.delete(`/api/zones/${id}`),
  addAlertRule: (zoneId: number, data: object) =>
    api.post(`/api/zones/${zoneId}/alert-rules`, data),
};

export const usersApi = {
  list: () => api.get("/api/users"),
  create: (data: object) => api.post("/api/users", data),
  update: (id: number, data: object) => api.patch(`/api/users/${id}`, data),
  delete: (id: number) => api.delete(`/api/users/${id}`),
};

export const reportsApi = {
  list: () => api.get("/api/reports"),
  generate: (data: object) => api.post("/api/reports/generate", data),
  download: (id: number) => api.get(`/api/reports/${id}/download`, { responseType: "blob" }),
};

export const approvedPersonsApi = {
  list: () => api.get("/api/approved-persons"),
  enroll: (name: string, image_b64: string, notes?: string) =>
    api.post("/api/approved-persons/enroll", { name, image_b64, notes }),
  batchEnroll: (persons: { name: string; image_b64: string; notes?: string }[]) =>
    api.post("/api/approved-persons/batch-enroll", { persons }),
  update: (id: number, data: { name?: string; notes?: string }) =>
    api.patch(`/api/approved-persons/${id}`, data),
  remove: (id: number) => api.delete(`/api/approved-persons/${id}`),
};

export const firePIR = (zone?: string) =>
  api.post("/api/pir/fire", null, { params: zone ? { zone } : {} });
