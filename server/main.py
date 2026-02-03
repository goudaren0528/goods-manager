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
    # Replace NaN with None for JSON compatibility
    df = df.where(pd.notnull(df), None)
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

@app.post("/run-scrape")
def run_scrape():
    """
    运行 scrape_goods.py 抓取数据，并 Upsert 到数据库
    """
    import subprocess
    import glob
    
    try:
        # 1. 运行抓取脚本
        script_path = os.path.abspath("../scrape_goods.py")
        work_dir = os.path.abspath("..")
        
        # 使用 subprocess.run 阻塞等待完成，因为我们需要立刻读取结果
        # 注意：抓取可能耗时较长，生产环境应使用异步任务队列 (Celery/RQ)
        # 这里为了简单闭环，我们先用阻塞，前端会有 Loading 状态
        result = subprocess.run(
            ["python", script_path], 
            cwd=work_dir, 
            capture_output=True, 
            text=True,
            encoding="utf-8"  # 尝试 utf-8
        )
        
        # 记录日志
        with open("../scrape.log", "w", encoding="utf-8") as f:
            f.write(result.stdout)
            if result.stderr:
                f.write("\n=== STDERR ===\n")
                f.write(result.stderr)
        
        if result.returncode != 0:
             raise HTTPException(status_code=500, detail=f"Scraping script failed. Check logs. Stderr: {result.stderr[:200]}")

        # 2. 找到最新的 scrape_goods_data_*.xlsx
        files = glob.glob(os.path.join(work_dir, "scrape_goods_data_*.xlsx"))
        if not files:
            return {"status": "warning", "message": "Script ran but no output file found."}
            
        latest_file = max(files, key=os.path.getctime)
        
        # 3. 读取 Excel 并 Upsert 到 SQLite
        # 逻辑：读取 DB -> 读取 Excel -> Merge (Excel 覆盖 DB) -> Write DB
        conn = sqlite3.connect(DB_PATH)
        
        try:
            # 读取新数据
            new_df = pd.read_excel(latest_file)
            # 确保 ID 是字符串
            if "ID" in new_df.columns:
                new_df["ID"] = new_df["ID"].astype(str)
            
            # 读取旧数据
            try:
                old_df = pd.read_sql_query("SELECT * FROM goods", conn)
                if "ID" in old_df.columns:
                    old_df["ID"] = old_df["ID"].astype(str)
            except:
                # 表可能不存在
                old_df = pd.DataFrame()
            
            if old_df.empty:
                final_df = new_df
            else:
                # Upsert 逻辑
                # 假设 ID + SKU 是唯一键。
                # 如果没有 SKU 列，仅用 ID。
                # 为了通用性，我们构造一个 unique_key
                
                def make_key(df):
                    if "SKU" in df.columns:
                        return df["ID"].astype(str) + "_" + df["SKU"].astype(str).fillna("")
                    return df["ID"].astype(str)
                
                # 设置索引以便更新
                new_df["_key"] = make_key(new_df)
                old_df["_key"] = make_key(old_df)
                
                # 过滤掉 old_df 中那些 key 在 new_df 里已经存在的行 (我们要用新的覆盖旧的)
                old_df_filtered = old_df[~old_df["_key"].isin(new_df["_key"])]
                
                # 合并
                final_df = pd.concat([old_df_filtered, new_df], ignore_index=True)
                
                # 移除临时 key
                if "_key" in final_df.columns:
                    final_df = final_df.drop(columns=["_key"])
            
            # 写入 DB (Replace 模式)
            final_df.to_sql("goods", conn, if_exists="replace", index=False)
            
            return {"status": "success", "message": f"Synced {len(new_df)} records from {os.path.basename(latest_file)}"}
            
        finally:
            conn.close()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
