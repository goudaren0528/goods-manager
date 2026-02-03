"use client";

import { useEffect, useState } from "react";
import { Goods, fetchGoods, runScrape, fetchLogs, API_BASE, EXPORT_URL } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { toast } from "sonner";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

export default function Home() {
  const router = useRouter();
  const [goods, setGoods] = useState<Goods[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [logs, setLogs] = useState("");
  const [loading, setLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");

  useEffect(() => {
    loadData();
    // 只有在加载中才轮询日志
    if (loading) {
        const interval = setInterval(loadLogs, 2000);
        return () => clearInterval(interval);
    }
  }, [loading]);

  const loadData = async () => {
    try {
      const data = await fetchGoods();
      setGoods(data);
    } catch (e) {
      toast.error("加载数据失败");
    }
  };

  const loadLogs = async () => {
    try {
      const res = await fetchLogs();
      setLogs(res.logs);
    } catch (e) {}
  };

  const handleSync = async () => {
    setLoading(true);
    setLogs("正在启动抓取任务...");
    try {
      await runScrape();
      await loadData();
      toast.success("数据更新成功");
    } catch (e) {
      toast.error("更新失败: " + String(e));
    }
    setLoading(false);
  };

  const filteredGoods = goods.filter(g => {
    if (!searchTerm) return true;
    const lower = searchTerm.toLowerCase();
    return (
        (g.ID && g.ID.toLowerCase().includes(lower)) ||
        (g.商品名称 && g.商品名称.toLowerCase().includes(lower)) ||
        (g.SKU && g.SKU.toLowerCase().includes(lower))
    );
  });

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      // 选中过滤后的所有商品
      setSelectedIds(new Set(filteredGoods.map((g) => g.ID)));
    } else {
      setSelectedIds(new Set());
    }
  };

  const handleSelectOne = (id: string, checked: boolean) => {
    const newSet = new Set(selectedIds);
    if (checked) {
      newSet.add(id);
    } else {
      newSet.delete(id);
    }
    setSelectedIds(newSet);
  };

  const startEdit = () => {
    if (selectedIds.size === 0) {
      toast.warning("请先选择商品");
      return;
    }
    // 跳转到工作台
    const ids = Array.from(selectedIds).join(",");
    router.push(`/workbench?ids=${ids}`);
  };

  return (
    <div className="container mx-auto p-4 space-y-4">
      <div className="flex flex-col gap-4 md:flex-row md:justify-between md:items-center">
        <h1 className="text-2xl font-bold">支付宝商品管理</h1>
        <div className="flex flex-col gap-2 sm:flex-row">
            <Input 
                placeholder="搜索 ID / 名称 / SKU..." 
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full sm:w-[250px]"
            />
          <Button variant="outline" onClick={() => window.open(EXPORT_URL, "_blank")}>
            导出 Excel
          </Button>
          <Button variant="outline" onClick={handleSync} disabled={loading}>
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            更新商品数据 (抓取)
          </Button>
          <Button onClick={startEdit} disabled={selectedIds.size === 0}>
            进入修改工作台 ({selectedIds.size})
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* 商品表格区域 */}
        <div className="lg:col-span-2 border rounded-md overflow-hidden bg-white dark:bg-zinc-950">
            <div className="max-h-[600px] overflow-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[50px]">
                  <Checkbox
                    checked={filteredGoods.length > 0 && selectedIds.size === filteredGoods.length}
                    onCheckedChange={(c) => handleSelectAll(!!c)}
                  />
                </TableHead>
                <TableHead>ID</TableHead>
                <TableHead>SKU</TableHead>
                <TableHead>商品名称</TableHead>
                <TableHead>库存</TableHead>
                {/* 更多列可以在这里动态渲染，但为了性能和宽度，暂时只显示关键列 */}
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredGoods.length === 0 ? (
                  <TableRow>
                      <TableCell colSpan={5} className="text-center h-24">暂无数据</TableCell>
                  </TableRow>
              ) : (
                filteredGoods.map((g, idx) => (
                <TableRow key={`${g.ID}-${g.SKU || idx}`}>
                  <TableCell>
                    <Checkbox
                      checked={selectedIds.has(g.ID)}
                      onCheckedChange={(c) => handleSelectOne(g.ID, !!c)}
                    />
                  </TableCell>
                  <TableCell>{g.ID}</TableCell>
                  <TableCell className="max-w-[150px] truncate" title={g.SKU}>{g.SKU}</TableCell>
                  <TableCell className="max-w-[200px] truncate" title={g.商品名称}>{g.商品名称}</TableCell>
                  <TableCell>{g.库存}</TableCell>
                </TableRow>
              )))}
            </TableBody>
          </Table>
          </div>
        </div>

        {/* 日志区域 */}
        <Card className="h-[600px] flex flex-col">
          <CardHeader>
            <CardTitle>运行日志</CardTitle>
          </CardHeader>
          <CardContent className="flex-1 p-0 overflow-hidden">
            <ScrollArea className="h-full p-4 bg-black text-white font-mono text-xs">
              <pre className="whitespace-pre-wrap">{logs || "等待任务启动..."}</pre>
            </ScrollArea>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
