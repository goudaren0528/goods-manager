
class AutomationRequest(BaseModel):
    ids: List[str]
    phone: Optional[str] = ""

AUTOMATION_STATUS_FILE = "automation_status.json"
CAPTCHA_INPUT_FILE = "captcha_input.txt"
AUTOMATION_DATA_FILE = "automation_data.json"

@app.post("/automation/alipay/update")
def start_alipay_update(req: AutomationRequest):
    global CURRENT_TASK_PROCESS
    
    if TASK_STATUS["running"]:
        return {"status": "error", "message": "Task already running"}
        
    # 1. Prepare Data
    conn = sqlite3.connect(DB_PATH)
    try:
        placeholders = ",".join(["?"] * len(req.ids))
        query = f"SELECT ID, 支付宝编码 FROM goods WHERE ID IN ({placeholders})"
        df = pd.read_sql_query(query, conn, params=req.ids)
        
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
    finally:
        conn.close()
        
    # 2. Reset Status
    if os.path.exists(AUTOMATION_STATUS_FILE):
        try:
            os.remove(AUTOMATION_STATUS_FILE)
        except: pass
        
    if os.path.exists(CAPTCHA_INPUT_FILE):
        try:
            os.remove(CAPTCHA_INPUT_FILE)
        except: pass
        
    update_task_status(True, "alipay_update", "Starting Alipay Automation...", 0)
    
    # 3. Start Process
    script_path = os.path.abspath("../alipay_product_automation.py")
    work_dir = os.path.abspath("..")
    log_path = os.path.abspath("../task.log")
    
    cmd = [sys.executable, "-u", script_path, "--data", AUTOMATION_DATA_FILE]
    if req.phone:
        cmd.extend(["--phone", req.phone])
        
    # Run in background without waiting (using Popen inside the helper effectively)
    # But run_process_with_logging waits. We need to run it in a thread or background task.
    # Since we want to support status polling via file (which the script does),
    # we can just launch it.
    # However, run_process_with_logging is designed to block and capture output.
    # Let's use BackgroundTasks or Threading.
    
    import threading
    def task_thread():
        run_process_with_logging(cmd, work_dir, log_path, "alipay_update")
        
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
    
    # Fallback to global task status if specific file not found
    return {
        "status": "running" if TASK_STATUS["running"] else "idle",
        "message": TASK_STATUS["message"]
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
