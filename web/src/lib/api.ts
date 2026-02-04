
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

export async function fetchGoods(page = 1, limit = 50, all_data = false, merchant?: string): Promise<FetchGoodsResponse> {
  const params: Record<string, string> = {
    page: String(page),
    limit: String(limit),
    all_data: String(all_data),
  };
  if (merchant) {
    params.merchant = merchant;
  }
  const query = new URLSearchParams(params);
  const res = await fetch(`${API_BASE}/goods?${query.toString()}`, { cache: 'no-store' });
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

export const prepareUpdate = async (items: Partial<GoodsItem>[]): Promise<Record<string, unknown>> => {
  const res = await fetch(`${API_BASE}/prepare-update`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items }),
  });
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

export async function updateMerchant(id: string, merchant: string) {
  const res = await fetch(`${API_BASE}/goods/${id}/merchant`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ merchant }),
  });
  if (!res.ok) throw new Error("Failed to update merchant");
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
