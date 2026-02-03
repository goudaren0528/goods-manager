"use client";

import { useEffect, useState } from "react";
import { Goods, fetchGoods, syncFromExcel, prepareUpdate, triggerUpdate, fetchLogs, API_BASE, EXPORT_URL } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { toast } from "sonner";

export default function Home() {
  const [goods, setGoods] = useState<Goods[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState<Partial<Goods>>({});
  const [logs, setLogs] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadLogs, 2000);
    return () => clearInterval(interval);
  }, []);

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
    try {
      await syncFromExcel();
      await loadData();
      toast.success("数据同步成功");
    } catch (e) {
      toast.error("同步失败");
    }
    setLoading(false);
  };

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedIds(new Set(goods.map((g) => g.ID)));
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
    // 这里简单处理：如果是批量编辑，只允许编辑公共字段，或者如果是单选，编辑所有字段
    // 为了演示，我们假设只编辑第一个选中的商品作为模板，或者这一步是“批量设置”
    // 实际业务中可能需要更复杂的逻辑。
    // 这里我们简化为：如果选了多个，就弹出一个空表单，填了哪个字段就更新哪个字段到所有选中项。
    setEditForm({});
    setIsEditing(true);
  };

  const saveEdit = async () => {
    // 构建要更新的数据列表
    const updates = goods
      .filter((g) => selectedIds.has(g.ID))
      .map((g) => ({
        ...g,
        ...editForm, // 覆盖修改的字段
      }));

    try {
      await prepareUpdate(updates);
      toast.success(`已准备 ${updates.length} 条更新数据`);
      setIsEditing(false);
      
      // 询问是否立即执行
      if (confirm("数据已准备就绪，是否立即运行自动化脚本更新到支付宝？")) {
          await triggerUpdate();
          toast.info("自动化脚本已启动，请查看日志");
      }
    } catch (e) {
      toast.error("保存失败");
    }
  };

  // 获取所有可能的列名（除了ID）
  const columns = goods.length > 0 ? Object.keys(goods[0]).filter(k => k !== "ID") : [];

  return (
    <div className="container mx-auto p-4 space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">支付宝商品管理</h1>
        <div className="space-x-2">
          <Button variant="outline" onClick={() => window.open(EXPORT_URL, "_blank")}>
            导出 Excel
          </Button>
          <Button variant="outline" onClick={handleSync} disabled={loading}>
            从 Excel 同步
          </Button>
          <Button onClick={startEdit} disabled={selectedIds.size === 0}>
            批量编辑 ({selectedIds.size})
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* 商品表格区域 */}
        <div className="md:col-span-2 border rounded-md overflow-hidden">
            <div className="max-h-[600px] overflow-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[50px]">
                  <Checkbox
                    checked={goods.length > 0 && selectedIds.size === goods.length}
                    onCheckedChange={(c) => handleSelectAll(!!c)}
                  />
                </TableHead>
                <TableHead>ID</TableHead>
                <TableHead>商品名称</TableHead>
                <TableHead>SKU</TableHead>
                <TableHead>库存</TableHead>
                {/* 更多列可以在这里动态渲染，但为了性能和宽度，暂时只显示关键列 */}
              </TableRow>
            </TableHeader>
            <TableBody>
              {goods.map((g) => (
                <TableRow key={g.ID}>
                  <TableCell>
                    <Checkbox
                      checked={selectedIds.has(g.ID)}
                      onCheckedChange={(c) => handleSelectOne(g.ID, !!c)}
                    />
                  </TableCell>
                  <TableCell>{g.ID}</TableCell>
                  <TableCell className="max-w-[200px] truncate" title={g.商品名称}>{g.商品名称}</TableCell>
                  <TableCell>{g.SKU}</TableCell>
                  <TableCell>{g.库存}</TableCell>
                </TableRow>
              ))}
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

      {/* 编辑弹窗 */}
      <Dialog open={isEditing} onOpenChange={setIsEditing}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>批量编辑 {selectedIds.size} 个商品</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <p className="text-sm text-gray-500">
              提示：只填写需要修改的字段，留空则保持原值。
            </p>
            <div className="grid grid-cols-2 gap-4">
                {/* 动态渲染常用字段表单 */}
                {["商品名称", "短标题", "库存", "SKU", "1天租金", "30天租金", "押金"].map(field => (
                    <div key={field} className="grid gap-2">
                        <Label>{field}</Label>
                        <Input 
                            placeholder={`保持原值`}
                            onChange={(e) => setEditForm({...editForm, [field]: e.target.value})}
                        />
                    </div>
                ))}
            </div>
            {/* 可以添加一个 Textarea 来输入 JSON 格式的高级编辑 */}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsEditing(false)}>取消</Button>
            <Button onClick={saveEdit}>保存并准备更新</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
