from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import pandas as pd
import numpy as np
import sqlite3
from typing import List, Optional, Any
import os
import shutil
import json
import subprocess
import glob
import logging

app = FastAPI()

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "../goods.db"
EXCEL_PATH = "../goods_data.xlsx"
UPDATE_EXCEL_PATH = "../update_goods_data.xlsx"

# 数据库初始化
def init_db():
    # 如果数据库不存在，从 Excel 初始化
    if not os.path.exists(DB_PATH):
        if os.path.exists(EXCEL_PATH):
            df = pd.read_excel(EXCEL_PATH)
            # 确保列名合法 (替换空格等)
            df.columns = [c.strip() for c in df.columns]
            
            # 创建连接
            conn = sqlite3.connect(DB_PATH)
            # 写入 SQLite
            df.to_sql("goods", conn, if_exists="replace", index=False)
            conn.close()
            print("Initialized database from Excel")
        else:
            print("Excel file not found, creating empty DB")
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS goods 
                         (ID text, 商品名称 text, 短标题 text, SKU text, 库存 integer, 
                          PRIMARY KEY (ID))''')
            conn.commit()
            conn.close()

init_db()

@app.get("/")
def read_root():
    return {"message": "Goods Manager API"}

@app.get("/goods")
def get_goods():
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query("SELECT * FROM goods", conn)
        df = df.replace([np.inf, -np.inf], np.nan)
        df = df.where(pd.notnull(df), None)
        return df.to_dict(orient="records")
    except Exception as e:
        return []
    finally:
        conn.close()

@app.get("/sync-from-excel")
def sync_from_excel():
    """从 goods_data.xlsx 重新加载数据到 DB"""
    try:
        if os.path.exists(EXCEL_PATH):
            df = pd.read_excel(EXCEL_PATH)
            conn = sqlite3.connect(DB_PATH)
            df.to_sql("goods", conn, if_exists="replace", index=False)
            conn.close()
            return {"status": "success", "count": len(df)}
        return {"status": "error", "message": "Excel file not found"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

import re

# Global task status tracker
TASK_STATUS = {
    "running": False,
    "task_name": None,
    "message": "Idle",
    "progress": 0
}

def update_task_status(running: bool, name: str = None, message: str = "Idle", progress: int = 0):
    TASK_STATUS["running"] = running
    TASK_STATUS["task_name"] = name
    TASK_STATUS["message"] = message
    TASK_STATUS["progress"] = progress

def run_process_with_logging(cmd, cwd, log_file, task_type):
    """
    运行子进程并实时记录日志，同时解析进度
    """
    try:
        # 使用 line buffering
        with open(log_file, "w", encoding="utf-8", buffering=1) as f:
            # Windows下有时候编码需要注意，这里尝试 utf-8
            process = subprocess.Popen(
                cmd, 
                cwd=cwd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, # 将 stderr 合并到 stdout
                text=True, 
                encoding="utf-8",
                bufsize=1 # Line buffered
            )
            
            for line in process.stdout:
                f.write(line)
                # f.flush() # buffering=1 should handle this for text files usually, but explicit flush is safer
                
                # Update status
                clean_line = line.strip()
                if clean_line:
                    current_progress = TASK_STATUS.get("progress", 0)
                    
                    if task_type in ["scrape", "update"]:
                        match = re.search(r'\[(\d+)/(\d+)\]', clean_line)
                        if match:
                            try:
                                current = int(match.group(1))
                                total = int(match.group(2))
                                if total > 0:
                                    current_progress = int((current / total) * 100)
                            except:
                                pass
                    
                    update_task_status(True, task_type, clean_line, current_progress)
        
        process.wait()
        return process.returncode
        
    except Exception as e:
        update_task_status(False, None, f"Process execution error: {str(e)}", 0)
        return -1

def run_scrape_task():
    """Background task for scraping"""
    try:
        update_task_status(True, "scrape", "Starting scrape task...", 0)
        script_path = os.path.abspath("../scrape_goods.py")
        work_dir = os.path.abspath("..")
        log_path = "../task.log"
        
        returncode = run_process_with_logging(
            ["python", "-u", script_path], # -u for unbuffered python output
            work_dir, 
            log_path, 
            "scrape"
        )
        
        if returncode != 0:
            update_task_status(False, None, "Scrape failed. Check logs.", 0)
            return

        # Upsert logic
        files = glob.glob(os.path.join(work_dir, "scrape_goods_data_*.xlsx"))
        if not files:
            update_task_status(False, None, "No output file found", 0)
            return
            
        latest_file = max(files, key=os.path.getctime)
        update_task_status(True, "scrape", f"Syncing data from {os.path.basename(latest_file)}...", 99)
        
        conn = sqlite3.connect(DB_PATH)
        try:
            new_df = pd.read_excel(latest_file)
            if "ID" in new_df.columns:
                new_df["ID"] = new_df["ID"].astype(str)
            
            try:
                old_df = pd.read_sql_query("SELECT * FROM goods", conn)
                if "ID" in old_df.columns:
                    old_df["ID"] = old_df["ID"].astype(str)
            except:
                old_df = pd.DataFrame()
            
            if old_df.empty:
                final_df = new_df
            else:
                def make_key(df):
                    if "SKU" in df.columns:
                        return df["ID"].astype(str) + "_" + df["SKU"].astype(str).fillna("")
                    return df["ID"].astype(str)
                
                new_df["_key"] = make_key(new_df)
                old_df["_key"] = make_key(old_df)
                old_df_filtered = old_df[~old_df["_key"].isin(new_df["_key"])]
                final_df = pd.concat([old_df_filtered, new_df], ignore_index=True)
                if "_key" in final_df.columns:
                    final_df = final_df.drop(columns=["_key"])
            
            final_df.to_sql("goods", conn, if_exists="replace", index=False)
            update_task_status(False, None, "Scrape completed successfully", 100)
        finally:
            conn.close()
            
    except Exception as e:
        update_task_status(False, None, f"Error: {str(e)}", 0)

def run_update_task():
    """Background task for updating goods"""
    try:
        update_task_status(True, "update", "Starting update task...", 0)
        script_path = os.path.abspath("../update_goods.py")
        work_dir = os.path.abspath("..")
        log_path = "../scrape.log" # Reusing same log file or append to it
        
        # Append to log instead of overwrite for update task? 
        # But run_process_with_logging uses "w". Let's use a separate log or append mode.
        # Ideally, we should just use "w" for a fresh task log.
        
        returncode = run_process_with_logging(
            ["python", "-u", script_path], 
            work_dir, 
            log_path, 
            "update"
        )
                
        if returncode != 0:
             update_task_status(False, None, "Update failed. Check logs.", 0)
        else:
             update_task_status(False, None, "Update completed successfully", 100)
             
    except Exception as e:
        update_task_status(False, None, f"Error: {str(e)}", 0)


@app.get("/task-status")
def get_task_status():
    return TASK_STATUS

@app.post("/run-scrape")
def run_scrape(background_tasks: BackgroundTasks):
    if TASK_STATUS["running"]:
        raise HTTPException(status_code=400, detail="A task is already running")
    
    background_tasks.add_task(run_scrape_task)
    return {"status": "success", "message": "Scrape task started in background"}

@app.post("/prepare-update")
def prepare_update(items: list[dict]):
    """
    接收前端传来的商品列表（行级数据），生成 update_goods_data.xlsx
    """
    try:
        if not items:
            return {"status": "warning", "message": "No items provided"}
            
        df = pd.DataFrame(items)
        
        # 确保保存路径在项目根目录，供 update_goods.py 读取
        save_path = os.path.abspath("../update_goods_data.xlsx")
        
        # 简单的列排序优化，确保 ID 在前
        cols = list(df.columns)
        if "ID" in cols:
            cols.insert(0, cols.pop(cols.index("ID")))
        df = df[cols]
        
        df.to_excel(save_path, index=False)
        return {"status": "success", "count": len(df), "path": save_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/export-excel")
def export_excel():
    """将数据库中的数据导出为 Excel 文件并下载"""
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT * FROM goods", conn)
        conn.close()
        
        export_path = "../exported_goods.xlsx"
        df.to_excel(export_path, index=False)
        
        return FileResponse(
            export_path, 
            filename="goods_data_export.xlsx", 
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/trigger-update")
def trigger_update(background_tasks: BackgroundTasks):
    if TASK_STATUS["running"]:
        raise HTTPException(status_code=400, detail="A task is already running")
        
    background_tasks.add_task(run_update_task)
    return {"status": "success", "message": "Update task started in background"}

@app.get("/logs")
def get_logs():
    """读取最新的更新日志"""
    log_path = "../update.log"
    if os.path.exists(log_path):
        try:
            # 优先尝试 utf-8，失败则回退到 gbk
            with open(log_path, "r", encoding="utf-8") as f:
                return {"logs": f.read()}
        except UnicodeDecodeError:
            with open(log_path, "r", encoding="gbk", errors="ignore") as f:
                return {"logs": f.read()}
    return {"logs": "No logs yet"}
