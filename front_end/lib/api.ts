import type { ApiResponse } from "@/lib/types";

let refreshing: Promise<boolean> | null = null;

async function refreshSession() {
  const response = await fetch("/api/auth/refresh", { method: "POST", credentials: "include" });
  return response.ok;
}

export async function api<T>(path: string, init: RequestInit = {}, retry = true): Promise<ApiResponse<T>> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...init, headers, credentials: "include", cache: "no-store" });
  if (response.status === 401 && retry && !path.includes("/auth/")) {
    refreshing ??= refreshSession().finally(() => { refreshing = null; });
    if (await refreshing) return api<T>(path, init, false);
    window.location.href = "/login";
  }
  const payload = await response.json().catch(() => ({ success: false, message: "Respons server tidak valid.", data: null, meta: {} }));
  if (!response.ok) throw new Error(payload.message ?? payload.detail ?? "Permintaan gagal.");
  return payload as ApiResponse<T>;
}
