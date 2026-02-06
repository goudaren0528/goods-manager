
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

export const API_BASE = "http://127.0.0.1:8000";
export const EXPORT_URL = `${API_BASE}/export-excel`;

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

  const res = await fetch(`${API_BASE}/goods?${params.toString()}`, { cache: 'no-store' });
  if (!res.ok) throw new Error("Failed to fetch goods");
  return res.json();
}

export const runScrape = async (): Promise<Record<string, unknown>> => {
  const res = await fetch(`${API_BASE}/run-scrape`, {
    method: "POST",
  });
  if (!res.ok) {
    throw new Error("Failed to run scrape");
  }
  return res.json();
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
  return res.json();
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
  return res.json();
}

export const fetchLogs = async (): Promise<{ logs: string }> => {
  const res = await fetch(`${API_BASE}/logs`);
  if (!res.ok) {
    throw new Error("Failed to fetch logs");
  }
  return res.json();
};

export const fetchTaskStatus = async (): Promise<{ running: boolean; task_name: string | null; message: string; progress: number; last_updated?: string }> => {
  const res = await fetch(`${API_BASE}/task-status`, { cache: 'no-store' });
  if (!res.ok) {
    throw new Error("Failed to fetch task status");
  }
  return res.json();
};

export async function stopTask() {
  const res = await fetch(`${API_BASE}/stop-task`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to stop task");
  return res.json();
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
