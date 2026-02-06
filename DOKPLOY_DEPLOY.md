# Dokploy 部署指南

本指南将帮助你使用 Dokploy 部署 Goods Manager 系统（包含 Web 前端、Server 后端和 PostgreSQL 数据库）。

## 1. 准备工作

确保代码已提交到 Git 仓库（GitHub/GitLab/Gitea）。

仓库结构应为：
```
/
  docker-compose.yml
  server/
    Dockerfile
    ...
  web/
    Dockerfile
    ...
```

## 2. Dokploy 项目设置

1. 登录 Dokploy 面板。
2. 创建一个新项目 (Project)，例如 `goods-manager`。

## 3. 部署方式选择

推荐使用 **Docker Compose** 方式进行统一部署，这样网络配置最简单。

### 方式一：Docker Compose Stack (推荐)

1. 在项目下点击 "Compose"。
2. 点击 "Create Compose"。
3. 填写名称，例如 `goods-stack`。
4. 选择 "Git" 作为来源。
   - **Repository URL**: 你的 Git 仓库地址。
   - **Branch**: `main` 或 `master`。
   - **Compose Path**: `docker-compose.yml` (默认即可)。
5. 点击 "Create"。

### 4. 环境变量配置 (Environment Variables)

在 Compose 详情页的 "Environment" 标签页中，你可以覆盖 `docker-compose.yml` 中的变量。

建议配置：

```env
# Postgres 配置
POSTGRES_USER=myuser
POSTGRES_PASSWORD=mypassword
POSTGRES_DB=goods

# Server 配置
# 注意：DATABASE_URL 必须与 Postgres 配置匹配
# 格式：postgresql://<user>:<password>@postgres:5432/<db>
DATABASE_URL=postgresql://myuser:mypassword@postgres:5432/goods

# Web 配置
#这是前端访问后端的地址。
# 如果你为 Server 绑定了域名 (如 api.example.com)，请填写该域名。
# 如果没有绑定域名，且只是测试，可以使用服务器 IP:8000 (需在 Dokploy 开放端口)。
NEXT_PUBLIC_API_URL=https://api.yourdomain.com
```

> **注意**：`NEXT_PUBLIC_API_URL` 是前端浏览器访问后端 API 的地址。在生产环境中，你应该为 Server 服务配置一个域名，并使用 HTTPS。

## 5. 域名与端口映射

部署成功后，你需要让外部能访问 Web 和 Server。

1. **Web 服务**:
   - 在 Compose 的 Services 列表中找到 `web`。
   - 添加域名 (Domains)，例如 `goods.yourdomain.com`。
   - 容器端口 (Container Port) 设置为 `3000`。

2. **Server 服务**:
   - 在 Compose 的 Services 列表中找到 `server`。
   - 添加域名，例如 `api.yourdomain.com`。
   - 容器端口设置为 `8000`。

## 6. 常见问题

### 数据库迁移
系统启动时会自动检测并创建表结构。如果是第一次部署，Postgres 数据库是空的，系统会自动初始化 `task_status` 和 `config` 表。`goods` 表会在第一次抓取数据或导入数据时创建。

### 自动化抓取
Server 容器内置了 Playwright 和 Chromium。抓取任务在后台运行。
可以通过查看 Server 容器的日志来监控抓取进度。

### 重新部署
代码更新后，在 Compose 页面点击 "Redeploy" 即可。

### 持久化存储
Postgres 数据存储在 Docker Volume `postgres_data` 中，重启容器不会丢失数据。
Server 的 `data` 目录也挂载了 Volume，用于存储临时文件。
