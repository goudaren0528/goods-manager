
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

export async function fetchRentCurves(): Promise<RentCurve[]> {
  const res = await fetch(`${API_BASE}/rent-curves`, { cache: 'no-store' });
  if (!res.ok) return [];
  return res.json();
}

export async function saveRentCurve(curve: RentCurve) {
  const res = await fetch(`${API_BASE}/rent-curves`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(curve),
  });
  if (!res.ok) throw new Error("Failed to save rent curve");
  return res.json();
}

export async function deleteRentCurve(id_or_name: string) {
  const res = await fetch(`${API_BASE}/rent-curves/${encodeURIComponent(id_or_name)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete rent curve");
  return res.json();
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

const isServer = typeof window === 'undefined';

const cleanEnvUrl = (value: string) => value.replace(/^`|`$/g, "").replace(/^"|"$/g, "").replace(/^'|'$/g, "").trim();

const getClientApiBase = () => {
  const raw = (process.env.NEXT_PUBLIC_API_URL || "").trim();
  const cleaned = cleanEnvUrl(raw);
  if (!cleaned) return "/api";
  let url = cleaned;
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

const parseJsonResponse = async <T>(res: Response, fallbackPath: string, errorMessage: string): Promise<T> => {
  const contentType = res.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    const text = await res.text();
    if (!isServer && fallbackPath && API_BASE !== "/api") {
      const retry = await fetch(`/api${fallbackPath}`, { cache: "no-store" });
      const retryContentType = retry.headers.get("content-type") || "";
      if (retryContentType.includes("application/json")) {
        if (!retry.ok) {
          const err = await retry.json().catch(() => null);
          throw new Error((err as { message?: string } | null)?.message || errorMessage);
        }
        return retry.json();
      }
      const retryText = await retry.text();
      throw new Error(`${errorMessage}: ${retry.status} ${retryText.slice(0, 200)}`);
    }
    throw new Error(`${errorMessage}: ${res.status} ${text.slice(0, 200)}`);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    throw new Error((err as { message?: string } | null)?.message || errorMessage);
  }
  return res.json();
};

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

  const path = `/goods?${params.toString()}`;
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  return parseJsonResponse<FetchGoodsResponse>(res, path, "Failed to fetch goods");
}

export const runScrape = async (): Promise<Record<string, unknown>> => {
  const res = await fetch(`${API_BASE}/run-scrape`, {
    method: "POST",
  });
  if (!res.ok) {
    throw new Error("Failed to run scrape");
  }
  const data = await res.json();
  if ((data as { status?: string; message?: string }).status === "error") {
    throw new Error((data as { message?: string }).message || "Failed to run scrape");
  }
  return data;
};

export const runPartialScrape = async (ids: string[]): Promise<Record<string, unknown>> => {
  const res = await fetch(`${API_BASE}/run-scrape-partial`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids }),
  });
  if (!res.ok) {
    throw new Error("Failed to run partial scrape");
  }
  const data = await res.json();
  if ((data as { status?: string; message?: string }).status === "error") {
    throw new Error((data as { message?: string }).message || "Failed to run partial scrape");
  }
  return data;
};

export const prepareUpdate = async (items: Partial<GoodsItem>[]): Promise<Record<string, unknown>> => {
  const res = await fetch(`${API_BASE}/prepare-update`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items }),
  });
  if (!res.ok) {
    try {
      const err = await res.json();
      throw new Error(err.message || "Failed to prepare update data");
    } catch {
      throw new Error("Failed to prepare update data");
    }
  }
  return res.json();
}

export async function triggerUpdate() {
  const res = await fetch(`${API_BASE}/trigger-update`, {
    method: "POST",
  });
  const data = await res.json();
  if ((data as { status?: string; message?: string }).status === "error") {
    throw new Error((data as { message?: string }).message || "Failed to trigger update");
  }
  return data;
}

export const fetchLogs = async (): Promise<{ logs: string }> => {
  const res = await fetch(`${API_BASE}/logs`);
  if (!res.ok) {
    throw new Error("Failed to fetch logs");
  }
  return res.json();
};

export const fetchTaskStatus = async (): Promise<{ running: boolean; task_name: string | null; message: string; progress: number; last_updated?: string }> => {
  const path = "/task-status";
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  return parseJsonResponse(res, path, "Failed to fetch task status");
};

export async function stopTask() {
  const res = await fetch(`${API_BASE}/stop-task`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to stop task");
  const data = await res.json();
  if ((data as { status?: string; message?: string }).status === "error") {
    throw new Error((data as { message?: string }).message || "Failed to stop task");
  }
  return data;
}

export async function updateMerchant(id: string, merchant: string) {
  const res = await fetch(`${API_BASE}/goods/${id}/merchant`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ merchant }),
  });
  if (!res.ok) throw new Error("Failed to update merchant");
  return res.json();
}

export async function updateAlipayCode(id: string, code: string) {
  const res = await fetch(`${API_BASE}/goods/${id}/field`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ field: "支付宝编码", value: code }),
  });
  if (!res.ok) throw new Error("Failed to update alipay code");
  return res.json();
}

export async function deleteGoods(id: string) {
  const res = await fetch(`${API_BASE}/goods/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete goods");
  return res.json();
}

export async function fetchConfig(): Promise<Record<string, string>> {
  const res = await fetch(`${API_BASE}/config`);
  if (!res.ok) return {};
  return res.json();
}

export async function updateConfig(key: string, value: string) {
  const res = await fetch(`${API_BASE}/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, value }),
  });
  if (!res.ok) throw new Error("Failed to update config");
  return res.json();
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
  const res = await fetch(`${API_BASE}/automation/alipay/update`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids, phone }),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.message || "Failed to start automation");
  }
  return res.json();
}

export async function getAutomationStatus(): Promise<AutomationStatus> {
  const res = await fetch(`${API_BASE}/automation/status`, { cache: 'no-store' });
  if (!res.ok) throw new Error("Failed to get status");
  return res.json();
}

export async function submitCaptcha(code: string) {
  const res = await fetch(`${API_BASE}/automation/captcha`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });
  if (!res.ok) throw new Error("Failed to submit captcha");
  return res.json();
}
