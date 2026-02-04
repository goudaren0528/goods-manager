"use client";

import { useCallback, useEffect, useState, Fragment } from "react";
import { GoodsGroup, fetchGoods, runScrape, runPartialScrape, fetchTaskStatus, API_BASE, EXPORT_URL, updateMerchant, fetchConfig, updateConfig, saveRentCurve, RentCurve, deleteGoods, stopTask, updateAlipayCode } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { useRouter } from "next/navigation";
import { Loader2, ChevronRight, ChevronDown, ChevronLeft, Wand2, Trash2, XCircle } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn, getRentInfo, RENT_DAYS } from "@/lib/utils";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

function AlipayCodeInput({ id, initialValue }: { id: string; initialValue: string }) {
  const [value, setValue] = useState(initialValue);
  const [loading, setLoading] = useState(false);

  // Sync with props if they change (e.g. after reload)
  useEffect(() => {
    setValue(initialValue);
  }, [initialValue]);

  const handleBlur = async () => {
    if (value === initialValue) return;
    setLoading(true);
    try {
      await updateAlipayCode(id, value);
      toast.success("支付宝编码已更新");
    } catch (e) {
      toast.error("更新失败");
      // Don't revert immediately, user might want to retry. 
      // But for consistency we might want to revert or just show error.
      // Reverting is safer for data consistency.
      setValue(initialValue);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.currentTarget.blur();
    }
  };

  return (
    <div className="relative">
      <Input 
        value={value} 
        onChange={(e) => setValue(e.target.value)} 
        onBlur={handleBlur}
        onKeyDown={handleKeyDown}
        className="h-8 w-full text-xs pr-6"
        disabled={loading}
        placeholder="输入编码"
      />
      {loading && <Loader2 className="h-3 w-3 absolute right-2 top-2.5 animate-spin text-muted-foreground" />}
    </div>
  );
}

export default function Home() {
  const router = useRouter();
  const [goods, setGoods] = useState<GoodsGroup[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  
  // 提取曲线状态
  const [extractDialogOpen, setExtractDialogOpen] = useState(false);
  const [extractCurveName, setExtractCurveName] = useState("");
  const [extractSourceSku, setExtractSourceSku] = useState<any>(null);
  const [previewCurve, setPreviewCurve] = useState<Record<string, number>>({});

  // 删除确认状态
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [goodsToDelete, setGoodsToDelete] = useState<string | null>(null);

  // 抓取确认状态
  const [scrapeConfirmOpen, setScrapeConfirmOpen] = useState(false);

  // 过滤功能状态
  const [filterKeywords, setFilterKeywords] = useState("已出租,下架,不可租");
  const [isFilterEnabled, setIsFilterEnabled] = useState(true);
  const [merchantFilter, setMerchantFilter] = useState("米奇");
  const [syncStatusFilter, setSyncStatusFilter] = useState("all");

  const [partialScrapeOpen, setPartialScrapeOpen] = useState(false);
  const [partialScrapeIds, setPartialScrapeIds] = useState("");

  const [searchTerm, setSearchTerm] = useState("");
  const [taskStatus, setTaskStatus] = useState<{ running: boolean; task_name: string | null; message: string; progress: number }>({
    running: false,
    task_name: null,
    message: "Idle",
    progress: 0
  });

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [total, setTotal] = useState(0);

  // Load config on mount
  useEffect(() => {
    fetchConfig().then(config => {
      if (config.filter_keywords !== undefined) setFilterKeywords(config.filter_keywords);
      if (config.default_merchant_filter !== undefined) setMerchantFilter(config.default_merchant_filter);
    });
  }, []);

  const loadData = useCallback(async (suppressToast = false) => {
    setLoading(true);
    try {
      const merchantParam = merchantFilter === "all" ? undefined : merchantFilter;
      const res = await fetchGoods(page, pageSize, false, merchantParam, syncStatusFilter);
      setGoods(Array.isArray(res.data) ? res.data : []);
      setTotal(typeof res.total === "number" ? res.total : 0);
    } catch (e) {
      if (!suppressToast) toast.error("加载数据失败: " + String(e));
      setGoods([]);
      setTotal(0);
    }
    setLoading(false);
  }, [page, pageSize, merchantFilter, syncStatusFilter]);

  useEffect(() => {
    const timeout = setTimeout(() => {
      void loadData();
    }, 0);
    return () => clearTimeout(timeout);
  }, [page, pageSize, loadData]);

  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const status = await fetchTaskStatus();
        setTaskStatus(prev => {
          if (prev.running && !status.running) {
            toast.success("任务已完成，正在刷新数据...");
            loadData(true);
          }
          return status;
        });
      } catch (e) {
        console.error(e);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [loadData]);

  const handleMerchantChange = async (id: string, newMerchant: string) => {
    try {
      await updateMerchant(id, newMerchant);
      toast.success(`商家已更新`);
      loadData(true);
    } catch (e) {
      toast.error("更新商家失败: " + String(e));
    }
  };

  const toggleExpand = (id: string) => {
    const newSet = new Set(expandedIds);
    if (newSet.has(id)) {
      newSet.delete(id);
    } else {
      newSet.add(id);
    }
    setExpandedIds(newSet);
  };

  const handleSync = async () => {
    try {
      setScrapeConfirmOpen(false);
      await runScrape();
      toast.success("抓取任务已启动，请在日志中查看进度");
      setTaskStatus({ running: true, task_name: "scrape", message: "Starting scrape task...", progress: 0 });
    } catch (e) {
      toast.error("启动失败: " + String(e));
    }
  };

  const handleStopTask = async () => {
    try {
      await stopTask();
      toast.success("已发送中止请求");
    } catch (e) {
      toast.error("中止失败: " + String(e));
    }
  };

  const handlePartialScrape = async () => {
    if (!partialScrapeIds.trim()) {
        toast.error("请输入商品ID");
        return;
    }
    const ids = partialScrapeIds.split(/[,，\n]/).map(s => s.trim()).filter(Boolean);
    if (ids.length === 0) {
        toast.error("无效的ID列表");
        return;
    }

    try {
        await runPartialScrape(ids);
        toast.success(`已启动 ${ids.length} 个商品的抓取任务`);
        setTaskStatus({ running: true, task_name: "scrape", message: `Starting partial scrape for ${ids.length} items...`, progress: 0 });
        setPartialScrapeOpen(false);
    } catch (e) {
        toast.error("启动失败: " + String(e));
    }
  };

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
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
    const ids = Array.from(selectedIds).join(",");
    router.push(`/workbench?ids=${ids}`);
  };

  // Render constants
  const PRICE_COLS = ["市场价", "押金", "购买价", "采购价"];

  // 过滤后的数据
  const filteredGoods = goods.filter(group => {
    if (!isFilterEnabled || !filterKeywords) return true;
    
    // 分割关键字，去除空白
    const keywords = filterKeywords.split(/[,，]/).map(k => k.trim()).filter(Boolean);
    if (keywords.length === 0) return true;

    // 只要商品名称包含任意一个关键字，就过滤掉
    const name = group.商品名称 || "";
    for (const k of keywords) {
      if (name.includes(k)) {
        return false;
      }
    }
    return true;
  });



  const handleExtractCurve = (sku: any) => {
    // 1. 验证必须包含的租期
    const requiredDays = [1, 3, 5, 7, 15, 30, 60, 90];
    const missingDays = requiredDays.filter(d => {
        const val = Number(sku[`${d}天租金`]);
        return isNaN(val) || val <= 0;
    });

    if (missingDays.length > 0) {
        toast.error(`商品租期数据不完整，无法生成曲线。缺失租期: ${missingDays.join("天, ")}天`);
        return;
    }

    // Check if 1-day rent exists and is valid (already covered by requiredDays but good for base calculation)
    const baseRent = Number(sku["1天租金"]);
    
    const curve: Record<string, number> = {};
    RENT_DAYS.forEach(d => {
        const val = Number(sku[`${d}天租金`]);
        if (!isNaN(val) && val > 0) {
            curve[String(d)] = Number((val / baseRent).toFixed(4));
        }
    });

    setExtractSourceSku(sku);
    setPreviewCurve(curve);
    setExtractCurveName(`${sku["SKU"] || "默认"}-曲线`);
    setExtractDialogOpen(true);
  };

  const handleSaveCurve = async () => {
    if (!extractCurveName) {
        toast.error("请输入曲线名称");
        return;
    }
    try {
        await saveRentCurve({
            name: extractCurveName,
            multipliers: previewCurve,
            source_sku: extractSourceSku?.SKU || extractSourceSku?.商品名称 || "未知商品",
            source_name: extractSourceSku?.商品名称 || ""
        });
        toast.success("租金曲线已保存");
        setExtractDialogOpen(false);
    } catch (e) {
        toast.error("保存失败: " + String(e));
    }
  };

  const handleDeleteGoods = async () => {
    if (!goodsToDelete) return;
    try {
        await deleteGoods(goodsToDelete);
        toast.success(`商品 ${goodsToDelete} 已删除`);
        setDeleteDialogOpen(false);
        setGoodsToDelete(null);
        loadData(true);
    } catch (e) {
        toast.error("删除失败: " + String(e));
    }
  };

  return (
    <div className="w-full max-w-[1800px] mx-auto p-4 space-y-4">
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除?</AlertDialogTitle>
            <AlertDialogDescription>
              此操作将永久删除商品 {goodsToDelete} 及其所有相关数据。此操作无法撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setGoodsToDelete(null)}>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteGoods} className="bg-red-600 hover:bg-red-700">确认删除</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={scrapeConfirmOpen} onOpenChange={setScrapeConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认更新所有商品?</AlertDialogTitle>
            <AlertDialogDescription>
              抓取所有商品需要10~30分钟，请确认是否继续。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setScrapeConfirmOpen(false)}>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleSync}>确认更新</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog open={extractDialogOpen} onOpenChange={setExtractDialogOpen}>
        <DialogContent>
            <DialogHeader>
                <DialogTitle>提取租金曲线</DialogTitle>
            </DialogHeader>
            <div className="grid gap-4 py-4">
                <div className="grid grid-cols-4 items-center gap-4">
                    <Label className="text-right">曲线名称</Label>
                    <Input 
                        value={extractCurveName}
                        onChange={e => setExtractCurveName(e.target.value)}
                        className="col-span-3"
                    />
                </div>
                <div className="space-y-2">
                    <Label>预览数据 (相对于1天租金的倍数)</Label>
                    <div className="grid grid-cols-4 gap-2 text-xs font-mono bg-muted p-2 rounded max-h-[200px] overflow-y-auto">
                        {Object.entries(previewCurve).map(([day, mult]) => (
                            <div key={day} className="flex justify-between border-b pb-1">
                                <span>{day}天:</span>
                                <span>x{mult}</span>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
            <DialogFooter>
                <Button onClick={handleSaveCurve}>保存配置</Button>
            </DialogFooter>
        </DialogContent>
      </Dialog>
      
      <Dialog open={partialScrapeOpen} onOpenChange={setPartialScrapeOpen}>
        <DialogContent>
            <DialogHeader>
                <DialogTitle>抓取部分商品</DialogTitle>
            </DialogHeader>
            <div className="py-4 space-y-2">
                <Label>输入商品ID (支持逗号、换行分隔)</Label>
                <Textarea 
                    value={partialScrapeIds}
                    onChange={e => setPartialScrapeIds(e.target.value)}
                    placeholder="12345, 67890&#10;11223"
                    className="h-[150px]"
                />
                <p className="text-xs text-muted-foreground">注意：只会更新输入的商品，不会扫描列表页。</p>
            </div>
            <DialogFooter>
                <Button onClick={handlePartialScrape}>开始抓取</Button>
            </DialogFooter>
        </DialogContent>
      </Dialog>
      
      <div className="flex flex-col gap-4 md:flex-row md:justify-between md:items-center">
        <h1 className="text-2xl font-bold">支付宝商品管理</h1>
        <div className="flex flex-col gap-2 sm:flex-row items-center flex-wrap">
            
          <div className="flex items-center gap-2">
             <span className="text-sm font-medium whitespace-nowrap">商家:</span>
             <Select value={merchantFilter} onValueChange={(v) => { 
                 setMerchantFilter(v); 
                 setPage(1); 
                 updateConfig("default_merchant_filter", v);
             }}>
                <SelectTrigger className="w-[80px] h-8">
                    <SelectValue />
                </SelectTrigger>
                <SelectContent>
                    <SelectItem value="米奇">米奇</SelectItem>
                    <SelectItem value="星享">星享</SelectItem>
                    <SelectItem value="活力">活力</SelectItem>
                    <SelectItem value="all">全部</SelectItem>
                </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-2">
             <span className="text-sm font-medium whitespace-nowrap">同步:</span>
             <Select value={syncStatusFilter} onValueChange={(v) => { 
                 setSyncStatusFilter(v); 
                 setPage(1); 
             }}>
                <SelectTrigger className="w-[80px] h-8">
                    <SelectValue />
                </SelectTrigger>
                <SelectContent>
                    <SelectItem value="all">全部</SelectItem>
                    <SelectItem value="已同步">已同步</SelectItem>
                    <SelectItem value="未同步">未同步</SelectItem>
                </SelectContent>
            </Select>
          </div>

          {/* 关键字过滤控制 */}
          <div className="flex items-center gap-2 border rounded-md p-1 px-2 bg-muted/20">
            <Checkbox 
                id="filter-enabled" 
                checked={isFilterEnabled} 
                onCheckedChange={(c) => setIsFilterEnabled(!!c)} 
            />
            <label htmlFor="filter-enabled" className="text-sm cursor-pointer whitespace-nowrap font-medium">
                过滤关键字:
            </label>
            <Input 
                className="h-7 w-[150px] text-xs" 
                value={filterKeywords}
                onChange={(e) => setFilterKeywords(e.target.value)}
                onBlur={(e) => updateConfig("filter_keywords", e.target.value)}
                placeholder="关键字1,关键字2"
                title="商品名称包含这些关键字时将被隐藏，多个关键字用逗号分隔"
            />
          </div>

          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground whitespace-nowrap">每页:</span>
            <Select value={String(pageSize)} onValueChange={(v) => { setPageSize(Number(v)); setPage(1); }}>
                <SelectTrigger className="w-[80px]">
                    <SelectValue />
                </SelectTrigger>
                <SelectContent>
                    <SelectItem value="20">20</SelectItem>
                    <SelectItem value="50">50</SelectItem>
                    <SelectItem value="100">100</SelectItem>
                </SelectContent>
            </Select>
          </div>

          <Button variant="outline" onClick={() => window.open(EXPORT_URL, "_blank")}>
            导出 Excel
          </Button>
          <Button variant="ghost" size="icon" onClick={() => loadData()} title="刷新数据">
              <Loader2 className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
          <Button 
            variant="outline" 
            onClick={() => setPartialScrapeOpen(true)}
            disabled={taskStatus.running}
          >
            更新部分商品
          </Button>
          <Button 
            variant="outline" 
            onClick={() => setScrapeConfirmOpen(true)} 
            disabled={taskStatus.running}
            className={taskStatus.running ? "opacity-50 cursor-not-allowed" : ""}
          >
            {taskStatus.running ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            {taskStatus.running ? "后台任务运行中..." : "更新所有商品"}
          </Button>
          <Button onClick={startEdit} disabled={selectedIds.size === 0 || taskStatus.running}>
            进入修改工作台 ({selectedIds.size})
          </Button>
        </div>
      </div>

      {taskStatus.running && (
        <div className="w-full flex items-center gap-2 px-1">
            <span className="text-sm text-muted-foreground whitespace-nowrap">
                任务运行中 ({taskStatus.progress}%): {taskStatus.message}
            </span>
            <Progress value={taskStatus.progress} className="h-2 flex-1" />
            <Button 
                variant="destructive" 
                size="sm" 
                className="h-7 px-2 text-xs"
                onClick={handleStopTask}
            >
                <XCircle className="h-3 w-3 mr-1" />
                中止任务
            </Button>
        </div>
      )}
      
      <div className="border rounded-md overflow-hidden bg-white dark:bg-zinc-950 shadow-sm">
        <Table className="w-full text-sm">
          <TableHeader className="bg-muted/50">
            <TableRow className="h-8">
              <TableHead className="w-[30px] px-1 text-center">
                <Checkbox
                  checked={filteredGoods.length > 0 && selectedIds.size === filteredGoods.length}
                  onCheckedChange={(c) => handleSelectAll(!!c)}
                />
              </TableHead>
              <TableHead className="w-[30px] px-1"></TableHead>
              <TableHead className="w-[60px] px-1">ID</TableHead>
              <TableHead className="w-[75px] px-1">商家</TableHead>
              <TableHead className="w-[120px] px-1">支付宝编码</TableHead>
              <TableHead className="w-[70px] px-1">同步状态</TableHead>
              <TableHead className="w-[150px] px-1">商品名称</TableHead>
              <TableHead className="w-[120px] px-1">分类</TableHead>
              <TableHead className="w-[60px] px-1 text-right">总库存</TableHead>
              <TableHead className="w-[50px] px-1 text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredGoods.length === 0 ? (
                <TableRow>
                    <TableCell colSpan={9} className="text-center h-24 text-muted-foreground">
                        {loading ? "加载中..." : (isFilterEnabled && goods.length > 0 ? "所有商品均已被关键字过滤" : "暂无数据")}
                    </TableCell>
                </TableRow>
            ) : (
              filteredGoods.map((group) => {
                const isSelected = selectedIds.has(group.ID);
                const isExpanded = expandedIds.has(group.ID);

                return (
                  <Fragment key={group.ID}>
                    <TableRow 
                        className={cn("cursor-pointer hover:bg-muted/50 h-8", isExpanded && "bg-muted/30")}
                        onClick={() => toggleExpand(group.ID)}
                    >
                      <TableCell className="px-1 text-center py-1" onClick={(e) => e.stopPropagation()}>
                        <Checkbox
                          checked={isSelected}
                          onCheckedChange={(c) => handleSelectOne(group.ID, !!c)}
                        />
                      </TableCell>
                      <TableCell className="px-1 text-center py-1">
                        {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                      </TableCell>
                      <TableCell className="font-medium font-mono px-1 py-1 text-xs">{group.ID}</TableCell>
                      <TableCell onClick={(e) => e.stopPropagation()} className="px-1 py-1">
                        <Select 
                            value={group.merchant || "米奇"} 
                            onValueChange={(v) => handleMerchantChange(group.ID, v)}
                        >
                            <SelectTrigger className="h-6 w-full text-[10px] px-1">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="米奇">米奇</SelectItem>
                                <SelectItem value="星享">星享</SelectItem>
                                <SelectItem value="活力">活力</SelectItem>
                            </SelectContent>
                        </Select>
                      </TableCell>
                      <TableCell className="px-1 py-1">
                          <AlipayCodeInput id={group.ID} initialValue={group.支付宝编码 || ""} />
                      </TableCell>
                      <TableCell className="px-1 py-1">
                        <span className={cn(
                            "px-1 py-0.5 rounded text-[10px] font-medium whitespace-nowrap",
                            group.是否同步支付宝 === "已同步" 
                                ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400" 
                                : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400"
                        )}>
                            {group.是否同步支付宝 || "未知"}
                        </span>
                      </TableCell>
                      <TableCell className="max-w-[150px] px-1 py-1">
                        <div className="flex flex-col">
                            <span className="font-medium truncate text-xs" title={group.商品名称}>{group.商品名称}</span>
                            {group.短标题 && <span className="text-[10px] text-muted-foreground truncate" title={group.短标题}>{group.短标题}</span>}
                        </div>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground max-w-[120px] truncate px-1 py-1" title={[group["1级分类"], group["2级分类"], group["3级分类"]].filter(Boolean).join(" / ")}>
                        {[group["1级分类"], group["2级分类"], group["3级分类"]].filter(Boolean).join(" / ")}
                      </TableCell>
                      <TableCell className="text-right font-mono px-1 py-1 text-xs">{group.库存}</TableCell>
                      <TableCell className="text-right px-1 py-1">
                         <Button 
                             variant="ghost" 
                             size="icon" 
                             className="h-6 w-6 text-muted-foreground hover:text-red-600"
                             onClick={(e) => {
                                 e.stopPropagation();
                                 setGoodsToDelete(group.ID);
                                 setDeleteDialogOpen(true);
                             }}
                             title="删除商品"
                         >
                             <Trash2 className="h-3 w-3" />
                         </Button>
                      </TableCell>
                    </TableRow>
                    
                    {isExpanded && (
                        <TableRow className="bg-muted/10 hover:bg-muted/10">
                            <TableCell colSpan={9} className="p-0">
                                <div className="p-4 bg-muted/20 border-b shadow-inner">
                                    <Table className="w-full text-xs border bg-background">
                                        <TableHeader>
                                            <TableRow className="bg-muted/50 hover:bg-muted/50">
                                                <TableHead className="h-8">SKU (套餐)</TableHead>
                                                <TableHead className="h-8">编号</TableHead>
                                                <TableHead className="h-8 text-right">库存</TableHead>
                                                {RENT_DAYS.map(d => (
                                                    <TableHead key={d} className="h-8 text-right min-w-[60px]">{d}天</TableHead>
                                                ))}
                                                {PRICE_COLS.map(p => (
                                                    <TableHead key={p} className="h-8 text-right min-w-[70px]">{p}</TableHead>
                                                ))}
                                            </TableRow>
                                        </TableHeader>
                                        <TableBody>
                                            {group.skus.map((sku, idx) => {
                                                const { anomalyDays } = getRentInfo(sku);
                                                return (
                                                <TableRow key={idx} className="hover:bg-muted/30">
                                                    <TableCell className="font-medium">{sku.SKU || "默认"}</TableCell>
                                                    <TableCell className="text-muted-foreground">{sku["编号"] as string}</TableCell>
                                                    <TableCell className="text-right font-mono">{sku["库存"] as number}</TableCell>
                                                    
                                                    {RENT_DAYS.map(d => {
                                                        const val = Number(sku[`${d}天租金`]);
                                                        const hasVal = !isNaN(val) && val > 0;
                                                        const daily = hasVal ? (val / d).toFixed(1) : "";
                                                        const isAnomaly = anomalyDays.has(d);
                                                        
                                                        return (
                                                            <TableCell key={d} className="text-right font-mono text-muted-foreground">
                                                                {hasVal ? (
                                                                    <div className={cn("flex flex-col items-end", isAnomaly && "text-green-600 font-bold")}>
                                                                        <span>{val}</span>
                                                                        <span className="text-[10px] opacity-70">({daily})</span>
                                                                    </div>
                                                                ) : "-"}
                                                            </TableCell>
                                                        );
                                                    })}
                                                    
                                                    {PRICE_COLS.map(p => (
                                                        <TableCell key={p} className="text-right font-mono">
                                                            {sku[p] as string || "-"}
                                                        </TableCell>
                                                    ))}
                                                    <TableCell className="text-right px-1 py-1">
                                                       <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => handleExtractCurve(sku)} title="提取租金曲线">
                                                           <Wand2 className="h-3 w-3" />
                                                       </Button>
                                                    </TableCell>
                                                </TableRow>
                                            )})}
                                        </TableBody>
                                    </Table>
                                </div>
                            </TableCell>
                        </TableRow>
                    )}
                  </Fragment>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination Controls */}
      <div className="flex items-center justify-between py-4">
          <div className="text-sm text-muted-foreground">
              共 {total} 个商品
          </div>
          <div className="flex items-center gap-2">
              <Button 
                variant="outline" 
                size="sm" 
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1 || loading}
              >
                  <ChevronLeft className="h-4 w-4" />
                  上一页
              </Button>
              <div className="text-sm font-medium">
                  第 {page} / {Math.ceil(total / pageSize) || 1} 页
              </div>
              <Button 
                variant="outline" 
                size="sm" 
                onClick={() => setPage(p => p + 1)}
                disabled={page >= Math.ceil(total / pageSize) || loading}
              >
                  下一页
                  <ChevronRight className="h-4 w-4" />
              </Button>
          </div>
      </div>
    </div>
  );
}

// ChevronLeft imported from lucide-react
