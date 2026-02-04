"use client";

import { useEffect, useState } from "react";
import { RentCurve, fetchRentCurves, saveRentCurve, deleteRentCurve } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { Pencil, Trash2, Plus, Loader2 } from "lucide-react";
import { RENT_DAYS } from "@/lib/utils";

export default function CurvesPage() {
  const [curves, setCurves] = useState<RentCurve[]>([]);
  const [loading, setLoading] = useState(false);
  const [editDialog, setEditDialog] = useState<{
    open: boolean;
    curve: RentCurve | null;
  }>({ open: false, curve: null });

  const loadCurves = async () => {
    setLoading(true);
    try {
      const data = await fetchRentCurves();
      setCurves(data);
    } catch (e) {
      toast.error("加载曲线失败");
    }
    setLoading(false);
  };

  useEffect(() => {
    loadCurves();
  }, []);

  const handleDelete = async (curve: RentCurve) => {
    if (!confirm(`确定要删除曲线 "${curve.name}" 吗？`)) return;
    try {
      await deleteRentCurve(curve.id || curve.name);
      toast.success("删除成功");
      loadCurves();
    } catch (e) {
      toast.error("删除失败: " + String(e));
    }
  };

  const openEdit = (curve: RentCurve) => {
    // Deep copy to avoid mutating state directly
    setEditDialog({
      open: true,
      curve: JSON.parse(JSON.stringify(curve))
    });
  };

  const handleSave = async () => {
    const { curve } = editDialog;
    if (!curve) return;
    if (!curve.name) {
      toast.error("请输入名称");
      return;
    }

    try {
      await saveRentCurve(curve);
      toast.success("保存成功");
      setEditDialog({ open: false, curve: null });
      loadCurves();
    } catch (e) {
      toast.error("保存失败: " + String(e));
    }
  };

  const handleMultiplierChange = (day: string, val: string) => {
    if (!editDialog.curve) return;
    const num = parseFloat(val);
    if (isNaN(num)) return;
    
    setEditDialog(prev => ({
      ...prev,
      curve: prev.curve ? {
        ...prev.curve,
        multipliers: {
          ...prev.curve.multipliers,
          [day]: num
        }
      } : null
    }));
  };

  return (
    <div className="w-full max-w-5xl mx-auto p-4 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">租金曲线配置</h1>
        <Button onClick={loadCurves} variant="outline" size="icon">
           <Loader2 className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      <Card>
        <CardHeader className="py-3 px-4 bg-muted/20 border-b">
          <CardTitle className="text-sm font-medium">已保存的曲线</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[100px]">ID</TableHead>
                <TableHead className="w-[200px]">名称</TableHead>
                <TableHead className="w-[200px]">源商品 (SKU)</TableHead>
                <TableHead className="w-[180px]">创建时间</TableHead>
                <TableHead>曲线预览 (部分)</TableHead>
                <TableHead className="w-[100px] text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {curves.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                    暂无配置，请先在商品列表提取曲线
                  </TableCell>
                </TableRow>
              ) : (
                curves.map((curve, idx) => (
                  <TableRow key={curve.id || idx}>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {curve.id ? curve.id.substring(0, 8) + "..." : "-"}
                    </TableCell>
                    <TableCell className="font-medium">{curve.name}</TableCell>
                    <TableCell className="text-xs">
                      <div className="flex flex-col gap-0.5">
                        <span className="font-medium">{curve.source_name || "未知商品"}</span>
                        <span className="text-[10px] text-muted-foreground font-mono">{curve.source_sku || "-"}</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">{curve.created_at || "-"}</TableCell>
                    <TableCell className="text-xs text-muted-foreground truncate max-w-[200px]">
                      {Object.entries(curve.multipliers || {})
                        .slice(0, 5)
                        .map(([d, m]) => `${d}天:x${m}`)
                        .join(", ")}
                      ...
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => openEdit(curve)}>
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button variant="ghost" size="icon" className="h-8 w-8 text-red-500 hover:text-red-600 hover:bg-red-50" onClick={() => handleDelete(curve)}>
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Dialog open={editDialog.open} onOpenChange={o => setEditDialog(prev => ({ ...prev, open: o }))}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>编辑租金曲线</DialogTitle>
          </DialogHeader>
          {editDialog.curve && (
            <div className="grid gap-6 py-4">
              <div className="grid grid-cols-4 items-center gap-4">
                <Label className="text-right">曲线名称</Label>
                <Input 
                  value={editDialog.curve.name} 
                  onChange={e => setEditDialog(prev => prev.curve ? ({ ...prev.curve, name: e.target.value }) : prev)}
                  className="col-span-3"
                />
              </div>
              
              <div className="grid gap-4">
                <Label>倍数配置 (相对于1天租金)</Label>
                <div className="grid grid-cols-4 gap-4 border rounded-md p-4 bg-muted/10">
                  {RENT_DAYS.map(day => (
                    <div key={day} className="flex flex-col gap-1">
                      <Label className="text-xs text-muted-foreground text-center">{day}天</Label>
                      <div className="relative">
                        <span className="absolute left-2 top-1.5 text-xs text-muted-foreground">x</span>
                        <Input 
                          type="number" 
                          step="0.0001"
                          className="pl-5 text-center h-8 text-sm"
                          value={editDialog.curve.multipliers[String(day)] || ""}
                          onChange={e => handleMultiplierChange(String(day), e.target.value)}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button onClick={handleSave}>保存修改</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
