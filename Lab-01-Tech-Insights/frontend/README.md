# Frontend (GitHub Pages)

这是一个极简静态页面：在浏览器端把 `report.md` 渲染成可阅读的 HTML。

## 本地预览（零安装）

仓库根目录执行：

- `python3 -m http.server 8000 --directory Lab-01-Tech-Insights/frontend`
- 浏览器打开：`http://localhost:8000`

> 说明：直接双击打开 `index.html` 在部分浏览器会触发跨域限制，导致 `fetch(report.md)` 失败；用本地静态服务器即可。

## 使用方式

- 默认渲染：`report.md`（与 `index.html` 同目录）

## 部署到 GitHub Pages

本仓库使用 GitHub Pages 进行部署，无需额外的云服务。

### 开启方式

1. 打开仓库 → **Settings** → 左侧 **Pages**。
2. Source 选择 **GitHub Actions**。
3. 手动触发 `Deploy GitHub Pages` 工作流（`.github/workflows/deploy-pages.yml`）。

### 自动部署

当 `Lab-01-Tech-Insights/frontend/` 下的文件发生变更并推送到 `main` 分支时，`deploy-pages.yml` 会自动触发部署。

Tech Insight Workflow 每次运行后会将最新的 `report.md` 写入 `Lab-01-Tech-Insights/frontend/report.md`，从而自动触发 Pages 重新部署。

### 访问地址

部署成功后，访问：`https://<你的用户名>.github.io/<仓库名>/`
