# 支付宝商品自动化管理系统

基于 Python Playwright 和 Next.js 全栈开发的商品管理系统，支持商品抓取、自动化更新、Excel 导入导出及可视化管理。

## 功能特性

- **数据展示**：可视化展示所有商品信息，支持按 ID、名称、SKU 搜索。
- **自动化同步**：一键从 Excel 同步数据到本地数据库，支持从数据库导出 Excel。
- **批量管理**：支持商品批量选择与编辑，自动生成更新任务。
- **自动化执行**：集成 Playwright 脚本，前端直接触发自动化更新流程（自动登录支付宝后台修改商品信息）。
- **实时日志**：前端实时显示自动化脚本的运行日志。

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
├── goods_data.xlsx       # 商品数据源文件
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
pip install fastapi uvicorn pandas openpyxl

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

确保根目录下有 `goods_data.xlsx` 文件。
首次运行自动化脚本时，需要手动扫码登录支付宝商家中心。

## 注意事项

- 自动化脚本运行时会占用鼠标和键盘，建议在独立环境或闲置时运行。
- `alipay_user_data` 目录存储了浏览器指纹和登录状态，请勿随意删除，以免频繁重新登录。
