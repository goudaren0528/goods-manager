"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Goods, fetchGoods, prepareUpdate, triggerUpdate, fetchLogs } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { toast } from "sonner";
import { ArrowLeft, Save, Play } from "lucide-react";

export default function Workbench() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [items, setItems] = useState<Goods[]>([]);
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState("");
  const [logInterval, setLogInterval] = useState<NodeJS.Timeout | null>(null);

  // 初始化加载选中数据
  useEffect(() => {
    const ids = searchParams.get("ids")?.split(",") || [];
    if (ids.length === 0) {
      toast.error("未选择任何商品");
      router.push("/");
      return;
    }

    const loadSelectedGoods = async () => {
      try {
        const allGoods = await fetchGoods();
        // 这里的逻辑需要注意：如果 ID 重复（不同 SKU），需要通过某种方式区分
        // 简单起见，我们目前认为 ID 是行的唯一标识（虽然实际上可能不是）
        // 理想情况后端应返回 unique_key。这里我们暂时先按 ID 过滤出所有相关行
        const selected = allGoods.filter(g => ids.includes(g.ID));
        setItems(selected);
      } catch (e) {
        toast.error("加载商品数据失败");
      }
    };
    loadSelectedGoods();
  }, [searchParams, router]);

  // 日志轮询
  useEffect(() => {
    return () => {
      if (logInterval) clearInterval(logInterval);
    };
  }, [logInterval]);

  const loadLogs = async () => {
    try {
      const res = await fetchLogs();
      setLogs(res.logs);
    } catch (e) {}
  };

  const handleFieldChange = (index: number, field: keyof Goods, value: string) => {
    const newItems = [...items];
    newItems[index] = { ...newItems[index], [field]: value };
    setItems(newItems);
  };

  const handleSaveAndRun = async () => {
    setLoading(true);
    setLogs("正在启动更新任务...");
    try {
      // 1. 准备数据
      await prepareUpdate(items);
      toast.success("数据已准备就绪，开始执行自动化更新...");
      
      // 2. 触发脚本
      await triggerUpdate();
      
      // 3. 开始轮询日志
      const interval = setInterval(loadLogs, 1000);
      setLogInterval(interval);
      
    } catch (e) {
      toast.error("启动更新失败: " + String(e));
      setLoading(false);
    }
  };

  // 动态获取所有列（排除 ID 和 SKU 这种固定列，放在前面）
  const fixedCols = ["ID", "SKU", "商品名称"];
  const dynamicCols = items.length > 0 
    ? Object.keys(items[0]).filter(k => !fixedCols.includes(k) && k !== "_key") 
    : [];
  
  const allCols = [...fixedCols, ...dynamicCols];

  return (
    <div className="container mx-auto p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" onClick={() => router.push("/")}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <h1 className="text-2xl font-bold">商品修改工作台</h1>
        </div>
        <div className="flex gap-2">
           <Button onClick={handleSaveAndRun} disabled={loading} className="bg-green-600 hover:bg-green-700">
            <Play className="mr-2 h-4 w-4" />
            提交并执行更新
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 border rounded-md bg-white dark:bg-zinc-950 overflow-hidden flex flex-col h-[700px]">
          <div className="p-2 bg-muted/50 border-b text-xs text-muted-foreground">
            共 {items.length} 条记录。请直接在表格中修改数据，完成后点击右上角“提交并执行更新”。
          </div>
          <ScrollArea className="flex-1">
            <div className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    {allCols.map(col => (
                      <TableHead key={col} className="min-w-[150px]">{col}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((item, idx) => (
                    <TableRow key={idx}>
                      {allCols.map(col => (
                        <TableCell key={col} className="p-1">
                          {col === "ID" ? (
                            <span className="pl-3 text-muted-foreground">{String(item[col as keyof Goods] ?? "")}</span>
                          ) : (
                            <Input 
                              value={String(item[col as keyof Goods] || "")}
                              onChange={(e) => handleFieldChange(idx, col as keyof Goods, e.target.value)}
                              className="h-8 border-transparent hover:border-input focus:border-ring bg-transparent"
                            />
                          )}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </ScrollArea>
        </div>

        <Card className="h-[700px] flex flex-col">
          <CardHeader>
            <CardTitle>执行日志</CardTitle>
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
