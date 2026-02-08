import sys
import os
import json
import pandas as pd
import threading
import subprocess
import time
import math
import io
import uuid
import logging
import re
import locale
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
import sqlalchemy
import db

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# DB_PATH is now managed in db.py
TASK_LOG_PATH = os.path.join(BASE_DIR, "task.log")
UPDATE_SCRIPT_PATH = os.path.join(BASE_DIR, "update_goods.py")
ALIPAY_SCRIPT_PATH = os.path.join(BASE_DIR, "alipay_product_automation.py")
SCRAPE_SCRIPT_PATH = os.path.join(BASE_DIR, "scrape_goods.py")
SCRAPE_OUTPUT_FILE = os.path.join(BASE_DIR, "scrape_goods_data.json")
RENT_CURVES_PATH = os.path.join(os.path.dirname(__file__), "data", "rent_curves.json")

AUTOMATION_STATUS_FILE = os.path.join(BASE_DIR, "automation_status.json")
CAPTCHA_INPUT_FILE = os.path.join(BASE_DIR, "captcha_input.txt")
AUTOMATION_DATA_FILE = os.path.join(BASE_DIR, "automation_data.json")
UPDATE_DATA_FILE = os.path.join(BASE_DIR, "update_goods_data.json")

# Task Status Management
TASK_STATUS = {
    "running": False,
    "task_name": None,
    "message": "",
    "progress": 0,
    "pid": None,
    "updated_at": None
}

CURRENT_TASK_PROCESS = None
TASK_LOCK = threading.Lock()

logging.basicConfig(filename=TASK_LOG_PATH, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def init_db():
    db.init_tables()

def load_task_status_from_db():
    try:
        with db.get_connection() as conn:
            row = conn.execute(text("SELECT running, task_name, message, progress, pid, updated_at FROM task_status WHERE id = 1")).fetchone()
            if not row:
                return TASK_STATUS.copy()
            return {
                "running": bool(row[0]),
                "task_name": row[1],
                "message": row[2] or "",
                "progress": row[3] or 0,
                "pid": row[4],
                "updated_at": row[5]
            }
    except Exception as e:
        logging.error(f"Failed to load task status from DB: {e}")
        return TASK_STATUS.copy()

def persist_task_status(status: Dict[str, Any]):
    try:
        with db.get_connection() as conn:
            conn.execute(
                text("UPDATE task_status SET running = :running, task_name = :task_name, message = :message, progress = :progress, pid = :pid, updated_at = :updated_at WHERE id = 1"),
                {
                    "running": 1 if status["running"] else 0,
                    "task_name": status.get("task_name"),
                    "message": status.get("message"),
                    "progress": status.get("progress"),
                    "pid": status.get("pid"),
                    "updated_at": status.get("updated_at")
                }
            )
            conn.commit()
    except Exception:
        try:
            db.init_tables()
            with db.get_connection() as conn:
                conn.execute(
                    text("UPDATE task_status SET running = :running, task_name = :task_name, message = :message, progress = :progress, pid = :pid, updated_at = :updated_at WHERE id = 1"),
                    {
                        "running": 1 if status["running"] else 0,
                        "task_name": status.get("task_name"),
                        "message": status.get("message"),
                        "progress": status.get("progress"),
                        "pid": status.get("pid"),
                        "updated_at": status.get("updated_at")
                    }
                )
                conn.commit()
        except Exception:
            pass

def update_task_status(running, task_name, message, progress, pid=None):
    with TASK_LOCK:
        TASK_STATUS["running"] = running
        TASK_STATUS["task_name"] = task_name
        TASK_STATUS["message"] = message
        TASK_STATUS["progress"] = progress
        if pid is not None:
            TASK_STATUS["pid"] = pid
        TASK_STATUS["updated_at"] = datetime.utcnow().isoformat()
        try:
            persist_task_status(TASK_STATUS)
        except Exception:
            pass

def run_process_with_logging(cmd, cwd, log_file, task_type):
    global CURRENT_TASK_PROCESS
    
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"Starting command: {' '.join(cmd)}\n")
        f.write(f"Working directory: {cwd}\n")
        f.write("-" * 50 + "\n")

    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace"
        )
        
        with TASK_LOCK:
            CURRENT_TASK_PROCESS = process
            TASK_STATUS["pid"] = process.pid
            TASK_STATUS["updated_at"] = datetime.utcnow().isoformat()
            persist_task_status(TASK_STATUS)

        with open(log_file, "a", encoding="utf-8") as f:
            for line in process.stdout:
                f.write(line)
                f.flush()
                line_text = line.strip()
                if task_type in ["scrape", "scrape_partial"]:
                    match = re.search(r"\[(\d+)\s*/\s*(\d+)\]", line_text)
                    if match:
                        processed = int(match.group(1))
                        total = int(match.group(2))
                        progress = int(processed / total * 100) if total > 0 else 0
                        update_task_status(True, task_type, line_text, progress)
                    elif line_text:
                        update_task_status(True, task_type, line_text, TASK_STATUS.get("progress", 0))
                elif line_text:
                    update_task_status(True, task_type, line_text, TASK_STATUS.get("progress", 0))
        
        process.wait()
        returncode = process.returncode
        if returncode == 0:
            update_task_status(False, task_type, "Task completed", 100)
        else:
            update_task_status(False, task_type, f"Task failed with return code {returncode}", 100)
        with TASK_LOCK:
            CURRENT_TASK_PROCESS = None
        return returncode
    except Exception as e:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\nError executing process: {e}\n")
        
        update_task_status(False, task_type, f"Error: {e}", 0)
        with TASK_LOCK:
            CURRENT_TASK_PROCESS = None
        return -1

@app.on_event("startup")
async def startup_event():
    try:
        logging.info("Initializing database...")
        init_db()
        logging.info("Database initialized successfully.")
    except Exception as e:
        logging.error(f"Database initialization failed: {e}")

@app.exception_handler(HTTPException)
def http_exception_handler(request: Request, exc: HTTPException):
    message = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail, ensure_ascii=False)
    return JSONResponse(status_code=exc.status_code, content={"status": "error", "message": message})

@app.exception_handler(Exception)
def unhandled_exception_handler(request: Request, exc: Exception):
    logging.exception("Unhandled error")
    return JSONResponse(status_code=500, content={"status": "error", "message": str(exc)})

# --- Goods Endpoints ---

@app.get("/goods")
def get_goods(
    page: int = 1,
    limit: int = 50,
    all_data: bool = False,
    merchant: Optional[str] = None,
    sync_status: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_desc: bool = False,
    page_size: Optional[int] = None
):
    if page_size is not None:
        limit = page_size
    if limit <= 0:
        limit = 50
    
    try:
        params = {}
        where_clauses = []
        if search:
            where_clauses.append("(\"商品名称\" LIKE :search OR \"SKU\" LIKE :search OR \"ID\" LIKE :search)")
            params["search"] = f"%{search}%"
        if merchant and merchant != "all":
            where_clauses.append("(\"merchant\" = :merchant OR \"商家\" = :merchant)")
            params["merchant"] = merchant
        if sync_status and sync_status != "all":
            where_clauses.append("\"是否同步支付宝\" = :sync_status")
            params["sync_status"] = sync_status
        where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        with db.get_connection() as conn:
            inspector = sqlalchemy.inspect(conn)
            if not inspector.has_table("goods"):
                return {"data": [], "total": 0, "page": page, "limit": limit, "total_pages": 0}

            total_row = conn.execute(text(f"SELECT COUNT(DISTINCT \"ID\") FROM goods{where_sql}"), params).fetchone()
            total = total_row[0] if total_row else 0
            if total == 0:
                return {"data": [], "total": 0, "page": page, "limit": limit, "total_pages": 0}

            order = "DESC" if sort_desc else "ASC"
            sort_field = (sort_by or "").strip()
            
            sort_expr = ""
            if sort_field == "ID" or not sort_field:
                if db.is_postgres():
                    sort_expr = "CASE WHEN \"ID\" ~ '^[0-9]+' THEN CAST(\"ID\" AS INTEGER) ELSE NULL END"
                else:
                    sort_expr = "CASE WHEN \"ID\" GLOB '[0-9]*' THEN CAST(\"ID\" AS INTEGER) ELSE NULL END"
            elif sort_field == "商品名称":
                sort_expr = "MIN(\"商品名称\")"
            elif sort_field == "1天租金":
                sort_expr = "MIN(CASE WHEN NULLIF(\"1天租金\", '') IS NULL THEN NULL ELSE CAST(\"1天租金\" AS REAL) END)"
            elif sort_field == "支付宝编码":
                sort_expr = "MIN(\"支付宝编码\")"
            elif sort_field == "最近提交时间":
                sort_expr = "MIN(NULLIF(\"最近提交时间\", ''))"
            elif sort_field == "merchant":
                sort_expr = "MIN(\"merchant\")"
            else:
                if db.is_postgres():
                    sort_expr = "CASE WHEN \"ID\" ~ '^[0-9]+' THEN CAST(\"ID\" AS INTEGER) ELSE NULL END"
                else:
                    sort_expr = "CASE WHEN \"ID\" GLOB '[0-9]*' THEN CAST(\"ID\" AS INTEGER) ELSE NULL END"

            id_query = f"""
                SELECT \"ID\", {sort_expr} AS sort_value
                FROM goods
                {where_sql}
                GROUP BY \"ID\"
                ORDER BY (sort_value IS NULL) ASC, sort_value {order}, \"ID\" {order}
            """
            
            id_params = params.copy()
            if not all_data:
                offset = max(page - 1, 0) * limit
                id_query += " LIMIT :limit OFFSET :offset"
                id_params["limit"] = limit
                id_params["offset"] = offset

            id_rows = conn.execute(text(id_query), id_params).fetchall()
            ids = [str(row[0]) for row in id_rows]
            if not ids:
                return {"data": [], "total": 0, "page": page, "limit": limit, "total_pages": 0}

            # Handle IN clause with parameters manually to avoid list binding issues across drivers
            # Or better, use pandas read_sql which handles it if we pass params correctly?
            # Actually constructing the IN clause safely is better for cross-db
            placeholders = ",".join([f":id_{i}" for i in range(len(ids))])
            in_params = {f"id_{i}": id_val for i, id_val in enumerate(ids)}
            # We don't need other params here since we are selecting by ID only
            
            df = pd.read_sql_query(
                text(f"SELECT * FROM goods WHERE \"ID\" IN ({placeholders})"),
                conn,
                params=in_params
            )
            df = df.fillna("")
            if df.empty:
                return {"data": [], "total": 0, "page": page, "limit": limit, "total_pages": 0}

            df["ID"] = df["ID"].astype(str)
            groups_map = {}
            for goods_id, group_df in df.groupby("ID"):
                first_row = group_df.iloc[0].to_dict()
                inventory_series = pd.to_numeric(group_df.get("库存", pd.Series([], dtype="object")), errors="coerce").fillna(0)
                total_inventory = int(inventory_series.sum()) if not inventory_series.empty else 0
                merchant_value = first_row.get("merchant") or first_row.get("商家") or ""
                group_data = {
                    "ID": goods_id,
                    "商品名称": first_row.get("商品名称", ""),
                    "短标题": first_row.get("短标题", ""),
                    "1级分类": first_row.get("1级分类", ""),
                    "2级分类": first_row.get("2级分类", ""),
                    "3级分类": first_row.get("3级分类", ""),
                    "merchant": merchant_value,
                    "是否同步支付宝": first_row.get("是否同步支付宝", ""),
                    "最近提交时间": first_row.get("最近提交时间", ""),
                    "商品图片": first_row.get("商品图片", ""),
                    "支付宝编码": first_row.get("支付宝编码", ""),
                    "库存": total_inventory,
                    "skus": group_df.to_dict(orient="records")
                }
                groups_map[goods_id] = group_data

            groups = [groups_map[gid] for gid in ids if gid in groups_map]
            total_pages = math.ceil(total / limit) if limit else 1
            return {"data": groups, "total": total, "page": page, "limit": limit, "total_pages": total_pages}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class UpdateFieldRequest(BaseModel):
    field: str
    value: Any

@app.post("/goods/{id}/field")
def update_goods_field(id: str, req: UpdateFieldRequest):
    try:
        ALLOWED_FIELDS = ["支付宝编码", "商品名称", "merchant", "商家", "是否同步支付宝"]
        if req.field not in ALLOWED_FIELDS:
            raise HTTPException(status_code=400, detail=f"Field {req.field} not allowed")
            
        with db.get_connection() as conn:
            inspector = sqlalchemy.inspect(conn)
            if not inspector.has_table("goods"):
                raise HTTPException(status_code=404, detail="Item not found (Table missing)")

            # Use quotes for field name to handle potential keywords or special chars
            result = conn.execute(
                text(f"UPDATE goods SET \"{req.field}\" = :value WHERE \"ID\" = :id"),
                {"value": req.value, "id": id}
            )
            conn.commit()
            if result.rowcount == 0:
                 raise HTTPException(status_code=404, detail="Item not found")
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class UpdateMerchantRequest(BaseModel):
    merchant: str

@app.post("/goods/{id}/merchant")
def update_goods_merchant(id: str, req: UpdateMerchantRequest):
    with db.get_connection() as conn:
        inspector = sqlalchemy.inspect(conn)
        if not inspector.has_table("goods"):
            raise HTTPException(status_code=404, detail="Item not found (Table missing)")

        result = conn.execute(
            text("UPDATE goods SET \"merchant\" = :merchant, \"商家\" = :merchant WHERE \"ID\" = :id"),
            {"merchant": req.merchant, "id": id}
        )
        conn.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Item not found")
    return {"status": "success"}

@app.delete("/goods/{id}")
def delete_goods(id: str):
    with db.get_connection() as conn:
        inspector = sqlalchemy.inspect(conn)
        if not inspector.has_table("goods"):
            raise HTTPException(status_code=404, detail="Item not found (Table missing)")

        result = conn.execute(text("DELETE FROM goods WHERE \"ID\" = :id"), {"id": id})
        conn.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Item not found")
    return {"status": "success"}

# --- Task Management Endpoints ---

@app.get("/task-status")
def get_task_status():
    status = load_task_status_from_db()
    # Check if process is still running
    if status["running"] and status["pid"]:
        try:
            # Check if PID exists (Windows)
            # Use tasklist filter
            output = subprocess.check_output(f"tasklist /FI \"PID eq {status['pid']}\"", shell=True).decode()
            if str(status["pid"]) not in output:
                # Process died
                status["running"] = False
                status["message"] = "Process terminated unexpectedly"
                persist_task_status(status)
        except:
             pass
    return status

@app.get("/logs")
def get_logs():
    if os.path.exists(TASK_LOG_PATH):
        try:
            with open(TASK_LOG_PATH, "r", encoding="utf-8") as f:
                return {"logs": f.read()}
        except:
            return {"logs": "Error reading logs"}
    return {"logs": "No logs yet"}

@app.post("/stop-task")
def stop_task():
    global CURRENT_TASK_PROCESS
    has_process = False
    with TASK_LOCK:
        if CURRENT_TASK_PROCESS:
            CURRENT_TASK_PROCESS.terminate()
            has_process = True
    if has_process:
        update_task_status(False, TASK_STATUS.get("task_name"), "Task stopped by user", TASK_STATUS.get("progress", 0))
        return {"status": "success", "message": "Task stopped"}
    return {"status": "error", "message": "No running task"}

class ConfigUpdateRequest(BaseModel):
    key: str
    value: str

def get_config_map():
    with db.get_connection() as conn:
        rows = conn.execute(text("SELECT key, value FROM config")).fetchall()
        data = {row[0]: row[1] for row in rows}
        defaults = {
            "filter_keywords": "已出租,下架,不可租",
            "default_merchant_filter": "all"
        }
        for k, v in defaults.items():
            data.setdefault(k, v)
        return data

@app.get("/config")
def get_config():
    return get_config_map()

@app.post("/config")
def update_config(req: ConfigUpdateRequest):
    db.upsert_config(req.key, req.value)
    return {"status": "success"}

def read_rent_curves() -> List[Dict[str, Any]]:
    if not os.path.exists(RENT_CURVES_PATH):
        return []
    with open(RENT_CURVES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        if isinstance(data, list):
            return data
        return []

def write_rent_curves(curves: List[Dict[str, Any]]):
    os.makedirs(os.path.dirname(RENT_CURVES_PATH), exist_ok=True)
    with open(RENT_CURVES_PATH, "w", encoding="utf-8") as f:
        json.dump(curves, f, ensure_ascii=False, indent=2)

@app.get("/rent-curves")
def get_rent_curves():
    return read_rent_curves()

@app.post("/rent-curves")
def save_rent_curve(curve: Dict[str, Any] = Body(...)):
    curves = read_rent_curves()
    curve_id = curve.get("id") or str(uuid.uuid4())
    curve["id"] = curve_id
    if "created_at" not in curve or not curve["created_at"]:
        curve["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existing_idx = next((i for i, c in enumerate(curves) if c.get("id") == curve_id or c.get("name") == curve.get("name")), None)
    if existing_idx is not None:
        curves[existing_idx] = {**curves[existing_idx], **curve}
    else:
        curves.append(curve)
    write_rent_curves(curves)
    return {"status": "success", "id": curve_id}

@app.delete("/rent-curves/{id_or_name}")
def delete_rent_curve(id_or_name: str):
    curves = read_rent_curves()
    filtered = [c for c in curves if c.get("id") != id_or_name and c.get("name") != id_or_name]
    if len(filtered) == len(curves):
        raise HTTPException(status_code=404, detail="Curve not found")
    write_rent_curves(filtered)
    return {"status": "success"}

@app.get("/debug/info")
def get_debug_info():
    db_url = os.getenv("DATABASE_URL", "")
    masked_url = "sqlite" if not db_url else db_url
    if "://" in db_url:
        try:
            scheme, rest = db_url.split("://", 1)
            if "@" in rest:
                auth, host = rest.split("@", 1)
                masked_url = f"{scheme}://***@{host}"
            else:
                masked_url = f"{scheme}://{rest}"
        except:
            masked_url = "invalid_url_format"
            
    goods_count = 0
    table_exists = False
    table_names = []
    current_database = None
    try:
        with db.get_connection() as conn:
            inspector = sqlalchemy.inspect(conn)
            table_names = inspector.get_table_names()
            table_exists = inspector.has_table("goods")
            if table_exists:
                result = conn.execute(text("SELECT COUNT(*) FROM goods")).fetchone()
                goods_count = result[0] if result else 0
            if db.is_postgres():
                db_row = conn.execute(text("SELECT current_database()")).fetchone()
                current_database = db_row[0] if db_row else None
    except Exception as e:
        goods_count = f"Error: {str(e)}"

    scrape_file_exists = os.path.exists(SCRAPE_OUTPUT_FILE)
    scrape_file_size = os.stat(SCRAPE_OUTPUT_FILE).st_size if scrape_file_exists else 0
    
    return {
        "database_url_masked": masked_url,
        "is_postgres": db.is_postgres(),
        "goods_table_exists": table_exists,
        "goods_count": goods_count,
        "table_names": table_names,
        "current_database": current_database,
        "scrape_file_path": SCRAPE_OUTPUT_FILE,
        "scrape_file_exists": scrape_file_exists,
        "scrape_file_size": scrape_file_size,
        "cwd": os.getcwd(),
        "base_dir": BASE_DIR,
        "env_database_url_present": bool(db_url)
    }

def merge_scraped_data(scrape_path: str) -> int:
    if not os.path.exists(scrape_path):
        raise HTTPException(status_code=400, detail="Scrape data file not found")
    
    logging.info(f"Starting merge from {scrape_path}")
    
    with open(scrape_path, "r", encoding="utf-8") as f:
        items = json.load(f)
    if not items:
        logging.info("No items in scrape file")
        return 0
    df = pd.DataFrame(items).fillna("")
    if "ID" not in df.columns:
        raise HTTPException(status_code=400, detail="Scrape data missing ID")
    df["ID"] = df["ID"].astype(str)
    ids = df["ID"].unique().tolist()
    
    logging.info(f"Found {len(ids)} unique items to merge")

    with db.get_connection() as conn:
        # Check if table exists
        inspector = sqlalchemy.inspect(conn)
        if not inspector.has_table("goods"):
            logging.info("Creating goods table")
            df.to_sql("goods", conn, if_exists="append", index=False)
            return len(ids)

        logging.info("Updating existing records")
        placeholders = ",".join([f":id_{i}" for i in range(len(ids))])
        params = {f"id_{i}": id_val for i, id_val in enumerate(ids)}
        
        existing_df = pd.read_sql_query(
            text(f"SELECT \"ID\", \"merchant\", \"商家\", \"支付宝编码\", \"是否同步支付宝\" FROM goods WHERE \"ID\" IN ({placeholders})"),
            conn,
            params=params
        )
        existing_map = {}
        for _, row in existing_df.fillna("").iterrows():
            existing_map[str(row["ID"])] = row.to_dict()

        for field in ["merchant", "商家", "支付宝编码", "是否同步支付宝"]:
            if field not in df.columns:
                df[field] = ""
            existing_values = {k: v.get(field, "") for k, v in existing_map.items()}
            df[field] = df[field].replace("", pd.NA)
            df[field] = df[field].fillna(df["ID"].map(existing_values)).fillna("")

        # Ensure columns exist
        db.ensure_columns("goods", df.columns.tolist())
        
        # Delete old records
        conn.execute(text(f"DELETE FROM goods WHERE \"ID\" IN ({placeholders})"), params)
        
        # Insert new records
        # Use chunksize to avoid parameter limit issues if many rows
        df.to_sql("goods", conn, if_exists="append", index=False, chunksize=500)
        conn.commit()
    return len(ids)

@app.post("/run-scrape")
def run_scrape():
    if TASK_STATUS["running"]:
        return {"status": "error", "message": "Task already running"}
    update_task_status(True, "scrape", "Starting scrape...", 0)
    cmd = [sys.executable, "-u", SCRAPE_SCRIPT_PATH]

    def task_thread():
        returncode = run_process_with_logging(cmd, BASE_DIR, TASK_LOG_PATH, "scrape")
        if returncode != 0:
            return
        try:
            updated = merge_scraped_data(SCRAPE_OUTPUT_FILE)
            update_task_status(False, "scrape", f"Scrape completed, updated {updated} goods", 100)
        except Exception as e:
            update_task_status(False, "scrape", f"Scrape completed, merge failed: {e}", 100)

    thread = threading.Thread(target=task_thread)
    thread.start()
    return {"status": "success", "message": "Scrape started"}

class PartialScrapeRequest(BaseModel):
    ids: List[str]

@app.post("/run-scrape-partial")
def run_partial_scrape(req: PartialScrapeRequest):
    if TASK_STATUS["running"]:
        return {"status": "error", "message": "Task already running"}
    clean_ids = [i.strip() for i in req.ids if i and i.strip()]
    if not clean_ids:
        raise HTTPException(status_code=400, detail="No IDs provided")
    update_task_status(True, "scrape_partial", "Starting partial scrape...", 0)
    cmd = [sys.executable, "-u", SCRAPE_SCRIPT_PATH, "--target-ids", ",".join(clean_ids)]

    def task_thread():
        returncode = run_process_with_logging(cmd, BASE_DIR, TASK_LOG_PATH, "scrape_partial")
        if returncode != 0:
            return
        try:
            updated = merge_scraped_data(SCRAPE_OUTPUT_FILE)
            update_task_status(False, "scrape_partial", f"Partial scrape completed, updated {updated} goods", 100)
        except Exception as e:
            update_task_status(False, "scrape_partial", f"Partial scrape completed, merge failed: {e}", 100)

    thread = threading.Thread(target=task_thread)
    thread.start()
    return {"status": "success", "message": "Partial scrape started"}

@app.get("/export-excel")
def export_excel(
    merchant: Optional[str] = None,
    sync_status: Optional[str] = None,
    search: Optional[str] = None
):
    try:
        params = {}
        where_clauses = []
        if search:
            where_clauses.append("(\"商品名称\" LIKE :search OR \"SKU\" LIKE :search OR \"ID\" LIKE :search)")
            params["search"] = f"%{search}%"
        if merchant and merchant != "all":
            where_clauses.append("(\"merchant\" = :merchant OR \"商家\" = :merchant)")
            params["merchant"] = merchant
        if sync_status and sync_status != "all":
            where_clauses.append("\"是否同步支付宝\" = :sync_status")
            params["sync_status"] = sync_status
        where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        with db.get_connection() as conn:
            inspector = sqlalchemy.inspect(conn)
            if not inspector.has_table("goods"):
                df = pd.DataFrame()
            else:
                df = pd.read_sql_query(text(f"SELECT * FROM goods{where_sql} ORDER BY \"ID\" DESC"), conn, params=params)
        
        df = df.fillna("")
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="goods")
        output.seek(0)
        filename = f"goods_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))

# --- Update Automation Endpoints ---

class PrepareUpdateRequest(BaseModel):
    items: List[Dict[str, Any]]

@app.post("/prepare-update")
def prepare_update(req: PrepareUpdateRequest):
    if not req.items:
        raise HTTPException(status_code=400, detail="No items provided")
    
    try:
        with open(UPDATE_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(req.items, f, ensure_ascii=False)
        return {"status": "success", "message": "Data prepared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/trigger-update")
def trigger_update():
    if TASK_STATUS["running"]:
        return {"status": "error", "message": "Task already running"}
        
    update_task_status(True, "update", "Starting update...", 0)
    
    cmd = [sys.executable, "-u", UPDATE_SCRIPT_PATH, UPDATE_DATA_FILE]
    
    def task_thread():
        run_process_with_logging(cmd, BASE_DIR, TASK_LOG_PATH, "update")
        
    thread = threading.Thread(target=task_thread)
    thread.start()
    
    return {"status": "success", "message": "Update started"}

# --- Alipay Automation Endpoints ---

class AutomationRequest(BaseModel):
    ids: List[str]
    phone: Optional[str] = ""

@app.post("/automation/alipay/update")
def start_alipay_update(req: AutomationRequest):
    if TASK_STATUS["running"]:
        return {"status": "error", "message": "Task already running"}
    if not req.ids:
        return {"status": "error", "message": "No IDs provided"}
        
    # 1. Prepare Data
    try:
        with db.get_connection() as conn:
            inspector = sqlalchemy.inspect(conn)
            if not inspector.has_table("goods"):
                 raise Exception("Table 'goods' not found. Please scrape data first.")

            placeholders = ",".join([f":id_{i}" for i in range(len(req.ids))])
            params = {f"id_{i}": id_val for i, id_val in enumerate(req.ids)}
            
            query = f"SELECT \"ID\", \"支付宝编码\" FROM goods WHERE \"ID\" IN ({placeholders})"
            df = pd.read_sql_query(text(query), conn, params=params)
        
        items = []
        for _, row in df.iterrows():
            items.append({
                "id": str(row["ID"]),
                "alipay_code": str(row["支付宝编码"])
            })
            
        with open(AUTOMATION_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False)
            
    except Exception as e:
        return {"status": "error", "message": f"Database error: {e}"}
        
    # 2. Reset Status
    if os.path.exists(AUTOMATION_STATUS_FILE):
        try: os.remove(AUTOMATION_STATUS_FILE)
        except: pass
        
    if os.path.exists(CAPTCHA_INPUT_FILE):
        try: os.remove(CAPTCHA_INPUT_FILE)
        except: pass
        
    initial_status = {
        "status": "running",
        "message": "Starting Alipay Automation...",
        "timestamp": time.time(),
        "total": len(items),
        "processed": 0,
        "success_count": 0,
        "error_count": 0,
        "current_id": "",
        "current_code": "",
        "step": "init"
    }
    try:
        with open(AUTOMATION_STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(initial_status, f, ensure_ascii=False)
    except:
        pass

    update_task_status(True, "alipay_update", "Starting Alipay Automation...", 0)
    
    # 3. Start Process
    cmd = [sys.executable, "-u", ALIPAY_SCRIPT_PATH, "--data", AUTOMATION_DATA_FILE]
    if req.phone:
        cmd.extend(["--phone", req.phone])
        
    def task_thread():
        run_process_with_logging(cmd, BASE_DIR, TASK_LOG_PATH, "alipay_update")
        
    thread = threading.Thread(target=task_thread)
    thread.start()
    
    return {"status": "success", "message": "Automation started"}

@app.get("/automation/status")
def get_automation_status():
    if os.path.exists(AUTOMATION_STATUS_FILE):
        try:
            with open(AUTOMATION_STATUS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    
    return {
        "status": "running" if TASK_STATUS["running"] else "idle",
        "message": TASK_STATUS["message"],
        "total": 0,
        "processed": 0,
        "success_count": 0,
        "error_count": 0
    }

class CaptchaInput(BaseModel):
    code: str

@app.post("/automation/captcha")
def submit_captcha(input: CaptchaInput):
    try:
        with open(CAPTCHA_INPUT_FILE, "w", encoding="utf-8") as f:
            f.write(input.code)
        return {"status": "success", "message": "Captcha submitted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
