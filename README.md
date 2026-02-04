# 支付宝商品自动化管理系统

基于 Python Playwright 和 Next.js 全栈开发的商品管理系统，支持商品抓取、自动化更新、数据库管理及可视化操作。

## 功能特性

- **数据展示**：可视化展示所有商品信息，支持按 ID、名称、SKU 搜索。
- **数据管理**：基于 SQLite 数据库管理商品信息，支持抓取脚本同步数据，替代传统 Excel 管理模式。
- **批量管理**：支持商品批量选择、批量修改（如差价设置、规格添加）、租金曲线应用。
- **自动化执行**：
    - 集成 Playwright 脚本，前端一键触发支付宝商品信息更新。
    - **自动登录**：支持支付宝商家中心自动登录流程（含验证码处理）。
    - **验证码交互**：前端弹窗实时输入手机验证码，无缝对接后台脚本。
    - **精确匹配**：通过“支付宝编码”与商家侧编码精确匹配，确保更新准确无误。
- **实时日志**：前端实时显示自动化脚本的运行日志及任务状态。

## 技术栈

- **前端**：Next.js 14 (App Router), Tailwind CSS, Shadcn UI
- **后端**：FastAPI, SQLite, Pandas
- **自动化**：Python Playwright

## 目录结构

```
/goods-manager
├── web/                  # Next.js 前端项目
├── server/               # FastAPI 后端服务
├── alipay_product_automation.py  # 支付宝自动化脚本
├── update_goods.py       # 商品更新脚本
├── scrape_goods.py       # 商品抓取脚本
└── README.md             # 项目文档
```

## 快速开始

### 1. 环境准备

确保已安装：
- Python 3.10+
- Node.js 18+
- Git

### 2. 启动后端服务

```bash
cd server
# 创建虚拟环境（可选）
python -m venv venv
# Windows 激活
.\venv\Scripts\activate

# 安装依赖
pip install fastapi uvicorn pandas openpyxl playwright
playwright install chromium

# 启动服务
uvicorn main:app --reload --port 8000
```

### 3. 启动前端服务

打开新的终端窗口：

```bash
cd web
# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

访问 [http://localhost:3000](http://localhost:3000) 即可使用系统。

### 4. 自动化脚本配置

1.  在系统工作台中，为需要更新的商品填入准确的“支付宝编码”（即支付宝后台的商家侧编码）。
2.  点击“更新支付宝”按钮，输入接收验证码的手机号启动任务。
3.  脚本会自动拉起浏览器（有头模式），在遇到登录验证码时，请留意网页提示及工作台弹窗。

## 注意事项

- 自动化脚本运行时会打开浏览器窗口（headless=False），请勿手动关闭窗口或干扰脚本操作。
- `alipay_user_data` 目录存储了浏览器用户数据，删除后需要重新登录。
