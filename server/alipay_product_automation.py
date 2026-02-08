import time
import random
import datetime
import os
import re
import json
import argparse
import sys
from playwright.sync_api import sync_playwright

# --- 配置区域 ---
STATUS_FILE = "automation_status.json"
CAPTCHA_INPUT_FILE = "captcha_input.txt"
DATA_FILE = "automation_data.json" # Input data file

ALIPAY_HOME_URL = os.getenv("ALIPAY_HOME_URL", "https://b.alipay.com/page/portal/home")
GOODS_LIST_URL = os.getenv("ALIPAY_GOODS_LIST_URL", "https://b.alipay.com/page/commerce/goods/list?appId=2021005181665859&itemSubType=RENT&itemType=NORMAL_ITEM")
USER_DATA_DIR = os.getenv("ALIPAY_USER_DATA_DIR", os.path.join(os.getcwd(), "alipay_user_data"))

# 待填写的文本内容 (保持原有逻辑)
SERVICE_INTRO = ""
PROTECTION_SCOPE = ""
DISCLAIMER = ""
CLAIM_PROCESS = ""

def parse_selectors(env_value, defaults):
    if env_value:
        parts = [p.strip() for p in re.split(r"\s*\|\|\s*|\s*;\s*|\s*,\s*", env_value) if p.strip()]
        if parts:
            return parts
    return defaults

LOGIN_BUTTON_SELECTORS = parse_selectors(
    os.getenv("ALIPAY_LOGIN_BUTTON_SELECTORS", ""),
    [
        "#bportal > div > div.header___nV0_x.bportalcomponents-header.undefined > div.portalTechWarp___Zh8Rp.hasEnoughWidth___SHnHo > div.headerRight___qCNXo.portalTech___IpIba > a",
        "a:has-text('登录')",
        "a:has-text('登录/注册')"
    ]
)
SMS_TAB_SELECTORS = parse_selectors(
    os.getenv("ALIPAY_SMS_TAB_SELECTORS", ""),
    ["#J-loginMethod-tabs > li:nth-child(2)", "li:has-text('短信')", "li:has-text('验证码')"]
)
PHONE_INPUT_SELECTORS = parse_selectors(
    os.getenv("ALIPAY_PHONE_INPUT_SELECTORS", ""),
    ["#J-input-user", "input[name='loginId']", "input[type='text']"]
)
SMS_INPUT_SELECTORS = parse_selectors(
    os.getenv("ALIPAY_SMS_INPUT_SELECTORS", ""),
    ["#J-input-sms", "input[name='smsCode']", "input[type='tel']"]
)
GET_CODE_SELECTORS = parse_selectors(
    os.getenv("ALIPAY_GET_CODE_SELECTORS", ""),
    ["#J-verifyCode", "button:has-text('获取验证码')", "a:has-text('获取验证码')"]
)
SUBMIT_SELECTORS = parse_selectors(
    os.getenv("ALIPAY_SUBMIT_SELECTORS", ""),
    ["button:has-text('登录')", "button:has-text('确定')", "button:has-text('提交')"]
)

def wait_for_any(page, selectors, timeout=10000):
    per = max(1000, int(timeout / max(len(selectors), 1)))
    for sel in selectors:
        try:
            locator = page.locator(sel).first
            locator.wait_for(state="visible", timeout=per)
            return locator
        except:
            continue
    return None

def safe_click(locator):
    try:
        locator.click()
        return True
    except:
        return False

def log_status(status, message, needed_data=None):
    """Write status to file for frontend to poll"""
    data = {
        "status": status,
        "message": message,
        "timestamp": time.time()
    }
    if needed_data:
        data.update(needed_data)
    
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"[{status}] {message}")

def get_timestamp_str():
    return datetime.datetime.now().strftime("%Y%m%d%H%M%S")

def wait_for_captcha(total=0, processed=0, success_count=0, error_count=0, current_id="", current_code=""):
    """Wait for captcha code from file"""
    log_status("waiting_for_captcha", "请输入短信验证码", {
        "total": total,
        "processed": processed,
        "success_count": success_count,
        "error_count": error_count,
        "current_id": current_id,
        "current_code": current_code,
        "step": "captcha"
    })
    
    # Remove old input file if exists
    if os.path.exists(CAPTCHA_INPUT_FILE):
        try:
            os.remove(CAPTCHA_INPUT_FILE)
        except:
            pass
            
    print("等待验证码输入...")
    while True:
        if os.path.exists(CAPTCHA_INPUT_FILE):
            try:
                with open(CAPTCHA_INPUT_FILE, "r", encoding="utf-8") as f:
                    code = f.read().strip()
                if code:
                    print(f"获取到验证码: {code}")
                    return code
            except:
                pass
        time.sleep(1)

def perform_login(page, phone_number, total=0, processed=0, success_count=0, error_count=0):
    print(f"访问首页: {ALIPAY_HOME_URL}")
    page.goto(ALIPAY_HOME_URL)
    
    # Check if already logged in (look for some element that indicates login)
    # But user requested specific flow, so we try to follow it if not logged in.
    
    try:
        print("尝试点击登录按钮...")
        login_btn = wait_for_any(page, LOGIN_BUTTON_SELECTORS, timeout=5000)
        if login_btn:
            safe_click(login_btn)
        else:
            print("未找到首页登录按钮，可能已跳转或布局变更，尝试直接检测登录状态...")
    except Exception as e:
        print(f"点击登录按钮异常: {e}")

    # Wait for login page elements
    # Click Captcha Login Tab: #J-loginMethod-tabs > li:nth-child(2)
    try:
        print("等待登录方式选项卡...")
        # Check if we are on a login page
        # Sometimes it opens a popup or redirects.
        # Wait for the tab to appear.
        tab = wait_for_any(page, SMS_TAB_SELECTORS, timeout=10000)
        if tab:
            print("点击短信登录选项卡...")
            safe_click(tab)
            
            print(f"输入手机号: {phone_number}")
            phone_input = wait_for_any(page, PHONE_INPUT_SELECTORS, timeout=8000)
            if phone_input:
                phone_input.fill(phone_number)
            else:
                raise Exception("手机号输入框未找到")
            
            print("点击验证码输入框...")
            sms_input = wait_for_any(page, SMS_INPUT_SELECTORS, timeout=8000)
            if sms_input:
                safe_click(sms_input)
            else:
                raise Exception("验证码输入框未找到")
            
            print("点击获取验证码...")
            get_code_btn = wait_for_any(page, GET_CODE_SELECTORS, timeout=8000)
            if get_code_btn:
                safe_click(get_code_btn)
            else:
                raise Exception("获取验证码按钮未找到")
            
            code = wait_for_captcha(total, processed, success_count, error_count)
            
            print("输入验证码...")
            sms_input = wait_for_any(page, SMS_INPUT_SELECTORS, timeout=8000)
            if sms_input:
                sms_input.fill(code)
            else:
                raise Exception("验证码输入框未找到")
            
            print("尝试提交登录...")
            submit_btn = wait_for_any(page, SUBMIT_SELECTORS, timeout=8000)
            if submit_btn:
                safe_click(submit_btn)
            else:
                try:
                    sms_input.press("Enter")
                except:
                    pass
                
            page.wait_for_load_state("networkidle")
            
        else:
            print("未检测到登录选项卡，可能已登录或页面不同。")
            
    except Exception as e:
        print(f"登录流程异常: {e}")
        print("请手动完成登录...")

def ensure_goods_list_page(page):
    """Ensure we are on the goods list page"""
    if GOODS_LIST_URL not in page.url:
        print("跳转到商品列表页...")
        page.goto(GOODS_LIST_URL)
        try:
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_selector(".merchant-ui-table", timeout=15000)
        except:
            print("等待商品列表表格超时，可能需要手动介入...")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", help="Path to JSON data file", default=DATA_FILE)
    parser.add_argument("--phone", help="Phone number for login", default="")
    args = parser.parse_args()
    
    # Load data
    target_items = []
    if os.path.exists(args.data):
        with open(args.data, "r", encoding="utf-8") as f:
            target_items = json.load(f)
    else:
        print(f"数据文件 {args.data} 不存在")
        return

    total_items = len(target_items)
    processed_count = 0
    success_count = 0
    error_count = 0
    print(f"待处理条目数: {total_items}")
    log_status("running", "启动浏览器...", {
        "total": total_items,
        "processed": processed_count,
        "success_count": success_count,
        "error_count": error_count,
        "step": "launch"
    })

    with sync_playwright() as p:
        # Launch browser (Headful as requested)
        if not os.path.exists(USER_DATA_DIR):
            os.makedirs(USER_DATA_DIR)
            
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False, # User requested headed mode
            args=["--start-maximized"],
            no_viewport=True
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        
        # Login Flow
        if args.phone:
            log_status("running", "执行登录流程...", {
                "total": total_items,
                "processed": processed_count,
                "success_count": success_count,
                "error_count": error_count,
                "step": "login"
            })
            perform_login(page, args.phone, total_items, processed_count, success_count, error_count)
        else:
            log_status("running", "跳过自动登录(未提供手机号)，请手动登录...", {
                "total": total_items,
                "processed": processed_count,
                "success_count": success_count,
                "error_count": error_count,
                "step": "login"
            })
            page.goto(ALIPAY_HOME_URL)

        # Wait for Goods List
        log_status("running", "进入商品列表...", {
            "total": total_items,
            "processed": processed_count,
            "success_count": success_count,
            "error_count": error_count,
            "step": "list"
        })
        ensure_goods_list_page(page)
        
        # Process Items
        for item in target_items:
            target_id = str(item.get("id"))
            alipay_code = str(item.get("alipay_code", "")).strip()
            
            if not alipay_code:
                print(f"跳过 ID {target_id}: 无支付宝编码")
                error_count += 1
                processed_count += 1
                log_status("running", f"跳过 ID {target_id}: 无支付宝编码", {
                    "total": total_items,
                    "processed": processed_count,
                    "success_count": success_count,
                    "error_count": error_count,
                    "current_id": target_id,
                    "current_code": alipay_code,
                    "step": "skip"
                })
                continue
                
            log_status("running", f"正在处理 ID {target_id} (支付宝编码: {alipay_code})", {
                "total": total_items,
                "processed": processed_count,
                "success_count": success_count,
                "error_count": error_count,
                "current_id": target_id,
                "current_code": alipay_code,
                "step": "search"
            })
            print(f"\n--- 处理 ID {target_id} ---")
            
            # Reset to list page for each item to be safe
            ensure_goods_list_page(page)
            
            # Search logic (Reuse existing but adapted)
            found_row = find_row_by_merchant_code(page, alipay_code)
            
            if found_row:
                print("找到匹配行，准备编辑...")
                try:
                    # Click Edit
                    # Assuming "Edit" is in the "More" dropdown or visible
                    # User request: "点击编辑"
                    # Try to find "编辑" button directly or in dropdown
                    
                    # Strategy: Check for "编辑" link/button in the row
                    edit_btn = found_row.locator("a:has-text('编辑')").first
                    if edit_btn.is_visible():
                        edit_btn.click()
                    else:
                        more_btn = found_row.locator("td:nth-child(8) a").first
                        if more_btn.is_visible():
                            more_btn.click()
                            page.wait_for_selector(".ant-dropdown:not(.ant-dropdown-hidden)", timeout=5000)
                            page.locator(".ant-dropdown-menu-item:has-text('编辑')").click()
                    
                    # Handle Edit Page
                    # Wait for page navigation
                    page.wait_for_load_state("domcontentloaded")
                    handle_update_page(page, item)
                    success_count += 1
                    processed_count += 1
                    log_status("running", f"已更新 ID {target_id}", {
                        "total": total_items,
                        "processed": processed_count,
                        "success_count": success_count,
                        "error_count": error_count,
                        "current_id": target_id,
                        "current_code": alipay_code,
                        "step": "updated"
                    })
                    
                except Exception as e:
                    print(f"编辑操作失败: {e}")
                    error_count += 1
                    processed_count += 1
                    log_status("running", f"编辑失败 ID {target_id}: {e}", {
                        "total": total_items,
                        "processed": processed_count,
                        "success_count": success_count,
                        "error_count": error_count,
                        "current_id": target_id,
                        "current_code": alipay_code,
                        "step": "error"
                    })
            else:
                print(f"未找到商家侧编码为 {alipay_code} 的商品")
                error_count += 1
                processed_count += 1
                log_status("running", f"未找到 ID {target_id} (编码 {alipay_code})", {
                    "total": total_items,
                    "processed": processed_count,
                    "success_count": success_count,
                    "error_count": error_count,
                    "current_id": target_id,
                    "current_code": alipay_code,
                    "step": "not_found"
                })

        log_status("finished", f"任务完成，成功 {success_count}，失败 {error_count}，已处理 {processed_count} 个商品", {
            "total": total_items,
            "processed": processed_count,
            "success_count": success_count,
            "error_count": error_count,
            "step": "finished"
        })
        # Keep open for a bit or close? User said "development... convenient to observe"
        # We'll wait a few seconds then close, or better, wait for user to stop it via API if we were loop.
        # But this is a script run. Let's just finish.
        time.sleep(5)
        context.close()

def get_row_code_text(row):
    selectors = [
        ".goodsPart___GoH9Y span",
        "td:nth-child(2) span",
        "td:nth-child(2)"
    ]
    for sel in selectors:
        loc = row.locator(sel)
        if loc.count() == 0:
            continue
        if sel == ".goodsPart___GoH9Y span" and loc.count() > 2:
            text = loc.nth(2).inner_text().strip()
        else:
            text = loc.first.inner_text().strip()
        if text:
            return text
    return ""

def find_row_by_merchant_code(page, target_code):
    """Find row where merchant code matches target_code"""
    while True:
        try:
            page.wait_for_selector(".merchant-ui-table table tbody tr", timeout=10000)
        except:
            return None
        rows = page.locator(".merchant-ui-table table tbody tr").all()
        
        for row in rows:
            try:
                code_text = get_row_code_text(row)
                
                if target_code == code_text:
                    print(f"Found match: {code_text}")
                    return row
                else:
                    pass
            except:
                continue
        
        next_li = page.locator("li.ant-pagination-next").first
        if next_li.count() > 0:
            class_attr = next_li.get_attribute("class") or ""
            aria_disabled = next_li.get_attribute("aria-disabled")
            if "ant-pagination-disabled" not in class_attr and aria_disabled != "true":
                next_btn = next_li.locator("button")
                if next_btn.is_visible():
                    next_btn.click()
                    page.wait_for_timeout(1500)
                    continue
        break
    return None

def handle_update_page(page, item):
    """Update info on the edit page"""
    print("进入编辑页面，开始更新信息...")
    try:
        page.wait_for_selector("#formContainerWrap", timeout=15000)
    except:
        pass
        
    time.sleep(2)
    
    try:
        print("更新租期规则和免押金...")
        page.locator("#rent_duration_cal_rule label").nth(1).click() 
        page.locator("#whether_support_free_deposit label").nth(0).click()
    except Exception as e:
        print(f"设置租期/免押金失败: {e}")

    print("更新增值服务内容...")
    fill_textarea(page, "#value_added_services_0_service_introduction", SERVICE_INTRO)
    fill_textarea(page, "#value_added_services_0_protection_scope", PROTECTION_SCOPE)
    fill_textarea(page, "#value_added_services_0_disclaimer", DISCLAIMER)
    fill_textarea(page, "#value_added_services_0_claim_process", CLAIM_PROCESS)
    
    try:
        print("勾选服务选项...")
        card3 = page.locator("div.goodsContainer___wtXQp form > div").nth(2)
        checkboxes = card3.locator(".ant-checkbox-wrapper:not(.ant-checkbox-wrapper-checked)").all()
        for cb in checkboxes:
            cb.click()
            time.sleep(0.05)
    except Exception as e:
        print(f"勾选选项失败: {e}")

    print("提交更新...")
    try:
        footer = page.locator("div.footer___wSqtX")
        submit_btn = footer.locator("button").last
        submit_btn.click()
        page.wait_for_timeout(3000)
    except Exception as e:
        print(f"提交失败: {e}")

def fill_textarea(page, selector, value):
    try:
        page.fill(selector, value)
    except:
        pass

if __name__ == "__main__":
    main()
