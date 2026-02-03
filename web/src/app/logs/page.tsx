"use client";

import { useEffect, useState } from "react";
import { fetchLogs, fetchTaskStatus } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Loader2 } from "lucide-react";

export default function LogsPage() {
  const [logs, setLogs] = useState("");
  const [status, setStatus] = useState<{ running: boolean; task_name: string | null; message: string }>({
    running: false,
    task_name: null,
    message: "Idle"
  });

  useEffect(() => {
    // 立即加载一次
    loadData();
    
    // 轮询
    const interval = setInterval(loadData, 1000);
    return () => clearInterval(interval);
  }, []);

  const loadData = async () => {
    try {
      const [logRes, statusRes] = await Promise.all([
        fetchLogs(),
        fetchTaskStatus()
      ]);
      setLogs(logRes.logs);
      setStatus(statusRes);
    } catch (e) {
      // ignore errors during poll
    }
  };

  return (
    <div className="container mx-auto p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">自动化任务日志</h1>
        <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">当前状态:</span>
            {status.running ? (
                <Badge variant="default" className="bg-blue-600 flex items-center gap-1">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    运行中 ({status.task_name})
                </Badge>
            ) : (
                <Badge variant="secondary">空闲</Badge>
            )}
        </div>
      </div>
      
      <Card className="h-[calc(100vh-120px)] flex flex-col">
        <CardHeader className="py-3 border-b bg-muted/50">
          <div className="flex justify-between items-center">
             <CardTitle className="text-sm font-medium">Console Output</CardTitle>
             <span className="text-xs text-muted-foreground">{status.message}</span>
          </div>
        </CardHeader>
        <CardContent className="flex-1 p-0 overflow-hidden">
          <ScrollArea className="h-full p-4 bg-black text-white font-mono text-xs">
            <pre className="whitespace-pre-wrap">{logs || "暂无日志..."}</pre>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}
