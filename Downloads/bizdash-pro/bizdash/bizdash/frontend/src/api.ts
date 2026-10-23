let token = localStorage.getItem("token") || "";
export const hasToken = () => !!token;
export function setToken(t: string) {
  token = t;
  t ? localStorage.setItem("token", t) : localStorage.removeItem("token");
}
export async function api<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const isForm = opts.body instanceof URLSearchParams || opts.body instanceof FormData;
  const res = await fetch("/api" + path, {
    ...opts,
    headers: {
      ...(opts.body && !isForm ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: "Bearer " + token } : {}),
    },
  });
  if (res.status === 401 && token) { setToken(""); location.reload(); }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : "Request failed");
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const upload = (path: string, file: File) => {
  const fd = new FormData(); fd.append("file", file);
  return api<unknown>(path, { method: "POST", body: fd });
};

export async function download(path: string, filename: string) {
  const res = await fetch("/api" + path, { headers: token ? { Authorization: "Bearer " + token } : {} });
  if (!res.ok) throw new Error("Export failed");
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a"); a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url);
}
