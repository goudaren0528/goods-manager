
export interface GoodsItem {
  ID: string;
  商品名称: string;
  短标题?: string;
  SKU?: string;
  库存?: number;
  [key: string]: unknown;
}

export interface RentCurve {
  id?: string;
  name: string;
  source_sku?: string;
  source_name?: string;
  created_at?: string;
  multipliers: Record<string, number>;
}

export interface GoodsGroup {
  ID: string;
  商品名称: string;
  短标题?: string;
  "1级分类"?: string;
  "2级分类"?: string;
  "3级分类"?: string;
  库存: number;
  skus: GoodsItem[];
  merchant?: string;
  是否同步支付宝?: string;
  最近提交时间?: string;
  商品图片?: string;
  支付宝编码?: string;
}

type ApiErrorShape = {
  status?: string;
  message?: string;
};

const isServer = typeof window === 'undefined';

const cleanEnvUrl = (value: string) => value.replace(/^`|`$/g, "").replace(/^"|"$/g, "").replace(/^'|'$/g, "").trim();

const getErrorMessage = (data: unknown): string | undefined => {
  if (data && typeof data === "object") {
    const candidate = data as ApiErrorShape;
    if (typeof candidate.message === "string") {
      return candidate.message;
    }
  }
  return undefined;
};

const hasErrorStatus = (data: unknown): boolean => {
  if (data && typeof data === "object") {
    const candidate = data as ApiErrorShape;
    return candidate.status === "error";
  }
  return false;
};

const getClientApiBase = () => {
  const raw = (process.env.NEXT_PUBLIC_API_URL || "").trim();
  const cleaned = cleanEnvUrl(raw);
  if (!cleaned) return "/api";
  let url = cleaned;
  if (!isServer) {
    const host = window.location.hostname;
    const isLocalHost = host === "localhost" || host === "127.0.0.1";
    if (!isLocalHost && (url.includes("localhost") || url.includes("127.0.0.1"))) {
      return "/api";
    }
  }
  if (!isServer && window.location.protocol === "https:" && url.startsWith("http:")) {
    url = url.replace("http:", "https:");
  }
  const isAbsolute = /^[a-zA-Z][a-zA-Z\d+\-.]*:/.test(url);
  const isRootRelative = url.startsWith("/");
  if (isAbsolute || isRootRelative) {
    const parsed = new URL(url, window.location.origin);
    const path = parsed.pathname.replace(/\/+$/, "");
    if (parsed.origin === window.location.origin && (path === "" || path === "/")) {
      return "/api";
    }
    return `${parsed.origin}${path}`;
  }
  return url.replace(/\/+$/, "");
};

const getServerApiBase = () => {
  const internal = cleanEnvUrl(process.env.INTERNAL_API_URL || "");
  if (internal) return internal.replace(/\/+$/, "");
  const publicUrl = cleanEnvUrl(process.env.NEXT_PUBLIC_API_URL || "");
  if (publicUrl) return publicUrl.replace(/\/+$/, "");
  return "http://server:8000";
};

export const API_BASE = isServer ? getServerApiBase() : getClientApiBase();
export const EXPORT_URL = `${API_BASE}/export-excel`;

// Robust fetch wrapper
async function fetchApi<T>(endpoint: string, options: RequestInit = {}, errorMessage: string = "Request failed"): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  let res: Response;
  
  try {
    res = await fetch(url, options);
  } catch (e) {
    // Network error - try fallback if on client and not already using proxy
    if (!isServer && API_BASE !== "/api") {
      console.warn(`Fetch failed for ${url}, trying fallback to /api${endpoint}`);
      try {
        res = await fetch(`/api${endpoint}`, options);
      } catch {
        throw e;
      }
    } else {
      throw e;
    }
  }

  const contentType = res.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");

  // If not JSON, or if we want to be extra safe, read text first
  const text = await res.text();
  
  // Check for HTML response
  if (text.trim().startsWith("<") || !isJson) {
    // If it looks like HTML/XML or isn't JSON
    if (!isServer && API_BASE !== "/api") {
      console.warn(`Received HTML/Non-JSON for ${url}, trying fallback to /api${endpoint}`);
      try {
        const fallbackRes = await fetch(`/api${endpoint}`, options);
        const fallbackText = await fallbackRes.text();
        const fallbackContentType = fallbackRes.headers.get("content-type") || "";
        
        if (fallbackContentType.includes("application/json")) {
           try {
             const data = JSON.parse(fallbackText);
             if (!fallbackRes.ok) throw new Error(data.message || errorMessage);
             return data;
           } catch {
             // Fallback also failed parsing
           }
        }
        throw new Error(`${errorMessage}: Fallback returned ${fallbackRes.status} (${fallbackContentType})`);
      } catch (fallbackErr) {
        console.error("Fallback failed", fallbackErr);
      }
    }
    
    // Construct meaningful error for HTML response
    const preview = text.slice(0, 100).replace(/\n/g, " ");
    throw new Error(`${errorMessage}: Received HTML/Invalid response (${res.status}): ${preview}...`);
  }

  // Parse JSON
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error(`${errorMessage}: Failed to parse JSON response`);
  }

  if (!res.ok) {
    // If error response has a specific structure with 'status': 'error', handle it
    const message = getErrorMessage(data);
    if (hasErrorStatus(data) && message) {
      throw new Error(message);
    }
    throw new Error(message || errorMessage);
  }
  
  // Also check for { status: "error" } in success responses (legacy API style)
  if (hasErrorStatus(data)) {
    const message = getErrorMessage(data);
    throw new Error(message || errorMessage);
  }

  return data as T;
}

export async function fetchRentCurves(): Promise<RentCurve[]> {
  return fetchApi<RentCurve[]>("/rent-curves", { cache: 'no-store' }, "Failed to fetch rent curves");
}

export async function saveRentCurve(curve: RentCurve) {
  return fetchApi("/rent-curves", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(curve),
  }, "Failed to save rent curve");
}

export async function deleteRentCurve(id_or_name: string) {
  return fetchApi(`/rent-curves/${encodeURIComponent(id_or_name)}`, {
    method: "DELETE",
  }, "Failed to delete rent curve");
}

export interface FetchGoodsResponse {
  data: GoodsGroup[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

export async function fetchGoods(page: number, limit: number, allData = false, merchant?: string, syncStatus?: string, sortBy?: string, sortDesc?: boolean): Promise<FetchGoodsResponse> {
  const params = new URLSearchParams({
    page: page.toString(),
    limit: limit.toString(),
    all_data: allData.toString(),
  });
  if (merchant) params.append("merchant", merchant);
  if (syncStatus) params.append("sync_status", syncStatus);
  if (sortBy) params.append("sort_by", sortBy);
  if (sortDesc !== undefined) params.append("sort_desc", sortDesc ? "true" : "false");

  return fetchApi<FetchGoodsResponse>(`/goods?${params.toString()}`, { cache: "no-store" }, "Failed to fetch goods");
}

export const runScrape = async (): Promise<Record<string, unknown>> => {
  return fetchApi("/run-scrape", { method: "POST" }, "Failed to run scrape");
};

export const runPartialScrape = async (ids: string[]): Promise<Record<string, unknown>> => {
  return fetchApi("/run-scrape-partial", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids }),
  }, "Failed to run partial scrape");
};

export const prepareUpdate = async (items: Partial<GoodsItem>[]): Promise<Record<string, unknown>> => {
  return fetchApi("/prepare-update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items }),
  }, "Failed to prepare update data");
}

export async function triggerUpdate() {
  return fetchApi("/trigger-update", { method: "POST" }, "Failed to trigger update");
}

export const fetchLogs = async (): Promise<{ logs: string }> => {
  return fetchApi<{ logs: string }>("/logs", {}, "Failed to fetch logs");
};

export const fetchTaskStatus = async (): Promise<{ running: boolean; task_name: string | null; message: string; progress: number; last_updated?: string }> => {
  return fetchApi("/task-status", { cache: "no-store" }, "Failed to fetch task status");
};

export async function stopTask() {
  return fetchApi("/stop-task", { method: "POST" }, "Failed to stop task");
}

export async function updateMerchant(id: string, merchant: string) {
  return fetchApi(`/goods/${id}/merchant`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ merchant }),
  }, "Failed to update merchant");
}

export async function updateAlipayCode(id: string, code: string) {
  return fetchApi(`/goods/${id}/field`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ field: "支付宝编码", value: code }),
  }, "Failed to update alipay code");
}

export async function deleteGoods(id: string) {
  return fetchApi(`/goods/${id}`, { method: "DELETE" }, "Failed to delete goods");
}

export async function fetchConfig(): Promise<Record<string, string>> {
  try {
    return await fetchApi<Record<string, string>>("/config", {}, "Failed to fetch config");
  } catch (e) {
    console.error(e);
    return {};
  }
}

export async function updateConfig(key: string, value: string) {
  return fetchApi("/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, value }),
  }, "Failed to update config");
}

export interface AutomationStatus {
  status: "idle" | "running" | "waiting_for_captcha" | "finished" | "error";
  message: string;
  timestamp?: number;
  total?: number;
  processed?: number;
  success_count?: number;
  error_count?: number;
  current_id?: string;
  current_code?: string;
  step?: string;
}

export async function startAutomation(ids: string[], phone: string) {
  return fetchApi("/automation/alipay/update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids, phone }),
  }, "Failed to start automation");
}

export async function getAutomationStatus(): Promise<AutomationStatus> {
  return fetchApi<AutomationStatus>("/automation/status", { cache: 'no-store' }, "Failed to get status");
}

export async function submitCaptcha(code: string) {
  return fetchApi("/automation/captcha", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  }, "Failed to submit captcha");
}
