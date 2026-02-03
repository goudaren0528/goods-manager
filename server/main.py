from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import pandas as pd
import sqlite3
from typing import List, Optional, Any
import os
import shutil
import json

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
    # 动态读取所有列
    df = pd.read_sql_query("SELECT * FROM goods", conn)
    conn.close()
    return df.to_dict(orient="records")

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

class UpdateRequest(BaseModel):
    items: List[dict] # 包含要更新的行数据

@app.post("/prepare-update")
def prepare_update(data: UpdateRequest):
    """
    接收前端编辑的数据，写入 update_goods_data.xlsx，
    供 update_goods.py 使用
    """
    try:
        if not data.items:
            return {"status": "empty"}
            
        df = pd.DataFrame(data.items)
        # 写入 Excel
        df.to_excel(UPDATE_EXCEL_PATH, index=False)
        return {"status": "success", "file": UPDATE_EXCEL_PATH}
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
def trigger_update():
    """
    调用 update_goods.py 执行自动化更新
    """
    import subprocess
    try:
        # 异步或同步调用脚本
        # 这里为了演示简单，使用 Popen
        # 注意：生产环境建议使用 Celery 或 RQ
        # 脚本路径需要绝对路径或相对路径正确
        script_path = os.path.abspath("../update_goods.py")
        work_dir = os.path.abspath("..")
        
        # 简单起见，我们假设这是阻塞调用，或者让它在后台跑
        # 为了能看到输出，可以重定向 stdout
        log_file = open("../update.log", "w")
        subprocess.Popen(["python", script_path], cwd=work_dir, stdout=log_file, stderr=log_file)
        
        return {"status": "started", "log_file": "update.log"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
