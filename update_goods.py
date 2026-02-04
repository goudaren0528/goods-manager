import os
import time
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError
import datetime

import sys

# 配置
USERNAME = "伟填"
PASSWORD = "Test0528."
LOGIN_URL = "https://szguokuai.zlj.xyzulin.top/web/index.php?c=site&a=entry&m=ewei_shopv2&do=web&r=goods"
# 默认数据文件，可以通过命令行参数覆盖
DATA_FILE = sys.argv[1] if len(sys.argv) > 1 else "update_goods_data.xlsx"
HEADLESS = True

def log_update(message):
    """记录更新日志"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] {message}"
    print(log_msg)
    with open("update.log", "a", encoding="utf-8") as f:
        f.write(log_msg + "\n")

def normalize_sku_key(sku_str):
    """
    归一化 SKU 键值：
    1. 去除空白
    2. 去重 (解决 Excel 中可能出现的重复规格)
    3. 排序 (解决列顺序不一致的问题)
    """
    if not sku_str: return ""
    parts = sku_str.split("|")
    # 过滤空值、去重、排序
    unique_parts = set()
    cleaned_parts = []
    for p in parts:
        p = p.strip()
        if p and p not in unique_parts:
            unique_parts.add(p)
            cleaned_parts.append(p)
            
    sorted_parts = sorted(cleaned_parts)
    return "|".join(sorted_parts)

def parse_excel_specs(group_df):
    """
    从 Excel 数据中解析出该商品需要的所有规格和值
    返回: { "规格名": ["值1", "值2"], ... } (有序字典)
    """
    from collections import OrderedDict
    specs_map = OrderedDict()
    
    for _, row in group_df.iterrows():
        sku_str = str(row.get("SKU", ""))
        if not sku_str: continue
        
        parts = sku_str.split("|")
        for part in parts:
            # 兼容中文冒号和英文冒号
            if "：" in part:
                separator = "："
            elif ":" in part:
                separator = ":"
            else:
                continue

            name, val = part.split(separator, 1)
            name = name.strip()
            val = val.strip()
            if name not in specs_map:
                specs_map[name] = []
            if val not in specs_map[name]:
                specs_map[name].append(val)
    
    return specs_map

def update_tenancy_specs(page, target_tenancies):
    if not target_tenancies:
        return False
        
    has_changes = False
    
    tenancy_btn_selector = "#tboption > table > tbody > tr:nth-child(1) > td > h4:nth-child(1) > a:nth-child(3)"
    tenancy_btn = page.query_selector(tenancy_btn_selector)
    
    if not tenancy_btn:
        log_update("  - 警告: 找不到'选择租期'按钮")
        return False
        
    log_update("  - 正在打开租期设置弹窗...")
    tenancy_btn.click()
    
    pop_selector = "body > div.BOX_PUBLIC_POP_WEB"
    try:
        page.wait_for_selector(pop_selector, state="visible", timeout=3000)
    except:
        log_update("  - 错误: 租期弹窗未弹出")
        return False
        
    list_container_selector = "body > div.BOX_PUBLIC_POP_WEB > div > div.tab-pane.active > div.main > div > div:nth-child(2) > table"
    
    def get_current_tenancies():
        rows = page.query_selector_all(f"{list_container_selector} > tbody > tr")
        current_map = {}
        for row in rows:
            # 用户提示：input 在 td:nth-child(2)
            input_el = row.query_selector("td:nth-child(2) input")
            if not input_el:
                # 降级尝试：直接找 input
                input_el = row.query_selector("input[type='text']") or row.query_selector("input")
            
            if input_el:
                val = input_el.input_value().strip()
                current_map[val] = row
        return current_map

    current_map = get_current_tenancies()
    
    # 注意：这里的 list_container_selector 是字符串，原来的代码写成了 .items() 可能是笔误
    # 应该是遍历 current_map 的副本
    for val, row in list(current_map.items()):
        if val not in target_tenancies:
            log_update(f"  - 删除多余租期: {val}天")
            # 优先使用用户提供的选择器: td:nth-child(4) > a
            del_btn = row.query_selector("td:nth-child(4) > a")
            
            if not del_btn:
                # 降级选择器
                del_btn = row.query_selector("td:last-child a") or row.query_selector("a.btn-del") or row.query_selector("a[onclick*='remove']")
                
            if del_btn:
                try:
                    del_btn.click()
                    has_changes = True
                    page.wait_for_timeout(500)
                except Exception as e:
                     log_update(f"    - 删除操作异常: {e}")
            else:
                log_update("    - 无法找到删除按钮")

    current_map = get_current_tenancies()

    add_btn_selector = "body > div.BOX_PUBLIC_POP_WEB > div > div.tab-pane.active > div.main > div > div:nth-child(1) > a"
    add_btn = page.query_selector(add_btn_selector)
    
    if not add_btn:
        log_update("  - 错误: 找不到'增加租期'按钮")
    else:
        for val in target_tenancies:
            if val not in current_map:
                log_update(f"  - 新增租期: {val}天")
                add_btn.click()
                page.wait_for_timeout(500)
                
                rows = page.query_selector_all(f"{list_container_selector} > tbody > tr")
                if rows:
                    new_row = rows[-1]
                    # 用户提示：input 在 td:nth-child(2)
                    input_el = new_row.query_selector("td:nth-child(2) input")
                    if not input_el:
                         input_el = new_row.query_selector("input")
                         
                    if input_el:
                        input_el.fill(val)
                        has_changes = True
                    else:
                        log_update("    - 新增后找不到输入框")
                else:
                    log_update("    - 新增后找不到新行")
                    
                current_map = get_current_tenancies()

    # 用户提供的精确选择器
    confirm_btn_selector = "body > div.BOX_PUBLIC_POP_WEB > div > div.box_hidden.box_btn > button.btn-sm-new.btn-primary.right.save"
    confirm_btn = page.query_selector(confirm_btn_selector)
    
    if not confirm_btn:
        # 降级尝试
        confirm_btn = page.query_selector(".BOX_PUBLIC_POP_WEB .btn-primary:has-text('确定')") or \
                      page.query_selector(".BOX_PUBLIC_POP_WEB .btn-primary")

    if confirm_btn:
        log_update("  - 提交租期修改...")
        # 尝试多种点击方式
        try:
            # 1. JS 原生 click (最稳健)
            confirm_btn.evaluate("el => el.click()")
            log_update("    - 已执行 JS 点击")
        except:
            try:
                # 2. Playwright force click
                confirm_btn.click(force=True)
                log_update("    - 已执行 Force 点击")
            except:
                log_update("    - 点击操作全部失败")
            
        # 等待弹窗消失
        try:
            page.wait_for_selector(pop_selector, state="hidden", timeout=5000)
        except:
            log_update("  - 警告: 租期弹窗可能未正常关闭 (点击提交后无反应)")
            # 再次尝试 JS 查找并点击 (防止引用丢失)
            try:
                page.evaluate(f"document.querySelector('{confirm_btn_selector}').click()")
                log_update("    - 重试 JS 全局查找并点击")
            except: pass
            
        page.wait_for_timeout(1000)
    else:
        log_update("  - 错误: 找不到租期弹窗的提交/保存按钮")
        close_btn = page.query_selector(".BOX_PUBLIC_POP_WEB .close")
        if close_btn:
            close_btn.click()
        else:
            log_update("  - 警告: 无法关闭租期弹窗")
            
    return has_changes

def update_page_specs(page, target_specs):
    """
    检查并更新页面的规格配置
    支持新增规格、新增规格值，以及删除多余的规格和值
    """
    if not target_specs:
        return False
        
    has_changes = False
    
    # --- 1. 清理多余的规格 ---
    # 获取页面现有的规格块
    spec_items = page.query_selector_all(".spec_item")
    page_specs_map = {}
    for item in spec_items:
        title_input = item.query_selector("input[name*='spec_title']")
        if title_input:
            title = title_input.input_value().strip()
            page_specs_map[title] = item

    # 找出不在目标列表中的规格并删除
    for title, item in page_specs_map.items():
        if title not in target_specs:
            log_update(f"  - 删除多余规格: {title}")
            # 查找删除按钮 (通常是 header 里的 x)
            btn = item.query_selector("a[onclick*='removeSpec']")
            if btn:
                try:
                    btn.click()
                    has_changes = True
                    page.wait_for_timeout(500) # 等待删除动画
                except Exception as e:
                    log_update(f"  - 删除规格失败: {e}")

    # --- 2. 遍历目标规格进行同步 (新增/更新/清理值) ---
    # 如果有变更，重新获取 DOM
    if has_changes:
        spec_items = page.query_selector_all(".spec_item")
        page_specs_map = {}
        for item in spec_items:
            title_input = item.query_selector("input[name*='spec_title']")
            if title_input:
                title = title_input.input_value().strip()
                page_specs_map[title] = item

    for spec_name, target_values in target_specs.items():
        if spec_name in ["租期", "天数"]:
            continue
            
        spec_block = None
        
        # 2.1 检查规格是否存在
        if spec_name in page_specs_map:
            spec_block = page_specs_map[spec_name]
            
            # --- 清理该规格下多余的值 ---
            val_items = spec_block.query_selector_all(".spec_item_item")
            for v_item in val_items:
                inp = v_item.query_selector("input[name*='spec_item_title']")
                if inp:
                    val = inp.input_value().strip()
                    if val not in target_values:
                        log_update(f"  - [{spec_name}] 删除多余值: {val}")
                        del_btn = v_item.query_selector("a[onclick*='removeSpecItem']")
                        if del_btn:
                            del_btn.click()
                            has_changes = True
                            page.wait_for_timeout(200)
            
        else:
            log_update(f"  - 新增规格: {spec_name}")
            # 点击添加规格按钮
            add_spec_btn = page.query_selector("#add-spec")
            if add_spec_btn:
                # 记录当前规格数量
                old_count = len(page.query_selector_all(".spec_item"))
                add_spec_btn.click()
                
                # 等待新规格块出现
                try:
                    page.wait_for_function(f"document.querySelectorAll('.spec_item').length > {old_count}", timeout=5000)
                except:
                    log_update("  - 警告: 等待新规格块超时")

                # 重新获取列表，取最后一个
                new_items = page.query_selector_all(".spec_item")
                if len(new_items) > old_count:
                    spec_block = new_items[-1]
                    # 填写规格名
                    title_input = spec_block.query_selector("input[name*='spec_title']")
                    if title_input:
                        title_input.fill(spec_name)
                    has_changes = True
                else:
                    log_update("  - 错误: 点击添加规格后未找到新规格块")
                    continue
            else:
                log_update("  - 错误: 找不到 #add-spec 按钮")
                continue
        
        # 2.2 检查并添加缺失的规格值
        if spec_block:
            # 重新获取当前已有的值 (因为可能删除了部分)
            existing_values = []
            item_inputs = spec_block.query_selector_all(".spec_item_item input[name*='spec_item_title']")
            for inp in item_inputs:
                existing_values.append(inp.input_value().strip())
            
            # 查找添加值的按钮
            add_val_btn = spec_block.query_selector(".add-specitem")
            
            for val in target_values:
                if val not in existing_values:
                    log_update(f"  - [{spec_name}] 新增值: {val}")
                    if add_val_btn:
                        add_val_btn.click()
                        try:
                            page.wait_for_timeout(300) 
                        except: pass

                        # 获取最新的输入框
                        new_inputs = spec_block.query_selector_all(".spec_item_item input[name*='spec_item_title']")
                        
                        if new_inputs:
                            # 找空值的或最后一个
                            target_input = None
                            for inp in reversed(new_inputs):
                                if not inp.input_value():
                                    target_input = inp
                                    break
                            
                            if not target_input: target_input = new_inputs[-1]
                            
                            target_input.fill(val)
                            has_changes = True
                        else:
                             log_update(f"  - 错误: 无法找到 [{spec_name}] 的新值输入框")
    
    if has_changes:
        # 等待表格刷新
        print("  - 规格已变更，等待 SKU 表格刷新...")
        refresh_btn = page.query_selector("a:has-text('刷新规格')")
        if refresh_btn and refresh_btn.is_visible():
             refresh_btn.click()
        page.wait_for_timeout(2000)
        
    return has_changes

def verify_data_completeness(page):
    """
    提交前检查：确保所有可见的输入框都有值
    """
    sku_table = page.query_selector("#options table")
    if not sku_table: return True # 如果没有 SKU 表格，可能只有单规格，略过
    
    inputs = sku_table.query_selector_all("input:not([type='hidden'])")
    is_complete = True
    for inp in inputs:
        if inp.is_visible():
            val = inp.input_value()
            if not val:
                # 高亮或记录
                try:
                    # 尝试获取父级 TD 的类名或位置以提供更多信息
                    parent = inp.evaluate("el => el.parentElement.className")
                    log_update(f"  - 警告: 发现未填写的输入框 (Class: {parent})")
                except:
                    log_update("  - 警告: 发现未填写的输入框")
                is_complete = False
    
    return is_complete

def login(page):
    """
    统一登录逻辑
    """
    print(f"正在访问登录页面: {LOGIN_URL}")
    try:
        page.goto(LOGIN_URL)
        page.wait_for_load_state('networkidle')
    except Exception as e:
        print(f"访问登录页失败: {e}")
        return False

    # 检查是否需要登录
    if "login" in page.url or page.query_selector("input[name='username']"):
        print(f"检测到需要登录 (当前URL: {page.url})")
        print("尝试自动登录...")
        
        try:
            # 确保输入框可见再操作
            page.wait_for_selector("input[name='username']", state="visible", timeout=5000)
            page.fill("input[name='username']", USERNAME)
            page.fill("input[name='password']", PASSWORD)
            
            # 使用 wait_for_navigation 配合点击，防止点击后页面立刻刷新导致上下文丢失
            # 或者先不等待导航，直接点，然后单独等状态
            submit_btn = page.query_selector("input[type='submit']")
            if submit_btn:
                submit_btn.click()
            else:
                # 尝试其他提交方式
                page.press("input[name='password']", "Enter")
            
            print("等待登录跳转...")
            # 1. 等待密码框消失 (表示提交成功)
            try:
                page.wait_for_selector("input[type='password']", state="hidden", timeout=5000)
            except:
                pass
            
            page.wait_for_timeout(3000)
            
            if "r=goods" not in page.url or "login" in page.url:
                print("未自动跳转到商品列表页，尝试强制访问...")
                page.goto(LOGIN_URL)
                page.wait_for_load_state('networkidle')
            
            print("登录流程结束。")
        except Exception as e:
            print(f"登录过程出错: {e}")
            return False
    else:
        print("已处于登录状态。")
        
    return True

def get_page_sku_map(page):
    """
    解析当前页面的 SKU 表格，返回一个映射字典：
    Key: SKU 字符串 (格式: "表头：值|表头：值")
    Value: { 
        "element_row_index": int, 
        "data_inputs": { "列名": InputElementHandle, ... } 
    }
    """
    sku_map = {}
    
    sku_table = page.query_selector("#options table")
    if not sku_table:
        return sku_map
        
    try:
        # 1. 获取表头
        headers = []
        thead = sku_table.query_selector("thead")
        if thead:
            ths = thead.query_selector_all("th")
            for th in ths:
                headers.append(th.inner_text().strip())
        
        # 2. 构建网格 (处理 rowspan/colspan)
        # 这里我们需要复用 scrape_goods.py 中的逻辑，但这次我们需要保存 ElementHandle 而不仅仅是值
        tbody = sku_table.query_selector("tbody")
        if not tbody: return sku_map
        
        tr_elements = tbody.query_selector_all("tr")
        
        grid = {} # row_idx -> col_idx -> { "value": str, "element": handle, "is_data": bool }
        
        current_row_idx = 0
        for tr in tr_elements:
            tds = tr.query_selector_all("td")
            current_col_idx = 0
            
            if current_row_idx not in grid: grid[current_row_idx] = {}
                
            for td in tds:
                # 跳过占用
                while current_col_idx in grid[current_row_idx]:
                    current_col_idx += 1
                
                # 获取 rowspan/colspan
                rowspan = 1
                colspan = 1
                try:
                    rs = td.get_attribute("rowspan")
                    if rs: rowspan = int(rs)
                except: pass
                try:
                    cs = td.get_attribute("colspan")
                    if cs: colspan = int(cs)
                except: pass
                
                # 提取值和输入框元素
                val = ""
                input_el = td.query_selector("input:not([type='hidden'])")
                is_data = False
                
                if input_el:
                    val = input_el.input_value() # 初始值用于调试，实际修改用 element
                    is_data = True
                else:
                    select_el = td.query_selector("select")
                    if select_el:
                        val = select_el.input_value()
                        is_data = True
                        input_el = select_el # Treat select as input
                    else:
                        val = td.inner_text().strip()
                
                cell_info = {
                    "value": val,
                    "element": input_el, # 只有数据列才有 element
                    "is_data": is_data
                }
                
                # 填充网格
                for r in range(rowspan):
                    for c in range(colspan):
                        target_row = current_row_idx + r
                        target_col = current_col_idx + c
                        if target_row not in grid: grid[target_row] = {}
                        grid[target_row][target_col] = cell_info
                
                current_col_idx += colspan
            current_row_idx += 1
            
        # 3. 区分规格列和数据列 (逻辑同 scrape_goods.py)
        spec_col_indices = []
        data_col_indices = []
        
        for idx, h in enumerate(headers):
            h_lower = h.lower()
            if any(k in h_lower for k in ["库存", "编号", "租金", "价格", "重量", "编码", "id"]):
                data_col_indices.append(idx)
            else:
                has_input = False
                for r in range(current_row_idx):
                    if r in grid and idx in grid[r] and grid[r][idx]["is_data"]:
                        has_input = True
                        break
                if has_input:
                    data_col_indices.append(idx)
                else:
                    spec_col_indices.append(idx)

        # 4. 生成 SKU Map
        for r in range(current_row_idx):
            if r not in grid: continue
            
            # 生成 SKU Key
            specs = []
            for c in spec_col_indices:
                if c in grid[r]:
                    val = grid[r][c]["value"]
                    if val:
                        header_name = headers[c] if c < len(headers) else ""
                        if header_name:
                            specs.append(f"{header_name}：{val}")
                        else:
                            specs.append(val)
            
            sku_key = "|".join(specs)
            sku_key = normalize_sku_key(sku_key)
            
            # 收集数据列的 Input 元素
            data_inputs = {}
            for c in data_col_indices:
                if c in grid[r]:
                    header_name = headers[c] if c < len(headers) else f"Col_{c}"
                    el = grid[r][c]["element"]
                    if el:
                        data_inputs[header_name] = el
            
            sku_map[sku_key] = {
                "row_idx": r,
                "data_inputs": data_inputs
            }
            
    except Exception as e:
        print(f"解析页面 SKU 表格失败: {e}")
        import traceback
        traceback.print_exc()
        
    return sku_map

def sync_goods_data(update_df, output_file="goods_data.xlsx"):
    if update_df is None or update_df.empty:
        return
    if "ID" not in update_df.columns:
        log_update("  - 警告: update_goods_data 中缺少 ID 列，无法同步 goods_data")
        return
        
    update_df = update_df.copy()
    update_df["ID"] = update_df["ID"].astype(str)
    update_df.fillna("", inplace=True)
    
    if not os.path.exists(output_file):
        try:
            update_df.to_excel(output_file, index=False)
            log_update(f"  - 已生成 {output_file}")
        except Exception as e:
            log_update(f"  - 写入 {output_file} 失败: {e}")
        return
        
    try:
        goods_df = pd.read_excel(output_file, dtype=str)
        goods_df.fillna("", inplace=True)
    except Exception as e:
        log_update(f"  - 读取 {output_file} 失败: {e}")
        return
        
    if "ID" not in goods_df.columns:
        goods_df["ID"] = ""
    goods_df["ID"] = goods_df["ID"].astype(str)
    
    target_ids = set(update_df["ID"].tolist())
    goods_df_filtered = goods_df[~goods_df["ID"].isin(target_ids)]
    
    all_cols = list(goods_df.columns)
    for col in update_df.columns:
        if col not in all_cols:
            all_cols.append(col)
            
    for col in all_cols:
        if col not in goods_df_filtered.columns:
            goods_df_filtered[col] = ""
        if col not in update_df.columns:
            update_df[col] = ""
            
    goods_df_filtered = goods_df_filtered[all_cols]
    update_df = update_df[all_cols]
    
    merged_df = pd.concat([goods_df_filtered, update_df], ignore_index=True)
    try:
        merged_df.to_excel(output_file, index=False)
        log_update(f"  - 已同步更新到 {output_file} (覆盖 {len(target_ids)} 个ID)")
    except Exception as e:
        log_update(f"  - 写入 {output_file} 失败: {e}")
        if "Permission denied" in str(e):
            try:
                timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                backup_file = f"goods_data_backup_{timestamp}.xlsx"
                merged_df.to_excel(backup_file, index=False)
                log_update(f"  - 严重警告: 原文件被占用，数据已紧急保存到: {backup_file}")
                log_update(f"  - 请关闭 Excel 后手动将备份文件重命名为 {output_file}")
            except Exception as e2:
                log_update(f"  - 备份写入也失败: {e2}")

def run_update():
    if not os.path.exists(DATA_FILE):
        print(f"错误：找不到数据文件 {DATA_FILE}")
        return

    print(f"正在读取数据文件 {DATA_FILE} ...")
    try:
        df = pd.read_excel(DATA_FILE, dtype=str)
        df.fillna("", inplace=True)
    except Exception as e:
        print(f"读取 Excel 失败: {e}")
        return

    # 按 ID 分组
    if "ID" not in df.columns:
        print("错误：Excel 中缺少 'ID' 列")
        return

    grouped = df.groupby("ID")
    print(f"共加载 {len(grouped)} 个商品待处理。")

    p = None
    browser = None
    try:
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context()
        page = context.new_page()

        # 登录
        if not login(page):
            return

        processed_count = 0
        for goods_id, group_df in grouped:
            processed_count += 1
            log_update(f"\n[{processed_count}/{len(grouped)}] 正在处理 ID: {goods_id}")
            
            # 访问编辑页
            edit_url = f"https://szguokuai.zlj.xyzulin.top/web/index.php?c=site&a=entry&m=ewei_shopv2&do=web&r=goods.edit&id={goods_id}&goodsfrom=sale&page=1"
            try:
                page.goto(edit_url)
                page.wait_for_load_state('domcontentloaded')
                
                # 检查是否进入了正确的编辑页
                if "r=goods.edit" not in page.url:
                    log_update(f"  - 无法进入编辑页，跳过 (当前URL: {page.url})")
                    continue
                
                is_modified = False
                
                # 1. 检查基础信息 (取第一行数据作为基准)
                first_row = group_df.iloc[0]
                
                # 商品名称
                if "商品名称" in first_row:
                    target_name = first_row["商品名称"]
                    name_input = page.query_selector("#goodsname")
                    if name_input:
                        current_name = name_input.input_value()
                        if current_name != target_name:
                            log_update(f"  - 修改商品名称: {current_name} -> {target_name}")
                            name_input.fill(target_name)
                            is_modified = True
                
                # 短标题
                if "短标题" in first_row:
                    target_short = first_row["短标题"]
                    short_input = page.query_selector("input[name='shorttitle']")
                    if not short_input:
                            short_input = page.locator("label:has-text('商品短标题')").locator("..").locator("input").first
                    
                    if short_input and short_input.is_visible():
                        current_short = short_input.input_value()
                        if current_short != target_short:
                            log_update(f"  - 修改短标题: {current_short} -> {target_short}")
                            short_input.fill(target_short)
                            is_modified = True

                # 1.5 更新分类 (1级, 2级, 3级)
                for level, selector in [(1, "#cate1"), (2, "#cate2"), (3, "#cate3")]:
                    col_name = f"{level}级分类"
                    if col_name in first_row:
                        target_val = str(first_row[col_name]).strip()
                        
                        # 如果 Excel 中该列有值（非空字符串），则尝试更新
                        if target_val:
                            try:
                                # 检查元素是否存在
                                if not page.query_selector(selector):
                                    continue

                                # 获取当前选中的文本
                                try:
                                    current_val = page.eval_on_selector(selector, "el => el.options[el.selectedIndex] ? el.options[el.selectedIndex].text : ''").strip()
                                    if "请选择" in current_val: current_val = ""
                                except:
                                    current_val = ""
                                
                                if current_val != target_val:
                                    log_update(f"  - 修改 {col_name}: {current_val} -> {target_val}")
                                    
                                    # 尝试选择
                                    page.select_option(selector, label=target_val)
                                    is_modified = True
                                    
                                    # 如果是 1 或 2 级，选择后可能触发 AJAX 加载下一级
                                    if level < 3:
                                        page.wait_for_timeout(1000)
                            except Exception as e:
                                log_update(f"  - 警告: 更新 {col_name} 失败: {e} (可能选项不存在)")

                # 2. 检查并同步规格 (新增逻辑)
                # 解析 Excel 中该商品的目标规格结构
                target_specs = parse_excel_specs(group_df)
                log_update(f"  - 解析到的目标规格: {target_specs}")
                
                # 提取租期信息
                target_tenancies = []
                if "租期" in target_specs:
                    target_tenancies = target_specs["租期"]
                elif "天数" in target_specs:
                    target_tenancies = target_specs["天数"]
                else:
                    # 尝试从 Excel 列名中解析租期 (例如 "3天租金", "30天租金")
                    # group_df 的列名中如果包含 "天租金" 或 "天价格"
                    for col in group_df.columns:
                        if "天租金" in col:
                            # 提取 "3" from "3天租金"
                            try:
                                day_val = col.split("天")[0].strip()
                                if day_val.isdigit() and day_val not in target_tenancies:
                                    target_tenancies.append(day_val)
                            except: pass
                    
                    # 排序租期 (按数字大小)
                    target_tenancies.sort(key=lambda x: int(x) if x.isdigit() else 9999)

                log_update(f"  - 解析到的目标租期: {target_tenancies}")

                # 先更新租期 (因为租期可能会影响规格列表或者 SKU 组合)
                if update_tenancy_specs(page, target_tenancies):
                    is_modified = True
                    log_update("  - 租期已更新")
                
                if update_page_specs(page, target_specs):
                    is_modified = True
                    log_update("  - 规格已更新，重新解析页面元素...")

                # 3. 检查 SKU 数据
                # 获取页面当前的 SKU 映射 (规格更新后需要重新获取)
                page_sku_map = get_page_sku_map(page)
                
                for idx, row in group_df.iterrows():
                    target_sku_key = row.get("SKU", "")
                    if not target_sku_key: continue
                    
                    # 归一化 Key 以匹配
                    target_sku_key = normalize_sku_key(target_sku_key)
                    
                    if target_sku_key in page_sku_map:
                        page_sku_data = page_sku_map[target_sku_key]
                        data_inputs = page_sku_data["data_inputs"]
                        
                        # 遍历 Excel 中的列，查找是否有对应的数据列需要更新
                        for col_name in row.index:
                            # 跳过基础列和 SKU 列
                            if col_name in ["ID", "商品名称", "短标题", "1级分类", "2级分类", "3级分类", "SKU"]:
                                continue
                                
                            target_val = str(row[col_name])
                            if target_val.endswith(".0"):
                                target_val = target_val[:-2]
                            
                            # 在页面 inputs 中查找
                            if col_name in data_inputs:
                                input_el = data_inputs[col_name]
                                try:
                                    current_val = input_el.input_value()
                                    if current_val != target_val:
                                        log_update(f"  - 修改 [{target_sku_key}] {col_name}: {current_val} -> {target_val}")
                                        input_el.fill(target_val)
                                        is_modified = True
                                except:
                                    pass
                    else:
                        log_update(f"  - 警告: 页面未找到 SKU [{target_sku_key}]，无法更新该行数据。")

                # 4. 提交前检查完整性
                if is_modified:
                    if not verify_data_completeness(page):
                         log_update("  - 严重警告: 存在未填写的输入框！但这可能影响保存，请检查日志。")

                    log_update("  - 检测到变更，正在保存...")
                    save_btn_selector = "body > div.wb-container > div.page-content > form > div.form-group > div > input"
                    save_btn = page.query_selector(save_btn_selector)
                    
                    if save_btn:
                        try:
                            with page.expect_navigation(timeout=10000):
                                save_btn.click()
                            log_update("  - 保存成功！")
                        except TimeoutError:
                            log_update("  - 警告: 保存超时 (10s未跳转)，可能存在验证错误或无需跳转。")
                            # 尝试检测页面上的错误提示 (假设是用 Bootstrap 或常见样式)
                            try:
                                error_tips = page.query_selector_all(".text-danger, .tip-msg") 
                                found_error = False
                                for tip in error_tips:
                                    if tip.is_visible():
                                        txt = tip.inner_text().strip()
                                        if txt: 
                                            log_update(f"    * 可能的错误提示: {txt}")
                                            found_error = True
                                if not found_error:
                                    log_update("    * 未检测到明显的错误提示文本。")
                            except:
                                pass
                    else:
                        log_update("  - 错误：找不到保存按钮！")
                else:
                    log_update("  - 数据一致，无需修改。")

            except Exception as e:
                log_update(f"处理 ID {goods_id} 时发生异常: {e}")
                import traceback
                traceback.print_exc()

    except Exception as e:
        log_update(f"更新任务异常: {e}")
    finally:
        if browser:
            try: browser.close()
            except: pass
        if p:
            try: p.stop()
            except: pass
        
    sync_goods_data(df)

if __name__ == "__main__":
    run_update()
