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

ALIPAY_HOME_URL = "https://b.alipay.com/page/portal/home"
GOODS_LIST_URL = "https://b.alipay.com/page/commerce/goods/list?appId=2021005181665859&itemSubType=RENT&itemType=NORMAL_ITEM"
USER_DATA_DIR = os.path.join(os.getcwd(), "alipay_user_data")

# 待填写的文本内容 (保持原有逻辑)
SERVICE_INTRO = ""
PROTECTION_SCOPE = ""
DISCLAIMER = ""
CLAIM_PROCESS = ""

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

def wait_for_captcha():
    """Wait for captcha code from file"""
    log_status("waiting_for_captcha", "请输入短信验证码")
    
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

def perform_login(page, phone_number):
    print(f"访问首页: {ALIPAY_HOME_URL}")
    page.goto(ALIPAY_HOME_URL)
    
    # Check if already logged in (look for some element that indicates login)
    # But user requested specific flow, so we try to follow it if not logged in.
    
    try:
        # Click Login Button
        # Selector provided: #bportal > div > div.header___nV0_x.bportalcomponents-header.undefined > div.portalTechWarp___Zh8Rp.hasEnoughWidth___SHnHo > div.headerRight___qCNXo.portalTech___IpIba > a
        # Simplified selector for robustness if possible, but using user's specific one first
        print("尝试点击登录按钮...")
        login_btn = page.locator("#bportal > div > div.header___nV0_x.bportalcomponents-header.undefined > div.portalTechWarp___Zh8Rp.hasEnoughWidth___SHnHo > div.headerRight___qCNXo.portalTech___IpIba > a")
        if login_btn.is_visible(timeout=5000):
            login_btn.click()
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
        tab = page.locator("#J-loginMethod-tabs > li:nth-child(2)")
        if tab.is_visible(timeout=10000):
            print("点击短信登录选项卡...")
            tab.click()
            
            # Input Phone: #J-input-user
            print(f"输入手机号: {phone_number}")
            page.fill("#J-input-user", phone_number)
            
            # Click SMS Input: #J-input-sms (Requested by user)
            print("点击验证码输入框...")
            page.click("#J-input-sms")
            
            # Click Get Code: #J-verifyCode
            print("点击获取验证码...")
            page.click("#J-verifyCode")
            
            # Wait for Captcha from user
            code = wait_for_captcha()
            
            # Input Captcha: #J-input-sms
            print("输入验证码...")
            page.fill("#J-input-sms", code)
            
            # Click Login/Submit
            # User didn't provide submit button selector. Usually it's a button nearby.
            # Try to find a button with "登录" text in the form
            print("尝试提交登录...")
            submit_btn = page.locator("button:has-text('登录')").first
            if submit_btn.is_visible():
                submit_btn.click()
            else:
                # Fallback: press Enter in the input
                page.press("#J-input-sms", "Enter")
                
            # Wait for navigation
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
            page.wait_for_selector(".merchant-ui-table", timeout=10000)
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

    print(f"待处理条目数: {len(target_items)}")
    log_status("running", "启动浏览器...")

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
            log_status("running", "执行登录流程...")
            perform_login(page, args.phone)
        else:
            log_status("running", "跳过自动登录(未提供手机号)，请手动登录...")
            page.goto(ALIPAY_HOME_URL)

        # Wait for Goods List
        log_status("running", "进入商品列表...")
        ensure_goods_list_page(page)
        
        # Process Items
        processed_count = 0
        for item in target_items:
            target_id = str(item.get("id"))
            alipay_code = str(item.get("alipay_code", "")).strip()
            
            if not alipay_code:
                print(f"跳过 ID {target_id}: 无支付宝编码")
                continue
                
            log_status("running", f"正在处理 ID {target_id} (支付宝编码: {alipay_code})")
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
                        # Try "More" -> "Edit"
                        more_btn = found_row.locator("td:nth-child(8) a").first # reuse existing column index assumption
                        if more_btn.is_visible():
                            more_btn.click()
                            page.wait_for_selector(".ant-dropdown:not(.ant-dropdown-hidden)", timeout=5000)
                            page.locator(".ant-dropdown-menu-item:has-text('编辑')").click()
                    
                    # Handle Edit Page
                    # Wait for page navigation
                    page.wait_for_load_state("domcontentloaded")
                    handle_update_page(page, item)
                    processed_count += 1
                    
                except Exception as e:
                    print(f"编辑操作失败: {e}")
            else:
                print(f"未找到商家侧编码为 {alipay_code} 的商品")

        log_status("finished", f"任务完成，已处理 {processed_count} 个商品")
        # Keep open for a bit or close? User said "development... convenient to observe"
        # We'll wait a few seconds then close, or better, wait for user to stop it via API if we were loop.
        # But this is a script run. Let's just finish.
        time.sleep(5)
        context.close()

def find_row_by_merchant_code(page, target_code):
    """Find row where merchant code matches target_code"""
    # Reuse pagination logic from original script
    while True:
        page.wait_for_timeout(2000)
        rows = page.locator(".merchant-ui-table table tbody tr").all()
        
        for row in rows:
            try:
                # Get merchant code text
                # Reuse selector from original script
                code_el = row.locator(".goodsPart___GoH9Y span").nth(2)
                if not code_el.count():
                     code_el = row.locator("td:nth-child(2)").first
                
                code_text = code_el.inner_text().strip()
                
                # Check for exact match (ignoring whitespace)
                # User requested: "check merchant side code = alipay code"
                if target_code == code_text:
                    print(f"Found match: {code_text}")
                    return row
                else:
                    # Debug log (optional, but helpful)
                    # print(f"Checking: {code_text} != {target_code}")
                    pass
            except:
                continue
        
        # Next page
        next_li = page.locator("li.ant-pagination-next").first
        if next_li.count() > 0:
            class_attr = next_li.get_attribute("class") or ""
            aria_disabled = next_li.get_attribute("aria-disabled")
            if "ant-pagination-disabled" not in class_attr and aria_disabled != "true":
                next_btn = next_li.locator("button")
                if next_btn.is_visible():
                    next_btn.click()
                    continue
        break
    return None

def handle_update_page(page, item):
    """Update info on the edit page"""
    print("进入编辑页面，开始更新信息...")
    # Wait for form
    try:
        page.wait_for_selector("#formContainerWrap", timeout=15000)
    except:
        # Maybe it's not #formContainerWrap in edit mode?
        pass
        
    time.sleep(2)
    
    # 1. Update Rent Rules & Deposit (Same as copy logic)
    try:
        print("更新租期规则和免押金...")
        # Check if elements exist before clicking (Edit mode might have values pre-filled)
        # Just re-click to ensure
        page.locator("#rent_duration_cal_rule label").nth(1).click() 
        page.locator("#whether_support_free_deposit label").nth(0).click()
    except Exception as e:
        print(f"设置租期/免押金失败: {e}")

    # 2. Update Value Added Services (Same as copy logic)
    print("更新增值服务内容...")
    fill_textarea(page, "#value_added_services_0_service_introduction", SERVICE_INTRO)
    fill_textarea(page, "#value_added_services_0_protection_scope", PROTECTION_SCOPE)
    fill_textarea(page, "#value_added_services_0_disclaimer", DISCLAIMER)
    fill_textarea(page, "#value_added_services_0_claim_process", CLAIM_PROCESS)
    
    # 3. Check checkboxes
    try:
        print("勾选服务选项...")
        # Need to be careful not to uncheck if already checked.
        # Logic: check if not checked, then click.
        # Reuse locator logic
        card3 = page.locator("div.goodsContainer___wtXQp form > div").nth(2)
        checkboxes = card3.locator(".ant-checkbox-wrapper:not(.ant-checkbox-wrapper-checked)").all()
        for cb in checkboxes:
            cb.click()
            time.sleep(0.05)
    except Exception as e:
        print(f"勾选选项失败: {e}")

    # 4. Submit
    print("提交更新...")
    try:
        footer = page.locator("div.footer___wSqtX")
        submit_btn = footer.locator("button").last
        submit_btn.click()
        
        # Check for success
        # Usually redirects back to list or shows toast
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
