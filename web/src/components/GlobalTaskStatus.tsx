"use client";

import { useEffect, useState } from "react";
import { Progress } from "@/components/ui/progress";
import { Loader2, CheckCircle2 } from "lucide-react";
import { fetchTaskStatus } from "@/lib/api";

interface TaskStatus {
    running: boolean;
    task_name: string | null;
    message: string;
    progress: number;
    last_updated?: string;
}

export function GlobalTaskStatus() {
  const [status, setStatus] = useState<TaskStatus | null>(null);

  useEffect(() => {
    const poll = async () => {
      try {
        const res = await fetchTaskStatus();
        setStatus(res);
      } catch (e) {
        console.error(e);
      }
    };

    // Initial poll
    poll();
    
    // Poll every 2 seconds
    const interval = setInterval(poll, 2000);
    return () => clearInterval(interval);
  }, []);

  if (!status) return null;

  return (
    <div className="w-full border-b bg-background/95 px-4 py-2 text-sm shadow-sm">
        <div className="container mx-auto flex items-center justify-between gap-4">
            <div className="flex items-center gap-4 flex-1 overflow-hidden">
                {status.running ? (
                    <>
                        <div className="flex items-center gap-2 text-blue-600 font-medium whitespace-nowrap">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            <span>{status.task_name === 'scrape' ? '数据抓取中' : '数据更新中'}</span>
                        </div>
                        <div className="flex items-center gap-2 flex-1 max-w-md hidden sm:flex">
                            <Progress value={status.progress} className="h-2" />
                            <span className="text-xs text-muted-foreground w-12 text-right">{status.progress}%</span>
                        </div>
                        <span className="text-muted-foreground truncate hidden md:inline-block max-w-[300px]" title={status.message}>
                            {status.message}
                        </span>
                    </>
                ) : (
                    <div className="flex items-center gap-2 text-muted-foreground">
                        <CheckCircle2 className="h-4 w-4 text-green-500" />
                        <span>系统就绪</span>
                    </div>
                )}
            </div>
            
            {status.last_updated && (
                <div className="text-xs text-muted-foreground whitespace-nowrap flex items-center gap-2">
                    <span>最近更新:</span>
                    <span className="font-mono font-medium text-foreground bg-muted px-2 py-0.5 rounded">
                        {status.last_updated}
                    </span>
                </div>
            )}
        </div>
    </div>
  );
}
