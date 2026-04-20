# Lab-01：Tech Insights — GitHub Agentic Workflows

本实验展示了如何利用 GitHub Agentic Workflows (gh-aw) 构建一个自动化的技术洞察流水线：从 60 多个 RSS/Sitemap 源抓取数据，通过 LLM 进行聚类与分析，最终生成中文技术周报。

## 概述

该工作流实现了从原始信号抓取到最终报告生成的自动化闭环，主要流程包括：信号聚合 → 热点聚类 → 深度洞察 → 中文 Markdown 报告生成。

## 工作流架构

