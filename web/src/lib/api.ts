
export interface Goods {
  ID: string;
  商品名称: string;
  短标题?: string;
  SKU?: string;
  库存?: number;
  [key: string]: any; // 允许动态字段
}

export const API_BASE = "http://127.0.0.1:8000";
export const EXPORT_URL = `${API_BASE}/export-excel`;

export async function fetchGoods(): Promise<Goods[]> {
  const res = await fetch(`${API_BASE}/goods`);
  if (!res.ok) throw new Error("Failed to fetch goods");
  return res.json();
}

export const runScrape = async (): Promise<any> => {
  const res = await fetch(`${API_BASE}/run-scrape`, {
    method: "POST",
  });
  if (!res.ok) {
    throw new Error("Failed to run scrape");
  }
  return res.json();
};

export const prepareUpdate = async (items: Partial<Goods>[]): Promise<any> => {
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

export async function fetchLogs() {
  const res = await fetch(`${API_BASE}/logs`);
  return res.json();
}
