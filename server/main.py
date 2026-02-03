from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import pandas as pd
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
        # Replace NaN with None (which becomes null in JSON) to avoid JSON errors
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

# Global task status tracker
TASK_STATUS = {
    "running": False,
    "task_name": None,
    "message": "Idle"
}

def update_task_status(running: bool, name: str = None, message: str = "Idle"):
    TASK_STATUS["running"] = running
    TASK_STATUS["task_name"] = name
    TASK_STATUS["message"] = message

def run_scrape_task():
    """Background task for scraping"""
    try:
        update_task_status(True, "scrape", "Scraping data...")
        script_path = os.path.abspath("../scrape_goods.py")
        work_dir = os.path.abspath("..")
        
        result = subprocess.run(
            ["python", script_path], 
            cwd=work_dir, 
            capture_output=True, 
            text=True,
            encoding="utf-8"
        )
        
        # Log handling
        with open("../scrape.log", "w", encoding="utf-8") as f:
            f.write(result.stdout)
            if result.stderr:
                f.write("\n=== STDERR ===\n")
                f.write(result.stderr)
        
        if result.returncode != 0:
            update_task_status(False, None, f"Scrape failed: {result.stderr[:50]}")
            return

        # Upsert logic
        files = glob.glob(os.path.join(work_dir, "scrape_goods_data_*.xlsx"))
        if not files:
            update_task_status(False, None, "No output file found")
            return
            
        latest_file = max(files, key=os.path.getctime)
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
            update_task_status(False, None, "Scrape completed successfully")
        finally:
            conn.close()
            
    except Exception as e:
        update_task_status(False, None, f"Error: {str(e)}")

def run_update_task():
    """Background task for updating goods"""
    try:
        update_task_status(True, "update", "Updating goods...")
        script_path = os.path.abspath("../update_goods.py")
        work_dir = os.path.abspath("..")
        
        result = subprocess.run(
            ["python", script_path], 
            cwd=work_dir, 
            capture_output=True, 
            text=True,
            encoding="utf-8"
        )
        
        # Append logs
        with open("../scrape.log", "a", encoding="utf-8") as f:
            f.write("\n\n=== UPDATE TASK ===\n")
            f.write(result.stdout)
            if result.stderr:
                f.write("\n=== STDERR ===\n")
                f.write(result.stderr)
                
        if result.returncode != 0:
             update_task_status(False, None, f"Update failed: {result.stderr[:50]}")
        else:
             update_task_status(False, None, "Update completed successfully")
             
    except Exception as e:
        update_task_status(False, None, f"Error: {str(e)}")

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
