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
import sys

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

    # Ensure config table exists
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS config 
                 (key text PRIMARY KEY, value text)''')
    conn.commit()
    conn.close()

    # Ensure merchant column exists
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("SELECT merchant FROM goods LIMIT 1")
    except sqlite3.OperationalError:
        print("Adding merchant column...")
        try:
            c.execute("ALTER TABLE goods ADD COLUMN merchant TEXT DEFAULT '米奇'")
            # Update any existing rows that might be null (though DEFAULT handles new ones)
            c.execute("UPDATE goods SET merchant = '米奇' WHERE merchant IS NULL OR merchant = ''")
            conn.commit()
        except Exception as e:
            print(f"Error adding merchant column: {e}")
            
    # Ensure 支付宝编码 column exists
    try:
        c.execute("SELECT 支付宝编码 FROM goods LIMIT 1")
    except sqlite3.OperationalError:
        print("Adding 支付宝编码 column...")
        try:
            c.execute("ALTER TABLE goods ADD COLUMN 支付宝编码 TEXT DEFAULT ''")
            conn.commit()
        except Exception as e:
            print(f"Error adding 支付宝编码 column: {e}")

    finally:
        conn.close()

# Rent Curve Storage
RENT_CURVES_FILE = "./data/rent_curves.json"

import uuid
from datetime import datetime

class RentCurve(BaseModel):
    id: Optional[str] = None
    name: str
    source_sku: Optional[str] = None
    source_name: Optional[str] = None
    created_at: Optional[str] = None
    multipliers: dict  # day -> multiplier (e.g. "3": 0.9)

@app.get("/rent-curves")
def get_rent_curves():
    if not os.path.exists(RENT_CURVES_FILE):
        return []
    try:
        with open(RENT_CURVES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading rent curves: {e}")
        return []

@app.post("/rent-curves")
def save_rent_curve(curve: RentCurve):
    curves = get_rent_curves()
    
    # If id is provided, update existing
    if curve.id:
        updated = False
        for i, c in enumerate(curves):
            if c.get("id") == curve.id:
                # Update fields
                c["name"] = curve.name
                c["multipliers"] = curve.multipliers
                # Keep original creation info if not provided
                if not c.get("source_sku") and curve.source_sku:
                    c["source_sku"] = curve.source_sku
                # Update source_name if provided
                if curve.source_name:
                    c["source_name"] = curve.source_name
                
                updated = True
                break
        if not updated:
            # ID provided but not found, treat as new (or error? treat as new for now)
            curve_dict = curve.dict()
            if not curve_dict.get("created_at"):
                curve_dict["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            curves.append(curve_dict)
    else:
        # No ID, create new
        curve_dict = curve.dict()
        curve_dict["id"] = str(uuid.uuid4())
        curve_dict["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        curves.append(curve_dict)
    
    os.makedirs(os.path.dirname(RENT_CURVES_FILE), exist_ok=True)
    with open(RENT_CURVES_FILE, "w", encoding="utf-8") as f:
        json.dump(curves, f, ensure_ascii=False, indent=2)
    
    return {"status": "success", "message": f"Saved curve {curve.name}"}

@app.delete("/rent-curves/{id_or_name}")
def delete_rent_curve(id_or_name: str):
    curves = get_rent_curves()
    # Try to match by ID first, then Name
    new_curves = [c for c in curves if c.get("id") != id_or_name and c.get("name") != id_or_name]
    
    if len(curves) == len(new_curves):
        raise HTTPException(status_code=404, detail="Curve not found")
    
    with open(RENT_CURVES_FILE, "w", encoding="utf-8") as f:
        json.dump(new_curves, f, ensure_ascii=False, indent=2)
    return {"status": "success", "message": f"Deleted curve {id_or_name}"}

init_db()

class MerchantUpdate(BaseModel):
    merchant: str

class FieldUpdate(BaseModel):
    field: str
    value: str

@app.post("/goods/{id}/field")
def update_goods_field(id: str, update: FieldUpdate):
    # Allowed fields for security
    ALLOWED_FIELDS = ["支付宝编码", "merchant"]
    if update.field not in ALLOWED_FIELDS:
        raise HTTPException(status_code=400, detail=f"Field {update.field} is not allowed to be updated directly")

    conn = sqlite3.connect(DB_PATH)
    try:
        c = conn.cursor()
        query = f"UPDATE goods SET {update.field} = ? WHERE ID = ?"
        c.execute(query, (update.value, id))
        conn.commit()
        return {"status": "success", "message": f"Updated {update.field} for ID {id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.post("/goods/{id}/merchant")
def update_merchant(id: str, update: MerchantUpdate):
    # Backward compatibility or convenience
    return update_goods_field(id, FieldUpdate(field="merchant", value=update.merchant))

class ConfigItem(BaseModel):
    key: str
    value: str

@app.get("/config")
def get_config():
    conn = sqlite3.connect(DB_PATH)
    try:
        # Check if table exists (it should, but just in case of old DB file)
        # Actually init_db handles it.
        # But if we want to be safe against errors if table is empty
        try:
            df = pd.read_sql_query("SELECT * FROM config", conn)
            if df.empty:
                return {}
            return df.set_index("key")["value"].to_dict()
        except:
            return {}
    finally:
        conn.close()

@app.post("/config")
def update_config(item: ConfigItem):
    conn = sqlite3.connect(DB_PATH)
    try:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (item.key, item.value))
        conn.commit()
        return {"status": "success", "key": item.key, "value": item.value}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/")
def read_root():
    return {"message": "Goods Manager API"}

@app.get("/goods")
def get_goods(page: int = 1, limit: int = 50, all_data: bool = False, merchant: Optional[str] = None, sync_status: Optional[str] = None):
    conn = sqlite3.connect(DB_PATH)
    try:
        # 1. Get total unique IDs count
        cursor = conn.cursor()
        
        base_query = "SELECT COUNT(DISTINCT ID) FROM goods"
        params = []
        where_clauses = []
        
        if merchant:
            where_clauses.append("merchant = ?")
            params.append(merchant)
        
        if sync_status and sync_status != "all":
            if sync_status == "已同步":
                where_clauses.append("是否同步支付宝 = '已同步'")
            else:
                where_clauses.append("(是否同步支付宝 IS NULL OR 是否同步支付宝 != '已同步')")
            
        if where_clauses:
            base_query += " WHERE " + " AND ".join(where_clauses)
            
        cursor.execute(base_query, params)
        total_ids = cursor.fetchone()[0]

        # 2. Get IDs for current page
        if not all_data:
            offset = (page - 1) * limit
            query_ids = "SELECT DISTINCT ID FROM goods"
            query_params = []
            
            if where_clauses:
                query_ids += " WHERE " + " AND ".join(where_clauses)
                query_params.extend(params)
                
            query_ids += " ORDER BY ID DESC LIMIT ? OFFSET ?"
            query_params.extend([limit, offset])
            
            ids_df = pd.read_sql_query(query_ids, conn, params=query_params)
            page_ids = ids_df["ID"].tolist()
        else:
            query_ids = "SELECT DISTINCT ID FROM goods"
            query_params = []
            
            if where_clauses:
                query_ids += " WHERE " + " AND ".join(where_clauses)
                query_params.extend(params)
                
            query_ids += " ORDER BY ID DESC"
            
            ids_df = pd.read_sql_query(query_ids, conn, params=query_params)
            page_ids = ids_df["ID"].tolist()

        if not page_ids:
             return {
                "data": [],
                "total": total_ids,
                "page": page,
                "limit": limit,
                "total_pages": (total_ids + limit - 1) // limit if limit > 0 else 1
            }

        # 3. Get all data rows for these IDs
        # Use parameterized query to avoid SQL injection
        placeholders = ",".join(["?"] * len(page_ids))
        query_data = f"SELECT * FROM goods WHERE ID IN ({placeholders})"
        df = pd.read_sql_query(query_data, conn, params=page_ids)
        
        # Handle NaN/Inf
        df = df.replace([np.inf, -np.inf], np.nan)
        df = df.fillna("")

        # 4. Group data by ID
        result_data = []
        # Ensure we iterate in the order of page_ids (to maintain sort order)
        for gid in page_ids:
            # Filter rows for this ID
            # Note: ID in DB is text, make sure types match. 
            # pandas might infer types, so safer to compare as string if needed, 
            # but usually it's fine if read_sql_query preserved types.
            # Let's force string comparison just in case.
            g_rows = df[df["ID"].astype(str) == str(gid)]
            
            if g_rows.empty:
                continue
                
            first_row = g_rows.iloc[0]
            
            # Extract common fields (Base Info)
            base_info = {
                "ID": str(gid),
                "商品名称": first_row.get("商品名称", ""),
                "短标题": first_row.get("短标题", ""),
                "1级分类": first_row.get("1级分类", ""),
                "2级分类": first_row.get("2级分类", ""),
                "3级分类": first_row.get("3级分类", ""),
                "merchant": first_row.get("merchant", "米奇"),
                "是否同步支付宝": first_row.get("是否同步支付宝", ""),
            }
            
            # Extract SKU list
            skus = g_rows.to_dict(orient="records")
            
            # Calculate total stock for the group
            total_stock = 0
            for sku in skus:
                try:
                    s = int(sku.get("库存", 0))
                    total_stock += s
                except:
                    pass
            base_info["库存"] = total_stock # Aggregate stock
            
            # Add skus to base info or as a separate field? 
            # User wants to expand. Let's put skus in a "skus" field.
            base_info["skus"] = skus
            
            result_data.append(base_info)
        
        return {
            "data": result_data,
            "total": total_ids,
            "page": page,
            "limit": limit,
            "total_pages": (total_ids + limit - 1) // limit if limit > 0 else 1
        }
    except Exception as e:
        print(f"Error fetching goods: {e}")
        import traceback
        traceback.print_exc()
        return {"data": [], "total": 0, "page": page, "limit": limit, "total_pages": 0}
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

# Global process tracker for aborting
CURRENT_TASK_PROCESS = None

def update_task_status(running: bool, name: str = None, message: str = "Idle", progress: int = 0):
    TASK_STATUS["running"] = running
    TASK_STATUS["task_name"] = name
    TASK_STATUS["message"] = message
    TASK_STATUS["progress"] = progress

def run_process_with_logging(cmd, cwd, log_file, task_type):
    """
    运行子进程并实时记录日志，同时解析进度
    """
    global CURRENT_TASK_PROCESS
    print(f"Executing command: {cmd} in {cwd}")
    try:
        # 准备环境变量，强制 UTF-8 输出
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        # 使用 line buffering
        with open(log_file, "w", encoding="utf-8", buffering=1) as f:
            f.write(f"Starting command: {' '.join(cmd)}\n")
            f.write(f"Working directory: {cwd}\n")
            f.write("-" * 50 + "\n")
            
            # Windows下有时候编码需要注意，这里尝试 utf-8
            process = subprocess.Popen(
                cmd, 
                cwd=cwd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, # 将 stderr 合并到 stdout
                text=True, 
                encoding="utf-8",
                bufsize=1, # Line buffered
                env=env
            )
            
            CURRENT_TASK_PROCESS = process
            
            try:
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
                # Handle case where process might be killed externally or iteration fails
                print(f"Process loop exception: {e}")
                return -1
            finally:
                CURRENT_TASK_PROCESS = None
        
    except Exception as e:
        update_task_status(False, None, f"Process execution error: {str(e)}", 0)
        return -1

@app.post("/stop-task")
def stop_task():
    global CURRENT_TASK_PROCESS
    if CURRENT_TASK_PROCESS:
        try:
            # Try terminate first
            CURRENT_TASK_PROCESS.terminate()
            # Wait a bit?
            # On Windows terminate() is usually enough or acts like kill
            update_task_status(False, None, "Task aborted by user", 0)
            CURRENT_TASK_PROCESS = None
            return {"status": "success", "message": "Task stopped"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to stop task: {e}")
    else:
        # Check if task status says running but no process (inconsistent state cleanup)
        if TASK_STATUS["running"]:
             update_task_status(False, None, "Task state reset (no process found)", 0)
             return {"status": "success", "message": "Task state reset"}
        return {"status": "warning", "message": "No running task found"}

def run_scrape_task(target_ids: List[str] = None):
    """Background task for scraping"""
    try:
        task_msg = "Starting scrape task..."
        if target_ids:
            task_msg = f"Starting partial scrape for {len(target_ids)} items..."
            
        update_task_status(True, "scrape", task_msg, 0)
        script_path = os.path.abspath("../scrape_goods.py")
        work_dir = os.path.abspath("..")
        log_path = os.path.abspath("../task.log")
        
        cmd = [sys.executable, "-u", script_path]
        if target_ids:
            ids_str = ",".join(target_ids)
            cmd.extend(["--target-ids", ids_str])
        
        returncode = run_process_with_logging(
            cmd, # -u for unbuffered python output
            work_dir, 
            log_path, 
            "scrape"
        )
        
        if returncode != 0:
            update_task_status(False, None, "Scrape failed. Check logs.", 0)
            return

        # Upsert logic
        def log_to_file(msg):
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[System] {msg}\n")

        # Look for JSON files now
        files = glob.glob(os.path.join(work_dir, "scrape_goods_data_*.json"))
        if not files:
            msg = "No output file found in " + work_dir
            log_to_file(msg)
            update_task_status(False, None, msg, 0)
            return
            
        latest_file = max(files, key=os.path.getctime)
        
        # Check if file is recent (within 10 minutes)
        import time
        if time.time() - os.path.getctime(latest_file) > 600:
             msg = f"Latest file {latest_file} is too old (>10 mins). Scrape likely produced no data."
             log_to_file(msg)
             update_task_status(False, None, msg, 0)
             return

        log_to_file(f"Found latest data file: {latest_file}")
        
        update_task_status(True, "scrape", f"Syncing data from {os.path.basename(latest_file)}...", 99)
        
        conn = sqlite3.connect(DB_PATH)
        try:
            # Read JSON
            new_df = pd.read_json(latest_file)
            log_to_file(f"Loaded {len(new_df)} rows from JSON.")
            
            # Clean column names
            new_df.columns = [c.strip() for c in new_df.columns]
            
            # Ensure ID is string
            if "ID" in new_df.columns:
                new_df["ID"] = new_df["ID"].astype(str)
            
            try:
                old_df = pd.read_sql_query("SELECT * FROM goods", conn)
                if "ID" in old_df.columns:
                    old_df["ID"] = old_df["ID"].astype(str)
                log_to_file(f"Loaded {len(old_df)} existing rows from Database.")
            except:
                old_df = pd.DataFrame()
                log_to_file("Database is empty or table not found.")
            
            # Preserve merchant info from old_df
            merchant_map = {}
            if not old_df.empty and "merchant" in old_df.columns:
                try:
                    # Create a map from ID to merchant (taking the first value for each ID)
                    temp_df = old_df[["ID", "merchant"]].drop_duplicates(subset=["ID"])
                    merchant_map = temp_df.set_index("ID")["merchant"].to_dict()
                except Exception as e:
                    log_to_file(f"Warning: Failed to create merchant map: {e}")

            # Preserve 支付宝编码 info from old_df
            alipay_map = {}
            if not old_df.empty and "支付宝编码" in old_df.columns:
                try:
                    temp_df = old_df[["ID", "支付宝编码"]].drop_duplicates(subset=["ID"])
                    alipay_map = temp_df.set_index("ID")["支付宝编码"].to_dict()
                except Exception as e:
                    log_to_file(f"Warning: Failed to create alipay_map: {e}")

            if old_df.empty:
                final_df = new_df
                # Default new data
                if "merchant" not in final_df.columns:
                     final_df["merchant"] = "米奇"
                if "支付宝编码" not in final_df.columns:
                     final_df["支付宝编码"] = ""
            else:
                # Apply merchant map to new_df
                if "merchant" not in new_df.columns:
                    new_df["merchant"] = new_df["ID"].map(merchant_map).fillna("米奇")
                
                # Apply alipay_map to new_df (since scrape usually doesn't get this manual field)
                # But if scrape DOES get it (in future), we might want to respect it?
                # For now, scrape doesn't get it, so we restore it from DB
                if "支付宝编码" not in new_df.columns:
                     new_df["支付宝编码"] = new_df["ID"].map(alipay_map).fillna("")
                else:
                     # If scrape has it, maybe we should prefer DB if scrape returns empty?
                     # But typically manual fields are NOT in scrape source.
                     pass

                # Preserve '是否同步支付宝' if new data says '未知' (which happens in partial scrape)
                if "是否同步支付宝" in new_df.columns and "是否同步支付宝" in old_df.columns:
                    status_map = old_df[["ID", "是否同步支付宝"]].drop_duplicates(subset=["ID"]).set_index("ID")["是否同步支付宝"].to_dict()
                    # Apply map where new value is '未知'
                    mask = new_df["是否同步支付宝"] == "未知"
                    # Map and fill missing (new IDs) with '未知'
                    restored = new_df.loc[mask, "ID"].map(status_map).fillna("未知")
                    new_df.loc[mask, "是否同步支付宝"] = restored

                def make_key(df):
                    # 如果有 SKU 列，则 ID+SKU 为唯一键
                    if "SKU" in df.columns:
                        return df["ID"].astype(str) + "_" + df["SKU"].astype(str).fillna("")
                    return df["ID"].astype(str)
                
                # 标记新数据的 Key
                new_df["_key"] = make_key(new_df)
                old_df["_key"] = make_key(old_df)
                
                # 找出旧数据中，不在新数据里的行（保留旧数据中未被更新的部分？）
                # 逻辑：全量同步模式下，通常以新数据为准。
                # 但为了保留可能手动修改的字段（如果不在抓取范围内），这里需要谨慎。
                # 目前逻辑是：保留 old_df 中 _key 不在 new_df 的行，加上 new_df 的所有行。
                
                old_df_filtered = old_df[~old_df["_key"].isin(new_df["_key"])]
                final_df = pd.concat([old_df_filtered, new_df], ignore_index=True)
                
                if "_key" in final_df.columns:
                    final_df = final_df.drop(columns=["_key"])
            
            final_df.to_sql("goods", conn, if_exists="replace", index=False)
            log_to_file(f"Database updated. Total rows: {len(final_df)}")
            
            update_task_status(False, None, "Scrape completed successfully", 100)
        except Exception as e:
            err_msg = f"Database sync error: {str(e)}"
            log_to_file(err_msg)
            print(err_msg)
            update_task_status(False, None, err_msg, 0)
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
        log_path = os.path.abspath("../task.log")
        data_file_path = os.path.abspath("../update_goods_data.json")
        
        # Unified log file
        
        returncode = run_process_with_logging(
            [sys.executable, "-u", script_path, data_file_path], 
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
    # Check DB last modified time
    last_updated = None
    if os.path.exists(DB_PATH):
        mtime = os.path.getmtime(DB_PATH)
        # Format: YYYY-MM-DD HH:mm:ss
        import datetime
        last_updated = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
    
    response = TASK_STATUS.copy()
    response["last_updated"] = last_updated
    return response

@app.post("/run-scrape")
def run_scrape(background_tasks: BackgroundTasks):
    if TASK_STATUS["running"]:
        raise HTTPException(status_code=400, detail="A task is already running")
    
    background_tasks.add_task(run_scrape_task)
    return {"status": "success", "message": "Scrape task started in background"}

class ScrapeRequest(BaseModel):
    ids: List[str]

@app.post("/run-scrape-partial")
def run_scrape_partial(req: ScrapeRequest, background_tasks: BackgroundTasks):
    if TASK_STATUS["running"]:
        raise HTTPException(status_code=400, detail="A task is already running")
    
    background_tasks.add_task(run_scrape_task, req.ids)
    return {"status": "success", "message": f"Partial scrape task started for {len(req.ids)} items"}

@app.delete("/goods/{id}")
def delete_goods(id: str):
    conn = sqlite3.connect(DB_PATH)
    try:
        c = conn.cursor()
        c.execute("DELETE FROM goods WHERE ID = ?", (id,))
        conn.commit()
        if c.rowcount == 0:
             raise HTTPException(status_code=404, detail="Goods not found")
        return {"status": "success", "message": f"Deleted goods {id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.post("/prepare-update")
def prepare_update(items: list[dict]):
    """
    接收前端传来的商品列表（行级数据），更新数据库并生成 update_goods_data.json
    """
    try:
        if not items:
            raise HTTPException(status_code=400, detail="No items provided for update")
            
        new_items_df = pd.DataFrame(items)
        
        # 1. Update Local Database
        conn = sqlite3.connect(DB_PATH)
        try:
            # Read all existing data
            # Note: This simple approach reads everything. For larger datasets, use SQL UPDATE.
            # But since columns are dynamic/Chinese, DataFrame merge is easier to maintain consistency with scrape logic.
            old_df = pd.read_sql_query("SELECT * FROM goods", conn)
            
            # Create a composite key for matching
            def make_key(df):
                if "SKU" in df.columns:
                    return df["ID"].astype(str) + "_" + df["SKU"].astype(str).fillna("")
                return df["ID"].astype(str)

            # Ensure ID is string in both
            if "ID" in new_items_df.columns:
                new_items_df["ID"] = new_items_df["ID"].astype(str)
            if "ID" in old_df.columns:
                old_df["ID"] = old_df["ID"].astype(str)
                
            new_items_df["_key"] = make_key(new_items_df)
            old_df["_key"] = make_key(old_df)
            
            # Remove rows from old_df that are present in new_items_df (based on key)
            # This is effectively an UPSERT for the provided rows
            old_df_filtered = old_df[~old_df["_key"].isin(new_items_df["_key"])]
            
            # Concat
            final_df = pd.concat([old_df_filtered, new_items_df], ignore_index=True)
            
            if "_key" in final_df.columns:
                final_df = final_df.drop(columns=["_key"])
            
            final_df.to_sql("goods", conn, if_exists="replace", index=False)
            print(f"Database updated with {len(new_items_df)} modified rows.")
            
        finally:
            conn.close()

        # 2. Write to JSON for update_goods.py
        # The update script needs to know which items to update on the remote site.
        # We pass the items directly via a JSON file.
        json_path = os.path.abspath("../update_goods_data.json")
        # orient='records' creates a list of dicts: [{"col1": val1, ...}, ...]
        # force_ascii=False ensures Chinese characters are readable
        new_items_df.to_json(json_path, orient="records", force_ascii=False, indent=2)
        print(f"Generated update data file: {json_path}")

        return {"status": "success", "message": "Data prepared and saved to database"}
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
    log_path = os.path.abspath("../task.log")
    if os.path.exists(log_path):
        try:
            # 优先尝试 utf-8，失败则回退到 gbk
            with open(log_path, "r", encoding="utf-8") as f:
                return {"logs": f.read()}
        except UnicodeDecodeError:
            with open(log_path, "r", encoding="gbk", errors="ignore") as f:
                return {"logs": f.read()}
    return {"logs": "No logs yet"}
