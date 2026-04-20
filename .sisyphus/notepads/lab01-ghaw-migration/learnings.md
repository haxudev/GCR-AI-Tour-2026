# Learnings — lab01-ghaw-migration

## 2026-04-07 Session Init

### Pipeline Data Flow (exact, from workflow.yaml)
1. `tech.fetch_all_to_disk(source_list_path, signals_dir, timeout_seconds=15, max_chars=200000, max_items_per_source=25)` → disk
2. `tech.load_articles_from_disk(signals_dir, source_list_path, max_items_per_source=25, time_window_hours=24)` → RawSignals JSON
3. Save `raw_signals.json`
4. LLM: HotspotClusteringAgent prompt → ClustersCandidate
5. `tech.cluster_or_fallback(raw_signals_json, clusters_json, top_k=12)` → HotspotClusters
6. Save `clusters/hotspots.json`
7. LLM: InsightAgent prompt → InsightsCandidate
8. `tech.insight_or_fallback(clusters_json, insights_json)` → HotspotInsights
9. Save `insights/insights.json`
10. LLM: ContentStrategyAgent (report) prompt → ReportCandidate
11. `tech.render_report_or_fallback(clusters_json, insights_json, draft_markdown)` → FinalMarkdown
12. Save `output/report.md` AND `frontend/report.md`

### Default Config Values (from workflow.yaml)
- SourceListPath: `input/api/rss_list.json`
- TimeWindowHours: `24`
- TopK: `12`
- MaxItemsPerSource: `25`
- TimeoutSeconds: `15`
- MaxChars: `200000`
- Language: `zh-CN`

### 6 Registered Tool Names (tech_insight_tools.py:947-952)
- `tech.read_source_list`
- `tech.fetch_all_to_disk`
- `tech.load_articles_from_disk`
- `tech.cluster_or_fallback`
- `tech.insight_or_fallback`
- `tech.render_report_or_fallback`
- Plus: `write_text_file` (from shared_tools/file_io_tool.py)

### tech_insight_tools.py imports (pure Python, zero Azure)
- json, math, re, time, dataclasses, datetime, pathlib, typing, urllib.parse
- httpx (HTTP client)
- No Azure imports whatsoever

### Current requirements.txt Azure packages to REMOVE
- --pre
- agent-framework
- agent-framework-azure-ai
- azure-identity
- azure-ai-projects
- azure-ai-agents
- azure-core
- openai (not needed for gh-aw tools)

### Current requirements.txt packages to KEEP
- python-dotenv
- PyYAML
- httpx
- feedparser
- beautifulsoup4

### Azure files to DELETE
- generated/tech_insight_workflow/run.py
- generated/tech_insight_workflow/maf_declarative_runtime.py
- generated/tech_insight_workflow/create_agents_from_workflow.py
- generated/tech_insight_workflow/agent_id_map.json
- generated/tech_insight_workflow/agents.yaml
- generated/tech_insight_workflow/workflow.yaml
- scripts/setup_github_actions_oidc.sh
- scripts/setup_github_actions_oidc.ps1
- scripts/install_deps.sh
- scripts/install_deps.ps1
- .github/workflows/deploy_frontend_swa.yml (in repo root)

### Files to NOT touch
- generated/tech_insight_workflow/tech_insight_tools.py (will be COPIED to mcp-scripts/ in Task 7)
- generated/tech_insight_workflow/social_insight_tools.py (out of scope)
- shared_tools/ (restructured in Task 7, not Task 5)
- input/ (zero changes)
- frontend/ (zero changes)

### Chinese LLM Prompts (from workflow.yaml)
Stage 2 - Clustering:
```
你是 Tech Hotspot Clustering Agent。
任务：把过去 {time_window_hours} 小时内的文章信号聚合成可行动的主题/更新列表。
...
```
Stage 3 - Insight:
```
你是 Tech Insight Agent。任务：针对每个热点输出"发生了什么/为什么重要/影响谁/接下来怎么做"。
...
```
Stage 4 - Report:
```
你是 Tech Report Writer。
请基于聚类与洞察生成一份 Markdown 报告（中英混合可接受，但以中文为主），结构包含：
- 24h 摘要、Cross-source Trends、High-signal Singles、Company Radar、DevTools Releases、Research Watch
...
```


## 2026-04-07 Workflow Markdown Port
- Created `.github/workflows/tech-insight.md` as gh-aw workflow frontmatter + markdown body.
- Frontmatter uses manual trigger only: `workflow_dispatch` with `permissions.contents: write`, `engine: copilot`, and `network: true`.
- Included all 7 MCP script paths under `Lab-01-Tech-Insights/mcp-scripts/` and referenced all 6 required `tech.*` tool names in body instructions.
- Ported the clustering, insight, and report Chinese prompts directly from `generated/tech_insight_workflow/workflow.yaml` and required fallback disclosure in every stage.
- Final stage instructs writing both `Lab-01-Tech-Insights/output/report.md` and `frontend/report.md`, then committing `frontend/report.md` via safe-outputs.
