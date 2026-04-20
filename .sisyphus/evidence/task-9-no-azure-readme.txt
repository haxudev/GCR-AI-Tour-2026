# Lab-01：Tech Insights — GitHub Agentic Workflows

本实验展示了如何利用 GitHub Agentic Workflows (gh-aw) 构建一个自动化的技术洞察流水线：从 60 多个 RSS/Sitemap 源抓取数据，通过 LLM 进行聚类与分析，最终生成中文技术周报。

## 概述

该工作流实现了从原始信号抓取到最终报告生成的自动化闭环，主要流程包括：信号聚合 → 热点聚类 → 深度洞察 → 中文 Markdown 报告生成。

## 工作流架构

```
RSS/Sitemap/HTML 源 (60+)
    ↓
MCP Scripts (数据工具)
    ↓ raw_signals.json
LLM + cluster_or_fallback
    ↓ hotspots.json
LLM + insight_or_fallback
    ↓ insights.json
LLM + render_report_or_fallback
    ↓ report.md
GitHub Pages
```

## 前置条件

- 已安装 GitHub CLI (gh) 及其 gh-aw 扩展
- Python 3.10+ 环境

## 快速开始

```bash
# 编译 gh-aw 工作流
gh aw compile .github/workflows/tech-insight.md

# 通过 GitHub Actions UI 手动触发，或使用 CLI：
gh workflow run tech-insight
```

## 目录结构

```
Lab-01-Tech-Insights/
  mcp-scripts/          # MCP Script 工具包装器（Python 实现）
  input/api/rss_list.json  # 包含 60+ 技术数据源的列表
  frontend/             # 报告静态展示前端
  output/               # 运行时产生的中间件与结果输出目录（不纳入版本控制）
.github/workflows/
  tech-insight.md       # gh-aw 工作流定义文件
  deploy-pages.yml      # GitHub Pages 自动部署脚本
```

## 工作流流程 (4-stage pipeline)

该流水线分为四个核心阶段：

- **阶段 1：信号抓取**
  调用 tech.fetch_all_to_disk 将 60 多个源的内容抓取并保存到本地磁盘，随后由 tech.load_articles_from_disk 过滤并生成标准的原始信号 JSON。
- **阶段 2：热点聚类**
  利用 LLM 对原始信号进行语义聚类，并使用 tech.cluster_or_fallback 进行结构验证与兜底处理，输出 hotspots.json。
- **阶段 3：洞察生成**
  LLM 针对每个热点分析“发生了什么、为什么重要、影响谁、建议做法”，通过 tech.insight_or_fallback 确保输出质量。
- **阶段 4：报告生成**
  将聚类与洞察结果整合，由 LLM 渲染成易读的 Markdown 报告，同步至 frontend/report.md 并触发 GitHub Pages 更新。

## MCP Scripts

工作流使用的核心工具列表：

| 脚本 | 说明 |
|------|------|
| tech_read_source_list.py | 读取 RSS/Sitemap 源列表配置 |
| tech_fetch_all_to_disk.py | 并行抓取所有数据源内容并落盘 |
| tech_load_articles_from_disk.py | 从本地文件加载并过滤有效文章信号 |
| tech_cluster_or_fallback.py | 执行聚类结果的 JSON 验证与逻辑兜底 |
| tech_insight_or_fallback.py | 执行洞察分析的 JSON 验证与逻辑兜底 |
| tech_render_report_or_fallback.py | 确保 Markdown 报告符合预期格式 |
| write_text_file.py | 通用的文件写入工具 |

## 配置

本地调试时，可以参考 .env.example 配置必要的环境变量（如 GitHub Token 等），确保 gh-aw 能够调用 Copilot LLM 能力。

## 输出结果

- **Markdown 报告**: 位于 frontend/report.md
- **在线查看**: 部署成功后，可通过仓库的 GitHub Pages URL 访问。

## 本地开发

你可以直接运行 mcp-scripts/ 下的脚本进行工具逻辑测试，例如：

```bash
python Lab-01-Tech-Insights/mcp-scripts/tech_read_source_list.py Lab-01-Tech-Insights/input/api/rss_list.json
```
