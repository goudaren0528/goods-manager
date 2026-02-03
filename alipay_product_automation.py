import time
import random
import datetime
import os
import re
from playwright.sync_api import sync_playwright

# --- 配置区域 ---
PENDING_FILE = "pending.txt"
ALIPAY_HOME_URL = "https://b.alipay.com/"
GOODS_LIST_URL = "https://b.alipay.com/page/commerce/goods/list?appId=2021005181665859&itemSubType=RENT&itemType=NORMAL_ITEM"
USER_DATA_DIR = os.path.join(os.getcwd(), "alipay_user_data") # 用户数据目录，用于保持登录状态

# 待填写的文本内容
SERVICE_INTRO = ""          # value_added_services_0_service_introduction
PROTECTION_SCOPE = ""       # value_added_services_0_protection_scope
DISCLAIMER = ""             # value_added_services_0_disclaimer
CLAIM_PROCESS = ""          # value_added_services_0_claim_process

def load_pending_ids():
    if not os.path.exists(PENDING_FILE):
        print(f"错误: {PENDING_FILE} 不存在")
        return []
    with open(PENDING_FILE, "r", encoding="utf-8") as f:
        # 过滤空行和空白字符
        return [line.strip() for line in f if line.strip()]

def get_timestamp_str():
    return datetime.datetime.now().strftime("%Y%m%d%H%M%S")

def main():
    pending_ids = load_pending_ids()
    if not pending_ids:
        print("没有待处理的商品ID。")
        return

    print(f"待处理ID列表: {pending_ids}")

    with sync_playwright() as p:
        # 启动持久化上下文，保持登录状态
        # 注意：如果浏览器正在运行且使用了相同的 user_data_dir，这里可能会报错
        if not os.path.exists(USER_DATA_DIR):
            os.makedirs(USER_DATA_DIR)
            
        print(f"启动浏览器 (UserData: {USER_DATA_DIR})...")
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=True,
            args=["--start-maximized"],
            no_viewport=True
        )
        
        # 获取第一个页面或新建
        page = context.pages[0] if context.pages else context.new_page()

        # 1. 访问首页并等待登录
        print(f"正在访问 {ALIPAY_HOME_URL}，如未登录请手动登录...")
        try:
            page.goto(ALIPAY_HOME_URL)
        except Exception as e:
            print(f"打开首页异常 (可忽略): {e}")

        print(">>> 请在浏览器中完成登录，并选择账号进入商家后台 <<<")
        print(">>> 脚本将持续检测商品列表页，直到成功进入 <<<")
        
        # 循环检测直到成功进入商品列表页
        # 逻辑：
        # 1. 每隔几秒尝试判断当前是否已在列表页
        # 2. 如果不在，且 URL 看起来已登录，尝试跳转到列表页
        # 3. 如果跳转后找不到表格，说明可能还在选账号或登录未完成，继续等待
        
        while True:
            try:
                # A. 尝试跳转到商品列表页 (如果当前不在)
                if GOODS_LIST_URL not in page.url:
                    print(f"尝试跳转到商品列表页...")
                    try:
                        page.goto(GOODS_LIST_URL)
                        page.wait_for_load_state("networkidle", timeout=5000)
                    except:
                        pass # 忽略跳转超时

                # B. 检测是否成功显示了商品表格
                try:
                    # 短暂等待表格出现
                    page.wait_for_selector(".merchant-ui-table", timeout=5000)
                    print("SUCCESS: 成功检测到商品表格！开始执行任务...")
                    break # 成功！跳出循环
                except:
                    # 未找到表格
                    print("等待中... 请确保已登录并进入商家后台 (脚本正在重试进入列表页)")
                    # 如果用户正在操作（比如选账号），不要频繁刷新打断，多等一会儿
                    time.sleep(5)
            
            except Exception as e:
                print(f"检测循环异常: {e}，重试中...")
                time.sleep(3)


        # 2. 遍历处理 ID
        processed_ids = []
        
        for target_id in pending_ids:
            print(f"\n正在查找商品 ID: {target_id}")
            
            # 每次查找新 ID 时，建议刷新回第一页，防止漏找
            print("正在重置到列表首页...")
            page.goto(GOODS_LIST_URL)
            try:
                page.wait_for_selector(".merchant-ui-table", timeout=10000)
            except:
                print("等待表格超时，重试...")
                page.reload()
                page.wait_for_selector(".merchant-ui-table")

            # 查找匹配的行 (支持翻页)
            found = False
            target_row = None
            
            while True:
                # 等待表格加载
                page.wait_for_timeout(2000)
                
                # 获取所有行
                rows = page.locator(".merchant-ui-table table tbody tr").all()
                print(f"当前页共有 {len(rows)} 行数据")
                
                for row in rows:
                    try:
                        # 获取商家侧编码
                        # 用户选择器: td.ant-table-cell.ant-table-cell-fix-left.ant-table-cell-fix-left-last > div > div.goodsPart___GoH9Y > span:nth-child(3)
                        # 尝试定位到 goodsPart___GoH9Y 下的第三个 span
                        code_el = row.locator(".goodsPart___GoH9Y span").nth(2)
                        
                        # 如果找不到，尝试更通用的定位
                        if not code_el.count():
                             code_el = row.locator("td:nth-child(2)").first
                        
                        code_text = code_el.inner_text().strip()
                        
                        # 匹配逻辑：必须包含类似 -ID- 的结构，即 ID 被横杠分隔或位于边界
                        # 使用正则匹配：(行首或-) + ID + (行尾或-)
                        # 避免部分匹配错误（如搜 253 匹配到 1253）
                        pattern = r'(?:^|-){}(?:-|$)'.format(re.escape(str(target_id)))
                        
                        if re.search(pattern, code_text):
                            print(f"找到匹配行！商家侧编码内容: {code_text}")
                            target_row = row
                            found = True
                            break
                    except Exception as e:
                        continue
                
                if found:
                    break
                
                # 未找到，尝试翻页
                # 用户选择器: li.ant-pagination-next > button
                next_li = page.locator("li.ant-pagination-next").first
                
                if next_li.count() > 0:
                    # 检查是否禁用 (class 包含 ant-pagination-disabled 或 aria-disabled=true)
                    class_attr = next_li.get_attribute("class") or ""
                    aria_disabled = next_li.get_attribute("aria-disabled")
                    
                    if "ant-pagination-disabled" not in class_attr and aria_disabled != "true":
                        next_btn = next_li.locator("button")
                        if next_btn.is_visible():
                            print("当前页未找到，点击下一页...")
                            next_btn.click()
                            continue
                
                print(f"已遍历所有页，未找到 ID {target_id}")
                break

            if not found:
                print(f"未找到 ID {target_id}，跳过")
                continue
                
            # 3. 点击更多 -> 复制
            try:
                # 更多按钮: td:nth-child(8) > div > a
                more_btn = target_row.locator("td:nth-child(8) a").first
                more_btn.click()
                
                # 等待下拉菜单出现并点击“复制”
                print("点击更多按钮，等待菜单...")
                # 等待下拉菜单出现，通常在 body 下
                page.wait_for_selector(".ant-dropdown:not(.ant-dropdown-hidden)", timeout=5000)
                
                with context.expect_page() as new_page_info:
                    # 点击“复制”文本
                    page.locator(".ant-dropdown-menu-item:has-text('复制')").click()
                    
                new_page = new_page_info.value
                print("新窗口已打开，等待加载...")
                new_page.wait_for_load_state("domcontentloaded")
                
                # 4. 在新窗口操作
                handle_copy_page(new_page, target_id)
                
                print(f"ID {target_id} 处理完成，保留新窗口...")
                # new_page.close() # 用户要求不关闭
                processed_ids.append(target_id)
                
            except Exception as e:
                print(f"处理 ID {target_id} 时发生错误: {e}")
                import traceback
                traceback.print_exc()

        print("\n所有任务处理完毕。")
        input("按回车键退出程序 (将关闭浏览器)...")
        context.close()

def handle_copy_page(page, original_id):
    """在新窗口中填写表单"""
    # 等待表单加载
    page.wait_for_selector("#formContainerWrap", timeout=20000)
    time.sleep(3) # 额外等待渲染
    
    timestamp = get_timestamp_str()
    
    # 1. 修改商家侧编码
    print("正在修改商家侧编码...")
    # 用户路径: #formContainerWrap > div.goodsContainer___wtXQp > div > form > div:nth-child(2) > div.ant-card-body > div > div:nth-child(5) ... input
    # 尝试使用相对稳定的部分
    try:
        # 定位到包含“商家侧编码”的 label 所在的 form-item，然后找 input
        code_input = page.locator("label:has-text('商家侧编码')").locator("xpath=../..").locator("input").first
        if not code_input.is_visible():
             # Fallback: 使用第5个 form item 的 input (基于用户描述)
             code_input = page.locator("div.goodsContainer___wtXQp form > div:nth-child(2) .ant-form-item").nth(4).locator("input")
        
        current_val = code_input.input_value()
        new_val = f"{current_val}_{timestamp}"
        print(f"编码更新: {current_val} -> {new_val}")
        code_input.fill(new_val)
        
        # 保存新的编码用于 SKU 前缀
        sku_prefix = new_val
    except Exception as e:
        print(f"修改商家侧编码失败: {e}")
        sku_prefix = f"SKU_{original_id}_{timestamp}"

    # 2. 租期计算规则 & 免押金
    try:
        print("设置租期规则和免押金...")
        page.locator("#rent_duration_cal_rule label").nth(1).click() # nth-child(2) is index 1
        page.locator("#whether_support_free_deposit label").nth(0).click() # nth-child(1) is index 0
    except Exception as e:
        print(f"设置租期/免押金失败: {e}")

    # 3. 修改增值服务内容
    print("修改增值服务内容...")
    fill_textarea(page, "#value_added_services_0_service_introduction", SERVICE_INTRO)
    fill_textarea(page, "#value_added_services_0_protection_scope", PROTECTION_SCOPE)
    fill_textarea(page, "#value_added_services_0_disclaimer", DISCLAIMER)
    fill_textarea(page, "#value_added_services_0_claim_process", CLAIM_PROCESS)
    
    # 清空 special_intruction
    try:
        page.fill("#value_added_services_0_special_intruction", "")
    except: pass

    # 4. 勾选所有选项
    print("勾选所有选项...")
    try:
        # 用户路径: ... div:nth-child(3) ... div.ant-col.ant-col-10 ...
        # 定位到第三个大块 (增值服务块?)
        # 直接定位所有 checkbox 可能会误伤，限制在第三个卡片区域
        card3 = page.locator("div.goodsContainer___wtXQp form > div").nth(2)
        
        # 查找该区域内的所有 checkbox
        checkboxes = card3.locator(".ant-checkbox-wrapper:not(.ant-checkbox-wrapper-checked)").all()
        for cb in checkboxes:
            cb.click()
            time.sleep(0.05)
    except Exception as e:
        print(f"勾选选项失败: {e}")

    # 5. SKU 编码输入
    print("填写 SKU 编码...")
    try:
        # 用户路径: ... div.ant-table-tbody-virtual ... div:nth-child(13) ... input
        # 定位虚拟表格容器
        virtual_body = page.locator("div.ant-table-tbody-virtual")
        if virtual_body.count() > 0:
            # 这是一个虚拟列表
            # 这里的难点是 div:nth-child(13) 是针对什么的？
            # 假设是每行里的第13个 div (列)
            
            # 获取所有可见的行容器
            # 通常虚拟列表的行是 .ant-table-row 或者直接是 div
            # ant-table-tbody-virtual-holder-inner > div
            
            # 我们可以尝试直接查找符合特定层级的 input
            # 用户给的层级非常深，我们可以尝试简化：
            # 在 virtual_body 内部查找所有的 input
            # 然后筛选出那些看起来像 SKU 编码的（或者全部填一遍，如果第13列是唯一的 input 列）
            
            # 让我们尝试定位每一行，然后找第13个格子
            # 假设每行是一个 div (在 virtual-holder-inner 下)
            rows = virtual_body.locator(".ant-table-tbody-virtual-holder-inner > div").all()
            print(f"找到 {len(rows)} 个 SKU 行 (可见)")
            
            for row in rows:
                # 尝试找第13个 div (列)
                # 注意：nth-child 是 1-based，nth 是 0-based
                # 用户说 div:nth-child(13)，所以是 index 12
                col_13 = row.locator("> div").nth(12) 
                input_el = col_13.locator("input")
                
                if input_el.count() > 0:
                    rand_suffix = str(random.randint(10, 99))
                    sku_val = f"{sku_prefix}_{rand_suffix}"
                    input_el.fill(sku_val)
        else:
            # 普通表格 fallback
            print("未检测到虚拟列表，尝试普通表格查找...")
            inputs = card3.locator("table input[type='text']").all()
            for inp in inputs:
                rand_suffix = str(random.randint(10, 99))
                sku_val = f"{sku_prefix}_{rand_suffix}"
                inp.fill(sku_val)
                
    except Exception as e:
        print(f"填写 SKU 失败: {e}")

    # 6. 提交
    print("提交表单...")
    try:
        # 用户路径: #formContainerWrap > div.footer___wSqtX > div:nth-child(1) > div:nth-child(1) > div > button
        # 寻找 footer 下的按钮，通常是“提交”或“发布”
        # 尝试点击最后一个按钮，或者包含“提交/发布”文本的按钮
        footer = page.locator("div.footer___wSqtX")
        submit_btn = footer.locator("button").last
        submit_btn.click()
        
        # 等待提交完成
        page.wait_for_timeout(3000)
    except Exception as e:
        print(f"提交失败: {e}")

def fill_textarea(page, selector, value):
    try:
        page.fill(selector, value)
    except Exception as e:
        print(f"填写 {selector} 失败: {e}")

if __name__ == "__main__":
    main()
