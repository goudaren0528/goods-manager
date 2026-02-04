"use client";

import { useEffect, useState, Suspense, useMemo, Fragment } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { GoodsItem, fetchGoods, prepareUpdate, triggerUpdate, fetchLogs, RentCurve, fetchRentCurves } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { toast } from "sonner";
import { ArrowLeft, Save, Play, Trash2, Copy, Settings2, Plus, Info, Calculator, Wand2 } from "lucide-react";
import { getRentInfo, RENT_DAYS } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

function WorkbenchContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [items, setItems] = useState<GoodsItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState("");
  const [logInterval, setLogInterval] = useState<NodeJS.Timeout | null>(null);

  // 批量添加规格状态
  const [isSpecDialogOpen, setIsSpecDialogOpen] = useState(false);
  const [targetGroupId, setTargetGroupId] = useState<string | null>(null); // null means all? No, user wants per card.
  const [specName, setSpecName] = useState("");
  const [specValue, setSpecValue] = useState("");

  // 批量差价操作状态
  const [diffDialog, setDiffDialog] = useState<{
    open: boolean;
    targetIndex: number; // Global index in items
    groupId: string;
    groupIndex: number; // Index within the group
  }>({ open: false, targetIndex: -1, groupId: "", groupIndex: -1 });
  const [diffValue, setDiffValue] = useState<string>("0");
  const [diffRefType, setDiffRefType] = useState<"prev" | "next">("prev");
  const [diffSelectedCols, setDiffSelectedCols] = useState<string[]>([]);

  // 应用曲线状态
  const [applyCurveDialog, setApplyCurveDialog] = useState<{
    open: boolean;
    targetIndex: number;
    curves: RentCurve[];
    selectedCurve: string;
  }>({ open: false, targetIndex: -1, curves: [], selectedCurve: "" });

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
        // Fetch all data for editing to ensure we find the IDs
        const response = await fetchGoods(1, 10000, true);
        const allGroups = response.data;
        const selectedGroups = allGroups.filter(g => ids.includes(g.ID));
        const allSkus = selectedGroups.flatMap(g => g.skus);
        setItems(allSkus);
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

  const rentCols = RENT_DAYS.map(d => `${d}天租金`);
  const priceCols = ["市场价", "押金", "购买价", "采购价"];

  // Group items by ID
  const groupedItems = useMemo(() => {
    const groups = new Map<string, { 
      items: { item: GoodsItem, index: number }[], 
      skuKeys: string[], 
      hasBaseSku: boolean 
    }>();

    items.forEach((item, index) => {
      if (!groups.has(item.ID)) {
        groups.set(item.ID, { items: [], skuKeys: [], hasBaseSku: false });
      }
      groups.get(item.ID)!.items.push({ item, index });
    });

    // Calculate columns per group
    groups.forEach(group => {
      const keys = new Set<string>();
      let hasBase = false;
      group.items.forEach(({ item }) => {
        if (!item.SKU) return;
        const parts = item.SKU.split("|");
        parts.forEach(p => {
          const match = p.match(/[:：]/);
          if (match) {
            keys.add(p.substring(0, match.index));
          } else if (p.trim()) {
            hasBase = true;
          }
        });
      });
      group.skuKeys = Array.from(keys).sort();
      group.hasBaseSku = hasBase;
    });

    return Array.from(groups.entries());
  }, [items]);

  const handleFieldChange = (index: number, field: string, value: string) => {
    const newItems = [...items];
    newItems[index] = { ...newItems[index], [field]: value };
    setItems(newItems);
  };

  const handleDeleteRow = (index: number) => {
    const newItems = [...items];
    newItems.splice(index, 1);
    setItems(newItems);
  };

  const handleDuplicateRow = (index: number) => {
    const newItems = [...items];
    const copy = { ...newItems[index] };
    newItems.splice(index + 1, 0, copy);
    setItems(newItems);
  };

  const openSpecDialog = (groupId: string) => {
    setTargetGroupId(groupId);
    setIsSpecDialogOpen(true);
  };

  const handleAddSpec = () => {
    if (!specName) {
      toast.error("请输入规格名");
      return;
    }
    if (!specValue) {
      toast.error("请输入规格值");
      return;
    }

    // Split spec values by comma (English or Chinese)
    const values = specValue.split(/[,，]/).map(v => v.trim()).filter(Boolean);
    
    if (values.length === 0) {
      toast.error("请输入有效的规格值");
      return;
    }

    const newItems: GoodsItem[] = [];

    items.forEach(item => {
      // If targetGroupId is set, only apply to items with that ID
      if (targetGroupId && item.ID !== targetGroupId) {
        newItems.push(item);
        return;
      }

      // For each matching item, create N copies (one for each new spec value)
      values.forEach(val => {
        const current = item.SKU || "";
        // If current is empty, just use the new spec. Otherwise append.
        const newSku = current ? `${current}|${specName}:${val}` : `${specName}:${val}`;
        
        newItems.push({
          ...item,
          SKU: newSku
        });
      });
    });

    setItems(newItems);
    setIsSpecDialogOpen(false);
    setSpecName("");
    setSpecValue("");
    toast.success(`已为商品 ${targetGroupId || '所有'} 批量添加规格`);
  };

  const openDiffDialog = (globalIndex: number, groupId: string, groupIndex: number) => {
    const groupData = groupedItems.find(g => g[0] === groupId)?.[1];
    if (!groupData) return;
    
    // Determine available neighbors
    const hasPrev = groupIndex > 0;
    const hasNext = groupIndex < groupData.items.length - 1;
    
    let defaultRef: "prev" | "next" = "prev";
    if (hasPrev) defaultRef = "prev";
    else if (hasNext) defaultRef = "next";
    
    setDiffDialog({
        open: true,
        targetIndex: globalIndex,
        groupId,
        groupIndex
    });
    setDiffRefType(defaultRef);
    setDiffSelectedCols([...rentCols]); // Default select all rent cols
    setDiffValue("0");
  };

  const handleApplyDiff = () => {
    const { targetIndex, groupId, groupIndex } = diffDialog;
    if (targetIndex === -1) return;

    const groupData = groupedItems.find(g => g[0] === groupId)?.[1];
    if (!groupData) {
        toast.error("找不到商品组数据");
        return;
    }

    let refItem: GoodsItem | undefined;
    if (diffRefType === "prev") {
        if (groupIndex > 0) {
            refItem = groupData.items[groupIndex - 1].item;
        }
    } else {
        if (groupIndex < groupData.items.length - 1) {
            refItem = groupData.items[groupIndex + 1].item;
        }
    }

    if (!refItem) {
        toast.error(diffRefType === "prev" ? "没有上一行数据" : "没有下一行数据");
        return;
    }

    const valToAdd = parseFloat(diffValue);
    if (isNaN(valToAdd)) {
        toast.error("请输入有效的差价数值");
        return;
    }

    const newItems = [...items];
    const targetItem = { ...newItems[targetIndex] };

    let updatedCount = 0;
    diffSelectedCols.forEach(col => {
        const refVal = parseFloat(String(refItem![col]));
        if (!isNaN(refVal)) {
            targetItem[col] = (refVal + valToAdd).toString();
            updatedCount++;
        }
    });

    newItems[targetIndex] = targetItem;
    setItems(newItems);
    setDiffDialog(prev => ({ ...prev, open: false }));
    toast.success(`已更新 ${updatedCount} 个价格列`);
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

  const openApplyCurveDialog = async (index: number) => {
    try {
        const curves = await fetchRentCurves();
        if (curves.length === 0) {
            toast.error("暂无保存的租金曲线，请先在商品列表提取曲线");
            return;
        }
        setApplyCurveDialog({
            open: true,
            targetIndex: index,
            curves,
            selectedCurve: curves[0].name
        });
    } catch (e) {
        toast.error("加载曲线失败");
    }
  };

  const handleApplyCurve = () => {
    const { targetIndex, selectedCurve, curves } = applyCurveDialog;
    if (targetIndex === -1 || !selectedCurve) return;

    const curve = curves.find(c => c.name === selectedCurve);
    if (!curve) return;

    const newItems = [...items];
    const item = { ...newItems[targetIndex] };
    const baseRent = parseFloat(String(item["1天租金"]));

    if (isNaN(baseRent) || baseRent <= 0) {
        toast.error("该商品没有有效的1天租金，无法应用曲线");
        return;
    }

    let updatedCount = 0;
    Object.entries(curve.multipliers).forEach(([day, multiplier]) => {
        const key = `${day}天租金`;
        const newRent = Math.round(baseRent * multiplier);
        // Only update if the key is a valid rent column (though all should be if defined in RENT_DAYS)
        item[key] = newRent.toString();
        updatedCount++;
    });

    newItems[targetIndex] = item;
    setItems(newItems);
    setApplyCurveDialog(prev => ({ ...prev, open: false }));
    toast.success(`已根据曲线 "${selectedCurve}" 更新租金`);
  };

  const handleSkuPartChange = (index: number, key: string, val: string) => {
    const newItems = [...items];
    const item = newItems[index];
    const currentSku = item.SKU || "";
    
    const parts = currentSku.split("|").filter(Boolean);
    const map = new Map<string, string>();
    const others: string[] = []; 
    
    parts.forEach(p => {
        const match = p.match(/[:：]/);
        if (match) {
            const k = p.substring(0, match.index);
            const v = p.substring(match.index! + 1);
            map.set(k, v);
        } else {
            others.push(p);
        }
    });
    
    if (val) {
        map.set(key, val);
    } else {
        map.delete(key);
    }
    
    const newParts = [...others];
    
    // Sort keys for stability
    const sortedKeys = Array.from(map.keys()).sort(); 
    sortedKeys.forEach(k => {
        newParts.push(`${k}:${map.get(k)}`);
    });
    
    newItems[index] = { ...item, SKU: newParts.join("|") };
    setItems(newItems);
  };

  const handleBaseSkuChange = (index: number, val: string) => {
      const newItems = [...items];
      const item = newItems[index];
      const currentSku = item.SKU || "";
      
      const parts = currentSku.split("|").filter(Boolean);
      const kvs: string[] = [];
      
      parts.forEach(p => {
          if (p.match(/[:：]/)) {
              kvs.push(p);
          }
      });
      
      const newSku = val ? (kvs.length > 0 ? `${val}|${kvs.join("|")}` : val) : kvs.join("|");
      
      newItems[index] = { ...item, SKU: newSku };
      setItems(newItems);
  };
  
  // 渲染编辑表格
  return (
    <div className="w-full px-4 space-y-4 h-screen flex flex-col bg-background">
      <div className="flex items-center justify-between shrink-0 py-4 border-b">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" onClick={() => router.push("/")}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <h1 className="text-xl font-bold">批量修改商品</h1>
        </div>
        <div className="flex gap-2">
          <Button onClick={handleSaveAndRun} disabled={loading} className="gap-2">
            {loading ? <Play className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {loading ? "执行中..." : "保存并执行自动化更新"}
          </Button>
        </div>
      </div>

      <Dialog open={isSpecDialogOpen} onOpenChange={setIsSpecDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>为商品 {targetGroupId} 批量增加规格</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-4 items-center gap-4">
              <Label className="text-right">规格名</Label>
              <Input 
                value={specName} 
                onChange={e => setSpecName(e.target.value)} 
                placeholder="如：材质" 
                className="col-span-3"
              />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label className="text-right">规格值</Label>
              <Input 
                value={specValue} 
                onChange={e => setSpecValue(e.target.value)} 
                placeholder="如：纯棉, 涤纶 (多值用逗号分隔)" 
                className="col-span-3"
              />
            </div>
            <p className="text-xs text-muted-foreground">
              提示：支持输入多个规格值（用逗号分隔），将为每个值生成一行新数据。
              <br />
              例如输入 "红色, 蓝色"，原来的每一行都会分裂成两行。
            </p>
          </div>
          <DialogFooter>
            <Button onClick={handleAddSpec}>确定添加</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={diffDialog.open} onOpenChange={o => setDiffDialog(prev => ({ ...prev, open: o }))}>
        <DialogContent className="max-w-2xl">
            <DialogHeader>
                <DialogTitle>批量设置租金差价</DialogTitle>
            </DialogHeader>
            <div className="grid gap-6 py-4">
                <div className="grid grid-cols-4 items-center gap-4">
                    <Label className="text-right">参照行</Label>
                    <RadioGroup 
                        value={diffRefType} 
                        onValueChange={(v: "prev" | "next") => setDiffRefType(v)}
                        className="flex gap-4 col-span-3"
                    >
                        <div className="flex items-center space-x-2">
                            <RadioGroupItem value="prev" id="r-prev" />
                            <Label htmlFor="r-prev">上一行</Label>
                        </div>
                        <div className="flex items-center space-x-2">
                            <RadioGroupItem value="next" id="r-next" />
                            <Label htmlFor="r-next">下一行</Label>
                        </div>
                    </RadioGroup>
                </div>
                <div className="grid grid-cols-4 items-center gap-4">
                    <Label className="text-right">差价 (增减)</Label>
                    <Input 
                        type="number"
                        value={diffValue}
                        onChange={e => setDiffValue(e.target.value)}
                        placeholder="0"
                        className="col-span-3"
                    />
                </div>
                <div className="grid grid-cols-4 gap-4">
                    <Label className="text-right pt-2">应用列</Label>
                    <div className="col-span-3 grid grid-cols-3 gap-2">
                        {rentCols.map(col => (
                            <div key={col} className="flex items-center space-x-2">
                                <Checkbox 
                                    id={`col-${col}`} 
                                    checked={diffSelectedCols.includes(col)}
                                    onCheckedChange={(checked) => {
                                        if (checked) {
                                            setDiffSelectedCols(prev => [...prev, col]);
                                        } else {
                                            setDiffSelectedCols(prev => prev.filter(c => c !== col));
                                        }
                                    }}
                                />
                                <Label htmlFor={`col-${col}`} className="text-sm cursor-pointer">{col}</Label>
                            </div>
                        ))}
                    </div>
                </div>
                <div className="grid grid-cols-4 gap-4">
                    <div className="col-start-2 col-span-3 flex gap-2">
                        <Button variant="outline" size="sm" onClick={() => setDiffSelectedCols([...rentCols])}>全选</Button>
                        <Button variant="outline" size="sm" onClick={() => setDiffSelectedCols([])}>清空</Button>
                    </div>
                </div>
            </div>
            <DialogFooter>
                <Button onClick={handleApplyDiff}>确认应用</Button>
            </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={applyCurveDialog.open} onOpenChange={o => setApplyCurveDialog(prev => ({ ...prev, open: o }))}>
        <DialogContent className="max-w-md">
            <DialogHeader>
                <DialogTitle>应用租金曲线</DialogTitle>
            </DialogHeader>
            <div className="grid gap-6 py-4">
                <div className="flex flex-col gap-2">
                    <Label>选择曲线</Label>
                    <Select
                        value={applyCurveDialog.selectedCurve}
                        onValueChange={(val) => setApplyCurveDialog(prev => ({ ...prev, selectedCurve: val }))}
                    >
                        <SelectTrigger>
                            <SelectValue placeholder="选择曲线" />
                        </SelectTrigger>
                        <SelectContent>
                            {applyCurveDialog.curves.map(c => (
                                <SelectItem key={c.name} value={c.name}>{c.name}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
                <p className="text-sm text-muted-foreground">
                    将根据该商品的 "1天租金" 和选定曲线的比例，自动计算并填充其他天数的租金。
                </p>
            </div>
            <DialogFooter>
                <Button onClick={handleApplyCurve}>确认应用</Button>
            </DialogFooter>
        </DialogContent>
      </Dialog>

      {logs && (
        <Card className="shrink-0 max-h-[200px] overflow-hidden flex flex-col">
          <CardHeader className="py-2 px-4 border-b">
            <CardTitle className="text-sm">执行日志</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
             <ScrollArea className="h-[150px] p-4 font-mono text-xs bg-muted/50 whitespace-pre-wrap">
               {logs}
             </ScrollArea>
          </CardContent>
        </Card>
      )}

      <ScrollArea className="flex-1">
        <div className="pb-20 space-y-8">
            {groupedItems.map(([groupId, { items: groupItems, skuKeys, hasBaseSku }]) => {
                const firstItem = groupItems[0]?.item;
                return (
                    <Card key={groupId} className="w-full shadow-md">
                        <CardHeader className="py-3 px-4 border-b flex flex-row items-center justify-between bg-muted/20">
                            <div className="flex items-center gap-2">
                                <span className="font-mono font-bold bg-primary/10 px-2 py-1 rounded text-primary">{groupId}</span>
                                <span className="font-medium text-sm truncate max-w-[400px]" title={firstItem?.商品名称}>{firstItem?.商品名称}</span>
                            </div>
                            <Button 
                                variant="outline" 
                                size="sm" 
                                onClick={() => openSpecDialog(groupId)} 
                                className="gap-2 h-8"
                            >
                                <Settings2 className="h-3 w-3" /> 批量增加规格
                            </Button>
                        </CardHeader>
                        <CardContent className="p-0 overflow-auto">
                            <Table className="w-full border-collapse">
                                <TableHeader className="bg-secondary/50">
                                    <TableRow>
                                        {/* Dynamic SKU Columns */}
                                        {skuKeys.length > 0 ? (
                                            <>
                                                {hasBaseSku && <TableHead className="w-[100px] border-r p-2 text-xs">SKU (基础)</TableHead>}
                                                {skuKeys.map(k => (
                                                    <TableHead key={k} className="w-[100px] border-r p-2 text-xs">{k}</TableHead>
                                                ))}
                                            </>
                                        ) : (
                                            <TableHead className="w-[120px] border-r p-2 text-xs">SKU</TableHead>
                                        )}
                                        <TableHead className="w-[200px] border-r p-2 text-xs">商品名称</TableHead>
                                        <TableHead className="w-[120px] border-r p-2 text-xs">支付宝编码</TableHead>
                                        {/* Removed explicit Logistics column as per request */}
                                        <TableHead className="w-[60px] border-r p-2 text-xs text-center">库存</TableHead>
                                        {rentCols.map(c => (
                                            <TableHead key={c} className="border-r min-w-[80px] text-center p-2 text-xs">{c.replace('租金','')}</TableHead>
                                        ))}
                                        {priceCols.map(c => (
                                            <TableHead key={c} className="border-r min-w-[70px] text-center p-2 text-xs">{c}</TableHead>
                                        ))}
                                        <TableHead className="w-[80px] border-r p-2 text-xs text-center">操作</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {groupItems.map(({ item, index: globalIndex }, groupIndex) => {
                                        // Calculate rent anomalies for this item
                                        const rentInfo = getRentInfo(item);
                                        return (
                                            <TableRow key={globalIndex} className="hover:bg-muted/30">
                                                {skuKeys.length > 0 ? (
                                                    <>
                                                        {hasBaseSku && (
                                                            <TableCell className="border-r p-1 align-top text-xs font-mono">
                                                                <Input 
                                                                    className="h-7 text-xs px-2"
                                                                    value={(() => {
                                                                        const parts = (item.SKU || "").split("|");
                                                                        return parts.filter(p => !p.match(/[:：]/)).join("|");
                                                                    })()}
                                                                    onChange={(e) => handleBaseSkuChange(globalIndex, e.target.value)}
                                                                    title={item.SKU}
                                                                />
                                                            </TableCell>
                                                        )}
                                                        {skuKeys.map(k => {
                                                            const parts = (item.SKU || "").split("|");
                                                            const match = parts.find(p => {
                                                                const m = p.match(/[:：]/);
                                                                return m && p.substring(0, m.index) === k;
                                                            });
                                                            let val = "";
                                                            if (match) {
                                                                const m = match.match(/[:：]/);
                                                                if (m) {
                                                                    val = match.substring(m.index! + 1);
                                                                }
                                                            }
                                                            return (
                                                                <TableCell key={k} className="border-r p-1 align-top text-xs font-mono">
                                                                    <Input 
                                                                        className="h-7 text-xs px-2"
                                                                        value={val}
                                                                        onChange={(e) => handleSkuPartChange(globalIndex, k, e.target.value)}
                                                                        title={val}
                                                                    />
                                                                </TableCell>
                                                            );
                                                        })}
                                                    </>
                                                ) : (
                                                    <TableCell className="border-r p-1 align-top text-xs font-mono">
                                                        <Input 
                                                            className="h-7 text-xs px-2 min-w-[120px]" 
                                                            value={item.SKU || ""} 
                                                            onChange={(e) => handleFieldChange(globalIndex, "SKU", e.target.value)}
                                                            title={item.SKU}
                                                        />
                                                    </TableCell>
                                                )}

                                                <TableCell className="border-r p-1">
                                                    <Input 
                                                        className="h-7 text-xs px-2" 
                                                        value={item.商品名称} 
                                                        onChange={(e) => handleFieldChange(globalIndex, "商品名称", e.target.value)}
                                                        title={item.商品名称}
                                                    />
                                                </TableCell>
                                                <TableCell className="border-r p-1">
                                                    <Input 
                                                        className="h-7 text-xs px-2" 
                                                        value={item.支付宝编码 || ""} 
                                                        onChange={(e) => handleFieldChange(globalIndex, "支付宝编码", e.target.value)}
                                                        title={item.支付宝编码}
                                                    />
                                                </TableCell>
                                                <TableCell className="border-r p-1">
                                                    <Input 
                                                        className="h-7 text-xs px-2 text-center" 
                                                        value={String(item["库存"] || "")} 
                                                        onChange={(e) => handleFieldChange(globalIndex, "库存", e.target.value)}
                                                    />
                                                </TableCell>
                                                {rentCols.map(col => {
                                                    const days = parseInt(col);
                                                    const isAnomaly = rentInfo.anomalyDays.has(days);
                                                    const val = Number(item[col]);
                                                    const dailyRent = (val && !isNaN(val) && val > 0) ? (val / days).toFixed(1) : null;
                                                    
                                                    return (
                                                        <TableCell key={col} className={cn("border-r p-1 relative", isAnomaly && "bg-green-100 dark:bg-green-900/20")}>
                                                            <Input 
                                                                className={cn("h-7 text-xs px-1 text-center", isAnomaly && "border-green-500")}
                                                                value={String(item[col] || "")} 
                                                                onChange={(e) => handleFieldChange(globalIndex, col, e.target.value)}
                                                            />
                                                            {dailyRent && (
                                                                <div className={cn("text-[10px] text-center mt-0.5", isAnomaly ? "text-green-600 font-bold" : "text-muted-foreground")}>
                                                                    ¥{dailyRent}/天
                                                                </div>
                                                            )}
                                                        </TableCell>
                                                    );
                                                })}
                                                {priceCols.map(col => (
                                                    <TableCell key={col} className="border-r p-1">
                                                        <Input 
                                                            className="h-7 text-xs px-1 text-center" 
                                                            value={String(item[col] || "")} 
                                                            onChange={(e) => handleFieldChange(globalIndex, col, e.target.value)}
                                                        />
                                                    </TableCell>
                                                ))}
                                                <TableCell className="border-r p-1">
                                                    <div className="flex items-center justify-center gap-1">
                                                        <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => openApplyCurveDialog(globalIndex)} title="应用租金曲线">
                                                            <Wand2 className="h-3 w-3" />
                                                        </Button>
                                                        <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => openDiffDialog(globalIndex, groupId, groupIndex)} title="批量差价">
                                                            <Calculator className="h-3 w-3" />
                                                        </Button>
                                                        <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => handleDuplicateRow(globalIndex)} title="复制行">
                                                            <Copy className="h-3 w-3" />
                                                        </Button>
                                                        <Button size="icon" variant="ghost" className="h-6 w-6 text-red-500 hover:text-red-600 hover:bg-red-50" onClick={() => handleDeleteRow(globalIndex)} title="删除行">
                                                            <Trash2 className="h-3 w-3" />
                                                        </Button>
                                                    </div>
                                                </TableCell>
                                            </TableRow>
                                        );
                                    })}
                                </TableBody>
                            </Table>
                        </CardContent>
                    </Card>
                );
            })}
        </div>
      </ScrollArea>
    </div>
  );
}

export default function Workbench() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-screen">Loading...</div>}>
      <WorkbenchContent />
    </Suspense>
  );
}
