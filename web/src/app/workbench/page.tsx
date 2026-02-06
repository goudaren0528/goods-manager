"use client";

import { useEffect, useState, Suspense, useMemo, useCallback, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { GoodsItem, fetchGoods, prepareUpdate, triggerUpdate, fetchLogs, fetchTaskStatus, updateAlipayCode, RentCurve, fetchRentCurves, startAutomation, getAutomationStatus, submitCaptcha, stopTask, AutomationStatus } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Progress } from "@/components/ui/progress";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { toast } from "sonner";
import { ArrowLeft, Play, Trash2, Copy, Settings2, Calculator, Wand2, Loader2 } from "lucide-react";
import { getRentInfo, RENT_DAYS } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

function AlipayCodeInput({
  id,
  initialValue,
  onUpdated
}: {
  id: string;
  initialValue: string;
  onUpdated: (value: string) => void;
}) {
  const [value, setValue] = useState(initialValue);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setValue(initialValue);
  }, [initialValue]);

  useEffect(() => {
    if (editing) {
      setTimeout(() => {
        inputRef.current?.focus();
        inputRef.current?.select();
      }, 0);
    }
  }, [editing]);

  const handleBlur = async () => {
    if (value === initialValue) {
      setEditing(false);
      return;
    }
    setLoading(true);
    try {
      await updateAlipayCode(id, value);
      onUpdated(value);
      toast.success("支付宝编码已更新");
    } catch {
      toast.error("更新失败");
      setValue(initialValue);
    } finally {
      setLoading(false);
      setEditing(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.currentTarget.blur();
    }
    if (e.key === "Escape") {
      setValue(initialValue);
      setEditing(false);
    }
  };

  const handleCopy = async () => {
    if (!value) {
      toast.error("暂无可复制的编码");
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      toast.success("已复制");
    } catch {
      toast.error("复制失败");
    }
  };

  return (
    <div className="flex items-center gap-1">
      {editing ? (
        <div className="relative w-full">
          <Input
            ref={inputRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onBlur={handleBlur}
            onKeyDown={handleKeyDown}
            className="h-7 w-full text-xs pr-6"
            disabled={loading}
            placeholder="输入编码"
          />
          {loading && <Loader2 className="h-3 w-3 absolute right-2 top-2 animate-spin text-muted-foreground" />}
        </div>
      ) : (
        <>
          <Button variant="ghost" size="sm" className="h-7 px-2 text-xs flex-1 justify-start" onClick={() => setEditing(true)}>
            {value ? value : "点击设置"}
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={handleCopy} disabled={!value}>
            <Copy className="h-3 w-3" />
          </Button>
        </>
      )}
    </div>
  );
}

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

  // 自动化任务状态
  const [autoDialogOpen, setAutoDialogOpen] = useState(false);
  const [autoPhone, setAutoPhone] = useState("");
  const [autoStatus, setAutoStatus] = useState<AutomationStatus>({ status: "idle", message: "" });
  const [captchaDialogOpen, setCaptchaDialogOpen] = useState(false);
  const [captchaCode, setCaptchaCode] = useState("");
  const [autoInterval, setAutoInterval] = useState<NodeJS.Timeout | null>(null);

  // 清理轮询
  useEffect(() => {
    return () => {
        if (autoInterval) clearInterval(autoInterval);
    };
  }, [autoInterval]);

  const startPolling = useCallback(() => {
      if (autoInterval) clearInterval(autoInterval);
      const interval = setInterval(async () => {
          try {
            const status = await getAutomationStatus();
            setAutoStatus(status);
            
            // 如果正在等待验证码，且弹窗未打开，则打开
            if (status.status === "waiting_for_captcha") {
                setCaptchaDialogOpen(true);
            }
            
            if (status.status === "finished" || status.status === "error") {
                clearInterval(interval);
                setAutoInterval(null);
                if (status.status === "finished") toast.success("自动化更新任务完成");
                else toast.error("任务出错: " + status.message);
            }
          } catch {}
      }, 1000);
      setAutoInterval(interval);
  }, [autoInterval]);

  useEffect(() => {
      const init = async () => {
          try {
              const status = await getAutomationStatus();
              setAutoStatus(status);
              if (status.status === "running" || status.status === "waiting_for_captcha") {
                  startPolling();
              }
          } catch {}
      };
      init();
  }, [startPolling]);

  const handleStartAutomation = async () => {
      try {
          // Extract unique IDs from current items
          const uniqueIds = Array.from(new Set(items.map(i => i.ID)));
          if (uniqueIds.length === 0) {
              toast.error("当前没有商品");
              return;
          }
          
          await startAutomation(uniqueIds, autoPhone);
          setAutoDialogOpen(false);
          setAutoStatus({ status: "running", message: "启动中..." });
          toast.success("自动化任务已启动，请留意浏览器窗口");
          startPolling();
      } catch (error) {
          const message = error instanceof Error ? error.message : "启动失败";
          toast.error(message);
      }
  };

  const handleSubmitCaptcha = async () => {
      try {
          await submitCaptcha(captchaCode);
          setCaptchaDialogOpen(false);
          setCaptchaCode("");
          toast.success("验证码已提交");
      } catch (error) {
          const message = error instanceof Error ? error.message : "验证码提交失败";
          toast.error(message);
      }
  };

  const handleStopAutomation = async () => {
      try {
          await stopTask();
          toast.success("已发送中止请求");
      } catch (error) {
          const message = error instanceof Error ? error.message : "中止失败";
          toast.error(message);
      }
  };

  const total = autoStatus.total ?? 0;
  const processed = autoStatus.processed ?? 0;
  const successCount = autoStatus.success_count ?? 0;
  const errorCount = autoStatus.error_count ?? 0;
  const progress = total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : 0;

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
      } catch {
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
      const interval = setInterval(async () => {
        try {
          const [res, status] = await Promise.all([fetchLogs(), fetchTaskStatus()]);
          setLogs(res.logs);
          if (!status.running) {
            clearInterval(interval);
            setLogInterval(null);
            setLoading(false);
            const message = status.message || "更新任务已结束";
            if (message.includes("Error") || message.includes("失败")) {
              toast.error(message);
            } else {
              toast.success(message);
            }
          }
        } catch {}
      }, 1000);
      setLogInterval(interval);
      
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      toast.error(`启动更新失败：${message}`);
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
    } catch {
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

    Object.entries(curve.multipliers).forEach(([day, multiplier]) => {
        const key = `${day}天租金`;
        const newRent = Math.round(baseRent * multiplier);
        // Only update if the key is a valid rent column (though all should be if defined in RENT_DAYS)
        item[key] = newRent.toString();
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
          <Button variant="outline" onClick={() => setAutoDialogOpen(true)} disabled={autoStatus.status === "running" || autoStatus.status === "waiting_for_captcha"}>
            <Wand2 className="mr-2 h-4 w-4" />
            更新支付宝
          </Button>
          <Button onClick={handleSaveAndRun} disabled={loading} className="gap-2">
            {loading ? <Play className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {loading ? "执行中..." : "保存并执行自动化更新"}
          </Button>
        </div>
      </div>

      {(autoStatus.status === "running" || autoStatus.status === "waiting_for_captcha") && (
        <div className="flex items-center gap-3 px-1">
          <span className="text-sm text-muted-foreground whitespace-nowrap">{autoStatus.message}</span>
          <div className="flex items-center gap-2 min-w-[220px]">
            <Progress value={progress} className="h-2 w-36" />
            <span className="text-xs text-muted-foreground whitespace-nowrap">{progress}%</span>
          </div>
          <div className="text-xs text-muted-foreground whitespace-nowrap">
            {processed}/{total} 成功 {successCount} 失败 {errorCount}
          </div>
          {(autoStatus.current_id || autoStatus.current_code) && (
            <div className="text-xs text-muted-foreground whitespace-nowrap">
              当前: {autoStatus.current_id || "-"} / {autoStatus.current_code || "-"}
            </div>
          )}
          <Button variant="destructive" size="sm" className="h-7 px-2 text-xs" onClick={handleStopAutomation}>
            中止任务
          </Button>
        </div>
      )}

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
              例如输入 &quot;红色, 蓝色&quot;，原来的每一行都会分裂成两行。
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
                    将根据该商品的 &quot;1天租金&quot; 和选定曲线的比例，自动计算并填充其他天数的租金。
                </p>
            </div>
            <DialogFooter>
                <Button onClick={handleApplyCurve}>确认应用</Button>
            </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={autoDialogOpen} onOpenChange={setAutoDialogOpen}>
        <DialogContent>
            <DialogHeader>
                <DialogTitle>启动支付宝自动化更新</DialogTitle>
            </DialogHeader>
            <div className="py-4 space-y-4">
                <p className="text-sm text-muted-foreground">
                    即将启动浏览器自动化脚本，对当前列表中的商品进行支付宝信息更新。
                    <br/>
                    请确保已在 &quot;支付宝编码&quot; 列中填入了正确的商家侧编码。
                </p>
                <div className="grid grid-cols-4 items-center gap-4">
                    <Label className="text-right">登录手机号</Label>
                    <Input 
                        value={autoPhone}
                        onChange={e => setAutoPhone(e.target.value)}
                        placeholder="请输入用于接收验证码的手机号"
                        className="col-span-3"
                    />
                </div>
            </div>
            <DialogFooter>
                <Button onClick={handleStartAutomation}>启动任务</Button>
            </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={captchaDialogOpen} onOpenChange={setCaptchaDialogOpen}>
        <DialogContent>
            <DialogHeader>
                <DialogTitle>需要验证码</DialogTitle>
            </DialogHeader>
            <div className="py-4 space-y-4">
                <p className="text-sm text-red-500 font-bold">
                    脚本正在等待短信验证码登录，请查看手机并输入。
                </p>
                <div className="grid grid-cols-4 items-center gap-4">
                    <Label className="text-right">验证码</Label>
                    <Input 
                        value={captchaCode}
                        onChange={e => setCaptchaCode(e.target.value)}
                        placeholder="6位验证码"
                        className="col-span-3"
                        autoFocus
                    />
                </div>
            </div>
            <DialogFooter>
                <Button onClick={handleSubmitCaptcha}>提交验证码</Button>
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
                                                    <AlipayCodeInput
                                                        id={String(item.ID)}
                                                        initialValue={typeof item.支付宝编码 === "string" ? item.支付宝编码 : String(item.支付宝编码 ?? "")}
                                                        onUpdated={(value) => handleFieldChange(globalIndex, "支付宝编码", value)}
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
