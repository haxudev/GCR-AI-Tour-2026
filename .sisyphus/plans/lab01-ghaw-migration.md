# Lab-01 Tech Insights: Azure AI Foundry → GitHub Agentic Workflows Migration

## TL;DR

> **Quick Summary**: Migrate Lab-01-Tech-Insights from Azure AI Foundry + MAF (Microsoft Agent Framework) to GitHub Agentic Workflows (gh-aw). Remove ALL Azure dependencies, replace the MAF declarative YAML workflow engine with a gh-aw markdown workflow, convert the pure-Python data tools into MCP Scripts, and rewrite all documentation.
> 
> **Deliverables**:
> - gh-aw markdown workflow file (`.github/workflows/tech-insight.md`) replacing MAF YAML
> - MCP Script wrappers for the 6 tech insight tools + file_io tool
> - Cleaned `requirements.txt` (Azure-free)
> - Updated GitHub Actions trigger workflow
> - Fully rewritten README and configuration files
> - All Azure-specific files deleted
> 
> **Estimated Effort**: Medium-Large
> **Parallel Execution**: YES - 4 waves
> **Critical Path**: Task 1 (gh-aw workflow) → Task 3 (MCP scripts) → Task 7 (GitHub Actions) → Task 9 (end-to-end verification) → F1-F4

---

## Context

### Original Request
User needs to completely remove Azure dependencies from Lab-01-Tech-Insights because Azure accounts are unavailable. Replace the entire Lab architecture with GitHub Agentic Workflows (gh-aw), referencing https://github.com/github/gh-aw.

### Interview Summary
**Key Discussions**:
- Current Lab uses 4-agent pipeline: SignalIngestion → HotspotClustering → Insight → ContentStrategy
- MAF declarative YAML runtime orchestrates the pipeline (571-line custom engine)
- 60+ RSS/Sitemap/HTML data sources for tech signal ingestion (pure Python, zero Azure deps)
- Azure AI Foundry Agents provide LLM reasoning (clustering, insights, report generation)
- Only 3 actual LLM calls in the pipeline — rest is deterministic tool execution
- `tech_insight_tools.py` (952 lines) is the crown jewel — pure Python, fully reusable
- Pipeline data flow: raw_signals.json → hotspots.json → insights.json → report.md

**Research Findings**:
- gh-aw uses markdown files with YAML frontmatter as workflow definitions
- gh-aw supports MCP Scripts (Python/Node scripts exposed as tools to the AI engine)
- gh-aw has DailyOps pattern perfect for scheduled tech signal analysis
- gh-aw workflows compiled via `gh aw compile` into `.lock.yml` files
- gh-aw AI engines: Copilot (default), Claude, Codex — all handle Chinese well
- gh-aw networking: outbound HTTP allowed (needed for RSS fetching)
- gh-aw safe-outputs: can commit files, create issues, PRs
- The 4-agent pipeline becomes single-agent natural language instructions in gh-aw
- MCP Scripts can execute Python with dependencies (httpx, feedparser, bs4)

### Metis Review
**Identified Gaps** (addressed):
- Social insight workflow (social_insight_tools.py, social_insight_workflow.yaml) explicitly excluded from scope
- gh-aw MCP Script networking/disk I/O capabilities need validation as first task
- Loss of mock mode for local development — mitigated by deterministic fallback tools
- `shared_tools/maf_shared_tools_registry.py` auto-discovery of `social_insight_tools.py` — harmless but confusing
- Report language is Chinese (zh-CN) — must be preserved in gh-aw prompts
- `generated/` directory name is misleading post-migration — restructure to `mcp-scripts/`
- The `.env.example` mentions "Social Insight workflow" in comments — stale naming needs cleanup

---

## Work Objectives

### Core Objective
Replace the Azure AI Foundry + MAF architecture with GitHub Agentic Workflows while preserving the exact same data pipeline behavior: 60+ tech signal sources → clustering → insights → Markdown report.

### Concrete Deliverables
- `.github/workflows/tech-insight.md` — gh-aw workflow definition (YAML frontmatter + natural language instructions)
- `.github/workflows/tech-insight.lock.yml` — compiled gh-aw workflow
- `Lab-01-Tech-Insights/mcp-scripts/` — MCP Script wrappers for all 6 tech insight tools + file_io
- `Lab-01-Tech-Insights/requirements.txt` — cleaned, Azure-free
- `Lab-01-Tech-Insights/.env.example` — gh-aw compatible (or deleted if unnecessary)
- `Lab-01-Tech-Insights/README.md` — fully rewritten for gh-aw
- Root `README.md` — Lab-01 section updated
- 10+ Azure-specific files deleted

### Definition of Done
- [ ] `grep -ri "azure" Lab-01-Tech-Insights/ --include="*.py" --include="*.txt" --include="*.yaml" --include="*.yml" --include="*.json" --include="*.sh" --include="*.ps1" | grep -v README | grep -v ".md"` returns zero lines
- [ ] `grep -ri "foundry" Lab-01-Tech-Insights/ --include="*.py" --include="*.txt" --include="*.yaml" --include="*.yml" | grep -v README | grep -v ".md"` returns zero lines
- [ ] `pip install -r Lab-01-Tech-Insights/requirements.txt` succeeds without any Azure packages
- [ ] gh-aw workflow file compiles successfully via `gh aw compile`
- [ ] `frontend/report.md` structure preserved (Markdown with required sections)
- [ ] All deleted files confirmed absent from filesystem

### Must Have
- gh-aw markdown workflow that replicates the exact 4-stage pipeline (signals → clusters → insights → report)
- MCP Script wrappers that expose all 6 tech insight tools to gh-aw AI engine
- Chinese (zh-CN) preserved in all LLM prompts and report output
- LLM fallback pattern preserved: LLM-first → tool validates → deterministic fallback
- Intermediate artifacts preserved: raw_signals.json, hotspots.json, insights.json, report.md
- `input/api/rss_list.json` untouched (60+ sources)
- `frontend/` directory untouched (HTML/JS/CSS viewer)
- `tech_insight_tools.py` core logic untouched — only wrapped as MCP scripts

### Must NOT Have (Guardrails)
- **NO social insight workflow migration** — `social_insight_workflow.yaml` and `social_insight_tools.py` are out of scope
- **NO modifications to `tech_insight_tools.py` function signatures or logic** — only wrap as MCP scripts
- **NO changes to RSS source list** (`rss_list.json`) — zero modifications
- **NO changes to report output format** — same Markdown structure with same sections
- **NO changes to frontend viewer logic** — `index.html`, `main.js`, `styles.css` untouched
- **NO new AI capabilities** — no summarization, translation, or features not in original pipeline
- **NO Azure fallback paths** — complete removal, no optional Azure mode
- **NO restructuring of the 4-stage pipeline concept** (signals → clusters → insights → report)
- **NO authentication/secrets management** beyond what gh-aw provides natively

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** - ALL verification is agent-executed. No exceptions.
> Acceptance criteria requiring "user manually tests/confirms" are FORBIDDEN.

### Test Decision
- **Infrastructure exists**: NO (this is a Lab/workshop, not a production app)
- **Automated tests**: None (workshop context — verification via agent-executed QA)
- **Framework**: N/A
- **If TDD**: N/A

### QA Policy
Every task MUST include agent-executed QA scenarios (see TODO template below).
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Workflow compilation**: Use Bash — `gh aw compile` and verify `.lock.yml` output
- **Azure removal verification**: Use Bash (grep) — confirm zero Azure references
- **File existence/absence**: Use Bash (test) — confirm files created/deleted
- **Python imports**: Use Bash (python -c) — verify no import errors
- **Frontend**: Use Bash — verify `report.md` exists and has expected structure

---

## Execution Strategy

### Parallel Execution Waves

> Maximize throughput by grouping independent tasks into parallel waves.
> Each wave completes before the next begins.

```
Wave 1 (Start Immediately — foundation + scaffolding):
├── Task 1: Create gh-aw workflow markdown file [deep]
├── Task 2: Create MCP Script directory structure + wrapper entry points [quick]
├── Task 3: Clean requirements.txt (remove Azure packages) [quick]
├── Task 4: Replace .env.example with gh-aw config [quick]
└── Task 5: Delete all Azure-only files (scripts, agents, runtime) [quick]

Wave 2 (After Wave 1 — integration + CI):
├── Task 6: Rewrite GitHub Actions workflow for gh-aw trigger [unspecified-high]
├── Task 7: Restructure directory layout (generated/ → mcp-scripts/) [quick]
└── Task 8: Handle social insight orphaned files (cleanup) [quick]

Wave 3 (After Wave 2 — documentation):
├── Task 9: Rewrite Lab-01 README.md for gh-aw [writing]
└── Task 10: Update root README.md Lab-01 section [quick]

Wave 4 (After Wave 3 — end-to-end verification):
└── Task 11: End-to-end verification (compile, grep, import checks) [deep]

Wave FINAL (After ALL tasks — 4 parallel reviews, then user okay):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)
-> Present results -> Get explicit user okay
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | - | 6, 11 | 1 |
| 2 | - | 6, 7, 11 | 1 |
| 3 | - | 11 | 1 |
| 4 | - | 9, 11 | 1 |
| 5 | - | 7, 8, 9, 11 | 1 |
| 6 | 1, 2 | 11 | 2 |
| 7 | 2, 5 | 9, 11 | 2 |
| 8 | 5 | 11 | 2 |
| 9 | 4, 5, 7 | 11 | 3 |
| 10 | - | 11 | 3 |
| 11 | ALL 1-10 | F1-F4 | 4 |
| F1-F4 | 11 | user okay | FINAL |

### Agent Dispatch Summary

- **Wave 1**: **5 tasks** — T1 → `deep`, T2 → `quick`, T3 → `quick`, T4 → `quick`, T5 → `quick`
- **Wave 2**: **3 tasks** — T6 → `unspecified-high`, T7 → `quick`, T8 → `quick`
- **Wave 3**: **2 tasks** — T9 → `writing`, T10 → `quick`
- **Wave 4**: **1 task** — T11 → `deep`
- **FINAL**: **4 tasks** — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

> Implementation + Verification = ONE Task. Never separate.
> EVERY task MUST have: Recommended Agent Profile + Parallelization info + QA Scenarios.

- [x] 1. Create gh-aw Workflow Markdown File

  **What to do**:
  - Create `.github/workflows/tech-insight.md` — the core gh-aw workflow definition
  - YAML frontmatter section must include:
    - `name: Tech Insight Pipeline`
    - `on: workflow_dispatch` (manual trigger only — no scheduled runs)
    - `permissions: contents: write` (to commit report.md)
    - `tools:` section listing all MCP scripts from `Lab-01-Tech-Insights/mcp-scripts/`
    - `engine: copilot` (default AI engine)
    - `network: true` (outbound HTTP for RSS fetching)
  - Markdown body must contain natural language instructions that replicate the exact 4-stage pipeline:
    - **Stage 1 — Signal Ingestion**: Call `tech.read_source_list` to get source list, then call `tech.fetch_all_to_disk` with the source list path and output directory. Call `tech.load_articles_from_disk` to normalize and filter signals by 24h time window. Save result as `raw_signals.json`.
    - **Stage 2 — Hotspot Clustering**: Analyze the raw signals and identify technology hotspot clusters. Group signals by topic similarity, technology relevance, and temporal proximity. Output JSON with cluster name, signal count, representative signals, and trend score. Pass result to `tech.cluster_or_fallback` for validation. Save validated result as `hotspots.json`.
    - **Stage 3 — Insight Generation**: For each hotspot cluster, generate actionable insights: why this matters, who is affected, what to watch next. Pass result to `tech.insight_or_fallback` for validation. Save validated result as `insights.json`.
    - **Stage 4 — Report Rendering**: Generate a comprehensive Chinese (zh-CN) Markdown report with sections: 24小时技术动态总览, 跨源趋势, 高信号单条, 公司雷达, DevTools 新版发布, 研究观察. Pass to `tech.render_report_or_fallback` for validation. Save final `report.md` to `frontend/report.md`.
  - All LLM prompts MUST be in Chinese (zh-CN) — directly port from existing `workflow.yaml` prompts
  - Each stage must explicitly instruct: "If the tool indicates a fallback was used, note it in the output"
  - Final step: commit `frontend/report.md` to the repository using safe-outputs

  **Must NOT do**:
  - Do NOT modify the pipeline stages or add new capabilities
  - Do NOT change the report section structure
  - Do NOT use English for LLM prompts (must be zh-CN)
  - Do NOT hardcode file paths — use relative paths from Lab-01-Tech-Insights/

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: This is the core architectural artifact — requires deep understanding of gh-aw workflow syntax, careful porting of Chinese prompts, and precise tool integration
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `microsoft-foundry`: Not relevant — we're removing Azure, not deploying to it

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3, 4, 5)
  - **Blocks**: Tasks 6, 11
  - **Blocked By**: None (can start immediately)

  **References** (CRITICAL):

  **Pattern References** (existing code to follow):
  - `Lab-01-Tech-Insights/generated/tech_insight_workflow/workflow.yaml:1-301` — The exact pipeline sequence, variable names, and Chinese prompts to port. This is the SOURCE OF TRUTH for what the gh-aw workflow must replicate.
  - `Lab-01-Tech-Insights/generated/tech_insight_workflow/agents.yaml:1-13` — Agent roles and instruction strings. These become natural language sections in the gh-aw markdown.

  **API/Type References** (contracts to implement against):
  - `Lab-01-Tech-Insights/generated/tech_insight_workflow/tech_insight_tools.py:942-952` — The 6 registered tool names and their exact function signatures. The gh-aw workflow must call these via MCP script names.
  - `Lab-01-Tech-Insights/generated/tech_insight_workflow/tech_insight_tools.py:72-150` — `tech_fetch_all_to_disk` function signature and parameters (source_list_path, signals_dir, timeout_seconds, max_items_per_source)
  - `Lab-01-Tech-Insights/generated/tech_insight_workflow/tech_insight_tools.py:250-350` — `tech_cluster_or_fallback` and `tech_insight_or_fallback` — the fallback validation pattern

  **External References** (gh-aw documentation):
  - https://github.github.com/gh-aw/setup/creating-workflows/ — Workflow creation syntax
  - https://github.github.com/gh-aw/reference/workflow-structure/ — YAML frontmatter schema
  - https://github.github.com/gh-aw/patterns/daily-ops/ — DailyOps pattern (schedule + data processing)
  - https://github.github.com/gh-aw/reference/mcp-scripts/ — How MCP scripts are referenced in frontmatter
  - https://github.github.com/gh-aw/reference/safe-outputs/ — How to commit files from workflow
  - https://github.github.com/gh-aw/reference/network/ — Network access configuration
  - https://github.github.com/gh-aw/reference/engines/ — AI engine selection

  **WHY Each Reference Matters**:
  - `workflow.yaml` is the single source of truth for the pipeline logic — the gh-aw workflow must be a faithful translation
  - `agents.yaml` shows the intent/role of each agent — these become sections in the markdown instructions
  - `tech_insight_tools.py` tool signatures define the MCP script interface — the workflow must call them with correct parameters
  - gh-aw docs provide the exact syntax for frontmatter, triggers, tools, and safe-outputs

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Workflow file has valid structure
    Tool: Bash
    Preconditions: `.github/workflows/tech-insight.md` exists
    Steps:
      1. Read the file and verify it starts with `---` (YAML frontmatter delimiter)
      2. Verify frontmatter contains `name:`, `on:`, `permissions:`, `tools:` keys
      3. Verify frontmatter contains `network: true`
      4. Verify markdown body contains all 4 stage headers (Signal Ingestion, Clustering, Insight, Report)
      5. Verify markdown body contains Chinese text (grep for Chinese characters)
    Expected Result: All 5 checks pass — file has valid frontmatter + 4 pipeline stages + Chinese content
    Failure Indicators: Missing frontmatter keys, missing pipeline stages, English-only content
    Evidence: .sisyphus/evidence/task-1-workflow-structure.txt

  Scenario: Workflow references all 6 MCP script tools
    Tool: Bash (grep)
    Preconditions: `.github/workflows/tech-insight.md` exists
    Steps:
      1. grep for "tech.read_source_list" in the workflow file
      2. grep for "tech.fetch_all_to_disk" in the workflow file
      3. grep for "tech.load_articles_from_disk" in the workflow file
      4. grep for "tech.cluster_or_fallback" in the workflow file
      5. grep for "tech.insight_or_fallback" in the workflow file
      6. grep for "tech.render_report_or_fallback" in the workflow file
    Expected Result: All 6 tool names found in the workflow file
    Failure Indicators: Any tool name missing from workflow
    Evidence: .sisyphus/evidence/task-1-tool-references.txt

  Scenario: Workflow has manual trigger only
    Tool: Bash (grep)
    Preconditions: `.github/workflows/tech-insight.md` exists
    Steps:
      1. grep for "workflow_dispatch" in the frontmatter section
      2. grep for "schedule" in the frontmatter section — should NOT be present
    Expected Result: workflow_dispatch present, no schedule trigger
    Failure Indicators: Missing manual trigger or unexpected schedule trigger
    Evidence: .sisyphus/evidence/task-1-triggers.txt
  ```

  **Evidence to Capture:**
  - [ ] task-1-workflow-structure.txt — frontmatter validation output
  - [ ] task-1-tool-references.txt — grep results for all 6 tools
  - [ ] task-1-triggers.txt — trigger configuration verification

  **Commit**: YES (Commit 1)
  - Message: `feat(lab01): add gh-aw workflow definition for tech-insight pipeline`
  - Files: `.github/workflows/tech-insight.md`
  - Pre-commit: `grep -c "tech\." .github/workflows/tech-insight.md` → expect 6+

- [x] 2. Create MCP Script Wrappers for Tech Insight Tools

  **What to do**:
  - Create directory `Lab-01-Tech-Insights/mcp-scripts/`
  - Create MCP Script wrapper files that expose each of the 6 tech insight tools + file_io tool to gh-aw:
    - `mcp-scripts/tech_read_source_list.py` — wraps `tech.read_source_list`
    - `mcp-scripts/tech_fetch_all_to_disk.py` — wraps `tech.fetch_all_to_disk`
    - `mcp-scripts/tech_load_articles_from_disk.py` — wraps `tech.load_articles_from_disk`
    - `mcp-scripts/tech_cluster_or_fallback.py` — wraps `tech.cluster_or_fallback`
    - `mcp-scripts/tech_insight_or_fallback.py` — wraps `tech.insight_or_fallback`
    - `mcp-scripts/tech_render_report_or_fallback.py` — wraps `tech.render_report_or_fallback`
    - `mcp-scripts/write_text_file.py` — wraps `write_text_file` from shared_tools
  - Each MCP Script must:
    - Follow gh-aw MCP Script conventions (see external references)
    - Import and call the corresponding function from `tech_insight_tools.py` (which will be moved to this directory in Task 7)
    - Accept parameters as JSON stdin or CLI args per gh-aw convention
    - Return results as JSON stdout
    - Include a `requirements.txt` or inline dependency declaration for `httpx`, `feedparser`, `beautifulsoup4`
  - Create `mcp-scripts/requirements.txt` with: `httpx`, `feedparser`, `beautifulsoup4`, `PyYAML`
  - Do NOT modify the underlying tool functions — only create thin wrapper entry points

  **Must NOT do**:
  - Do NOT modify `tech_insight_tools.py` function signatures or logic
  - Do NOT add new tools not in the original pipeline
  - Do NOT add Azure SDK dependencies

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Thin wrappers around existing functions — straightforward Python scripting
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3, 4, 5)
  - **Blocks**: Tasks 6, 7, 11
  - **Blocked By**: None

  **References** (CRITICAL):

  **Pattern References**:
  - `Lab-01-Tech-Insights/generated/tech_insight_workflow/tech_insight_tools.py:942-952` — Tool registration showing exact function names and their mapping
  - `Lab-01-Tech-Insights/generated/tech_insight_workflow/tech_insight_tools.py:1-70` — Imports and helper functions used by tools
  - `Lab-01-Tech-Insights/shared_tools/file_io_tool.py:1-31` — The `write_text_file` function to wrap

  **External References**:
  - https://github.github.com/gh-aw/reference/mcp-scripts/ — MCP Script format, conventions, input/output
  - https://github.github.com/gh-aw/llms.txt — Full gh-aw reference for LLM consumption

  **WHY Each Reference Matters**:
  - `tech_insight_tools.py:942-952` shows the exact tool names and function signatures to wrap
  - `file_io_tool.py` is the shared tool that needs its own wrapper
  - gh-aw MCP Script docs define the exact format (shebang, stdin/stdout, metadata)

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: All 7 MCP script files exist
    Tool: Bash (test)
    Preconditions: Task 2 completed
    Steps:
      1. test -f Lab-01-Tech-Insights/mcp-scripts/tech_read_source_list.py
      2. test -f Lab-01-Tech-Insights/mcp-scripts/tech_fetch_all_to_disk.py
      3. test -f Lab-01-Tech-Insights/mcp-scripts/tech_load_articles_from_disk.py
      4. test -f Lab-01-Tech-Insights/mcp-scripts/tech_cluster_or_fallback.py
      5. test -f Lab-01-Tech-Insights/mcp-scripts/tech_insight_or_fallback.py
      6. test -f Lab-01-Tech-Insights/mcp-scripts/tech_render_report_or_fallback.py
      7. test -f Lab-01-Tech-Insights/mcp-scripts/write_text_file.py
    Expected Result: All 7 files exist (exit code 0 for each)
    Failure Indicators: Any file missing
    Evidence: .sisyphus/evidence/task-2-files-exist.txt

  Scenario: MCP scripts have valid Python syntax
    Tool: Bash (python -m py_compile)
    Preconditions: All 7 MCP script files exist
    Steps:
      1. python -m py_compile Lab-01-Tech-Insights/mcp-scripts/tech_read_source_list.py
      2. python -m py_compile Lab-01-Tech-Insights/mcp-scripts/tech_fetch_all_to_disk.py
      3. (repeat for all 7 scripts)
    Expected Result: All compile without syntax errors
    Failure Indicators: SyntaxError from py_compile
    Evidence: .sisyphus/evidence/task-2-syntax-check.txt

  Scenario: MCP scripts requirements.txt exists and has no Azure packages
    Tool: Bash
    Preconditions: Task 2 completed
    Steps:
      1. test -f Lab-01-Tech-Insights/mcp-scripts/requirements.txt
      2. grep -c "azure" Lab-01-Tech-Insights/mcp-scripts/requirements.txt
      3. grep "httpx" Lab-01-Tech-Insights/mcp-scripts/requirements.txt
      4. grep "feedparser" Lab-01-Tech-Insights/mcp-scripts/requirements.txt
      5. grep "beautifulsoup4" Lab-01-Tech-Insights/mcp-scripts/requirements.txt
    Expected Result: File exists, zero azure references, httpx/feedparser/bs4 present
    Failure Indicators: Missing requirements file, Azure packages present, missing core deps
    Evidence: .sisyphus/evidence/task-2-requirements.txt
  ```

  **Evidence to Capture:**
  - [ ] task-2-files-exist.txt
  - [ ] task-2-syntax-check.txt
  - [ ] task-2-requirements.txt

  **Commit**: YES (Commit 2)
  - Message: `feat(lab01): convert tech insight tools to MCP scripts`
  - Files: `Lab-01-Tech-Insights/mcp-scripts/*`
  - Pre-commit: `ls Lab-01-Tech-Insights/mcp-scripts/*.py | wc -l` → expect 7

- [x] 3. Clean requirements.txt — Remove Azure Dependencies

  **What to do**:
  - Edit `Lab-01-Tech-Insights/requirements.txt`
  - Remove ALL Azure-related packages:
    - `azure-identity`
    - `azure-ai-projects`
    - `azure-ai-agents`
    - `azure-core`
    - `agent-framework`
    - `agent-framework-azure-ai`
    - Any other `azure-*` packages
  - Keep ONLY the pure Python dependencies needed by `tech_insight_tools.py`:
    - `httpx` — HTTP client for RSS/sitemap fetching
    - `feedparser` — RSS/Atom feed parsing
    - `beautifulsoup4` — HTML parsing
    - `PyYAML` — YAML parsing
    - `python-dotenv` — .env file loading
    - `lxml` (if used by bs4)
  - Verify no Azure imports remain by checking `tech_insight_tools.py` imports

  **Must NOT do**:
  - Do NOT add new dependencies not needed by the existing tools
  - Do NOT remove non-Azure dependencies that tools actually use

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Single file edit — remove lines from a requirements file
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 4, 5)
  - **Blocks**: Task 11
  - **Blocked By**: None

  **References** (CRITICAL):

  **Pattern References**:
  - `Lab-01-Tech-Insights/requirements.txt:1-20` — Current requirements file showing which packages to remove vs keep
  - `Lab-01-Tech-Insights/generated/tech_insight_workflow/tech_insight_tools.py:1-30` — Import statements showing actual dependencies used

  **WHY Each Reference Matters**:
  - `requirements.txt` is the file being edited — executor needs to see current state
  - `tech_insight_tools.py` imports prove which dependencies are actually used by the tools

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Zero Azure packages in requirements.txt
    Tool: Bash (grep)
    Preconditions: requirements.txt has been edited
    Steps:
      1. grep -i "azure" Lab-01-Tech-Insights/requirements.txt
      2. grep -i "agent-framework" Lab-01-Tech-Insights/requirements.txt
      3. grep -i "foundry" Lab-01-Tech-Insights/requirements.txt
    Expected Result: All 3 greps return no matches (exit code 1)
    Failure Indicators: Any Azure/agent-framework/foundry package still present
    Evidence: .sisyphus/evidence/task-3-no-azure-deps.txt

  Scenario: Core dependencies preserved
    Tool: Bash (grep)
    Preconditions: requirements.txt has been edited
    Steps:
      1. grep "httpx" Lab-01-Tech-Insights/requirements.txt
      2. grep "feedparser" Lab-01-Tech-Insights/requirements.txt
      3. grep "beautifulsoup4" Lab-01-Tech-Insights/requirements.txt
    Expected Result: All 3 core deps present
    Failure Indicators: Any core dependency accidentally removed
    Evidence: .sisyphus/evidence/task-3-core-deps.txt
  ```

  **Commit**: YES (Commit 3)
  - Message: `chore(lab01): remove Azure dependencies from requirements.txt`
  - Files: `Lab-01-Tech-Insights/requirements.txt`
  - Pre-commit: `grep -ic "azure" Lab-01-Tech-Insights/requirements.txt` → expect 0

- [x] 4. Replace .env.example with gh-aw Compatible Configuration

  **What to do**:
  - Rewrite `Lab-01-Tech-Insights/.env.example` to remove ALL Azure environment variables:
    - Remove `AZURE_AI_PROJECT_ENDPOINT`
    - Remove `AZURE_AI_MODEL_DEPLOYMENT_NAME`
    - Remove `AZURE_AI_AGENT_ID`
    - Remove any `AZURE_SPEECH_*` variables
  - Replace with minimal gh-aw compatible configuration (if needed):
    - Add comments explaining that gh-aw handles authentication natively via `COPILOT_GITHUB_TOKEN`
    - Add `OUTPUT_DIR=output` (local output directory for generated artifacts)
    - Add `SIGNALS_DIR=output/signals` (directory for fetched signal files)
    - Add `TIME_WINDOW_HOURS=24` (signal filtering window)
  - If gh-aw doesn't need a `.env.example` at all, create a minimal one with just the output config variables
  - Update comments — remove any mention of "Social Insight workflow" (stale naming from Metis review)

  **Must NOT do**:
  - Do NOT add Azure fallback configuration
  - Do NOT add API keys or secrets

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple file rewrite — replace Azure env vars with gh-aw config
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3, 5)
  - **Blocks**: Tasks 9, 11
  - **Blocked By**: None

  **References** (CRITICAL):

  **Pattern References**:
  - `Lab-01-Tech-Insights/.env.example:1-15` — Current file showing Azure vars to remove
  - `Lab-01-Tech-Insights/generated/tech_insight_workflow/workflow.yaml:20-50` — Shows variable defaults (TimeWindowHours=24, OutputDir, SignalsDir) that should be in .env

  **WHY Each Reference Matters**:
  - Current `.env.example` shows what to remove
  - `workflow.yaml` variable defaults inform what non-Azure config is actually needed

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Zero Azure references in .env.example
    Tool: Bash (grep)
    Preconditions: .env.example has been rewritten
    Steps:
      1. grep -i "azure" Lab-01-Tech-Insights/.env.example
      2. grep -i "foundry" Lab-01-Tech-Insights/.env.example
    Expected Result: Both greps return no matches (exit code 1)
    Failure Indicators: Any Azure/Foundry reference remaining
    Evidence: .sisyphus/evidence/task-4-no-azure-env.txt

  Scenario: Configuration file has useful content
    Tool: Bash
    Preconditions: .env.example has been rewritten
    Steps:
      1. test -f Lab-01-Tech-Insights/.env.example
      2. wc -l Lab-01-Tech-Insights/.env.example (verify non-empty)
      3. grep -c "=" Lab-01-Tech-Insights/.env.example (verify has key=value pairs)
    Expected Result: File exists, has content, has at least 1 configuration variable
    Failure Indicators: Empty file, no configuration variables
    Evidence: .sisyphus/evidence/task-4-env-content.txt
  ```

  **Commit**: YES (groups with Commit 7 — docs)
  - Message: grouped into `docs(lab01): rewrite .env.example and README for gh-aw`
  - Files: `Lab-01-Tech-Insights/.env.example`

- [x] 5. Delete All Azure-Only Files

  **What to do**:
  - Delete the following files from `Lab-01-Tech-Insights/`:
    - `generated/tech_insight_workflow/run.py` (928 lines — Azure invoker + MAF runner)
    - `generated/tech_insight_workflow/maf_declarative_runtime.py` (571 lines — MAF engine)
    - `generated/tech_insight_workflow/create_agents_from_workflow.py` (221 lines — Azure agent creation)
    - `generated/tech_insight_workflow/agent_id_map.json` (6 lines — Azure agent ID map)
    - `generated/tech_insight_workflow/agents.yaml` (13 lines — Azure agent definitions)
    - `generated/tech_insight_workflow/workflow.yaml` (301 lines — MAF workflow definition, replaced by gh-aw .md)
    - `scripts/setup_github_actions_oidc.sh` — Azure OIDC setup script
    - `scripts/setup_github_actions_oidc.ps1` — Azure OIDC setup (PowerShell)
    - `scripts/install_deps.sh` — Azure CLI installer
    - `scripts/install_deps.ps1` — Azure CLI installer (PowerShell)
  - Do NOT delete:
    - `generated/tech_insight_workflow/tech_insight_tools.py` — pure Python, needed for MCP scripts
    - `generated/tech_insight_workflow/social_insight_tools.py` — out of scope, leave as-is
    - `shared_tools/` — may be restructured in Task 7, don't delete here
    - `input/` — data sources, keep as-is
    - `frontend/` — viewer, keep as-is

  **Must NOT do**:
  - Do NOT delete `tech_insight_tools.py` — it's the reusable asset
  - Do NOT delete `social_insight_tools.py` — out of scope
  - Do NOT delete anything in `input/`, `frontend/`, or `shared_tools/`
  - Do NOT delete `.gitignore`

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Pure deletion task — remove files via `rm` commands
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3, 4)
  - **Blocks**: Tasks 7, 8, 9, 11
  - **Blocked By**: None

  **References** (CRITICAL):

  **Pattern References**:
  - `Lab-01-Tech-Insights/generated/tech_insight_workflow/` — Directory listing showing which files to delete vs preserve
  - `Lab-01-Tech-Insights/scripts/` — Directory listing showing Azure setup scripts to delete

  **WHY Each Reference Matters**:
  - Executor needs to verify the exact file list before deletion to avoid deleting the wrong files
  - The distinction between "delete" and "preserve" files in `generated/` is critical

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: All Azure files are deleted
    Tool: Bash (test)
    Preconditions: Deletion commands executed
    Steps:
      1. test ! -f Lab-01-Tech-Insights/generated/tech_insight_workflow/run.py
      2. test ! -f Lab-01-Tech-Insights/generated/tech_insight_workflow/maf_declarative_runtime.py
      3. test ! -f Lab-01-Tech-Insights/generated/tech_insight_workflow/create_agents_from_workflow.py
      4. test ! -f Lab-01-Tech-Insights/generated/tech_insight_workflow/agent_id_map.json
      5. test ! -f Lab-01-Tech-Insights/generated/tech_insight_workflow/agents.yaml
      6. test ! -f Lab-01-Tech-Insights/generated/tech_insight_workflow/workflow.yaml
      7. test ! -f Lab-01-Tech-Insights/scripts/setup_github_actions_oidc.sh
      8. test ! -f Lab-01-Tech-Insights/scripts/setup_github_actions_oidc.ps1
      9. test ! -f Lab-01-Tech-Insights/scripts/install_deps.sh
      10. test ! -f Lab-01-Tech-Insights/scripts/install_deps.ps1
    Expected Result: All 10 tests pass (exit code 0 — files do not exist)
    Failure Indicators: Any file still exists (exit code 1)
    Evidence: .sisyphus/evidence/task-5-files-deleted.txt

  Scenario: Preserved files still exist
    Tool: Bash (test)
    Preconditions: Deletion commands executed
    Steps:
      1. test -f Lab-01-Tech-Insights/generated/tech_insight_workflow/tech_insight_tools.py
      2. test -f Lab-01-Tech-Insights/input/api/rss_list.json
      3. test -f Lab-01-Tech-Insights/frontend/index.html
      4. test -f Lab-01-Tech-Insights/frontend/report.md
      5. test -f Lab-01-Tech-Insights/.gitignore
    Expected Result: All 5 preserved files still exist (exit code 0)
    Failure Indicators: Any preserved file accidentally deleted
    Evidence: .sisyphus/evidence/task-5-preserved-files.txt
  ```

  **Commit**: YES (Commit 4)
  - Message: `chore(lab01): remove Azure-specific files and scripts`
  - Files: 10 deletions listed above
  - Pre-commit: `test ! -f Lab-01-Tech-Insights/generated/tech_insight_workflow/run.py`

- [x] 6. Rewrite GitHub Actions Workflow for gh-aw Trigger

  **What to do**:
  - Replace or rewrite `.github/workflows/tech_insight_workflow.yml` (180 lines) to become a gh-aw trigger workflow:
    - Remove ALL Azure OIDC login steps (`azure/login@v2`, federated credentials)
    - Remove agent creation steps (`create_agents_from_workflow.py`)
    - Remove Azure-specific environment variables and secrets
    - The new workflow should simply trigger the gh-aw compiled workflow (`.github/workflows/tech-insight.lock.yml`)
    - OR, if gh-aw handles its own triggering via the compiled `.lock.yml`, delete this file entirely and rely on gh-aw's native trigger mechanism
  - Delete `.github/workflows/deploy_frontend_swa.yml` (145 lines — Azure Static Web Apps deployment)
    - This deploys to Azure SWA which is no longer available
    - Replace with GitHub Pages deployment
  - Create a simple `.github/workflows/deploy-pages.yml` that:
    - Triggers on push to main (when `frontend/report.md` changes)
    - Deploys `Lab-01-Tech-Insights/frontend/` to GitHub Pages
    - Uses `actions/upload-pages-artifact` and `actions/deploy-pages` actions

  **Must NOT do**:
  - Do NOT keep any Azure login or OIDC steps
  - Do NOT reference Azure secrets or credentials
  - Do NOT modify the gh-aw workflow file (Task 1's output)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Requires understanding gh-aw CI integration patterns and GitHub Actions workflow syntax
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7, 8)
  - **Blocks**: Task 11
  - **Blocked By**: Tasks 1, 2

  **References** (CRITICAL):

  **Pattern References**:
  - `.github/workflows/tech_insight_workflow.yml:1-180` — Current workflow showing Azure steps to remove
  - `.github/workflows/deploy_frontend_swa.yml:1-145` — Azure SWA deployment to delete

  **External References**:
  - https://github.github.com/gh-aw/setup/creating-workflows/ — How gh-aw workflows are triggered
  - https://github.github.com/gh-aw/reference/workflow-structure/ — How .lock.yml works with GitHub Actions

  **WHY Each Reference Matters**:
  - Current workflow shows the Azure steps to strip
  - gh-aw docs explain how compiled workflows integrate with GitHub Actions triggers

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: No Azure references in GitHub Actions workflows
    Tool: Bash (grep)
    Preconditions: Workflow files updated
    Steps:
      1. grep -ri "azure" .github/workflows/ --include="*.yml" --include="*.yaml"
      2. grep -ri "oidc" .github/workflows/ --include="*.yml" --include="*.yaml"
      3. grep -ri "foundry" .github/workflows/ --include="*.yml" --include="*.yaml"
    Expected Result: All greps return no matches
    Failure Indicators: Any Azure/OIDC/Foundry reference in workflow files
    Evidence: .sisyphus/evidence/task-6-no-azure-ci.txt

  Scenario: Azure SWA deployment workflow deleted and GitHub Pages workflow created
    Tool: Bash (test)
    Preconditions: Deletion and creation executed
    Steps:
      1. test ! -f .github/workflows/deploy_frontend_swa.yml
      2. test -f .github/workflows/deploy-pages.yml
      3. grep -i "azure" .github/workflows/deploy-pages.yml (should return no matches)
      4. grep "upload-pages-artifact\|deploy-pages" .github/workflows/deploy-pages.yml
    Expected Result: SWA workflow deleted, Pages workflow exists with no Azure refs and correct actions
    Failure Indicators: SWA still present, Pages missing, or Azure refs in Pages workflow
    Evidence: .sisyphus/evidence/task-6-swa-deleted.txt
  ```

  **Commit**: YES (Commit 5)
  - Message: `chore(lab01): replace GitHub Actions workflow with gh-aw trigger`
  - Files: `.github/workflows/tech_insight_workflow.yml`, `.github/workflows/deploy_frontend_swa.yml`
  - Pre-commit: `grep -ric "azure" .github/workflows/` → expect 0

- [x] 7. Restructure Directory Layout for gh-aw

  **What to do**:
  - Move `Lab-01-Tech-Insights/generated/tech_insight_workflow/tech_insight_tools.py` to `Lab-01-Tech-Insights/mcp-scripts/tech_insight_tools.py`
    - This places the core tool module alongside its MCP script wrappers (created in Task 2)
    - Update import paths in MCP script wrappers to reference the co-located module
  - Move `Lab-01-Tech-Insights/shared_tools/file_io_tool.py` to `Lab-01-Tech-Insights/mcp-scripts/file_io_tool.py`
    - Update import path in `write_text_file.py` wrapper
  - Clean up now-empty or near-empty directories:
    - If `generated/tech_insight_workflow/` only has `social_insight_tools.py` left, leave it (out of scope)
    - If `shared_tools/` is empty (after moving file_io_tool.py), consider keeping `maf_shared_tools_registry.py` IF social workflow needs it, or leaving as-is
  - Move `Lab-01-Tech-Insights/workflows/tech_insight_workflow.yaml` — this MAF YAML is replaced by the gh-aw .md file. Delete it.
    - Note: `workflows/social_insight_workflow.yaml` stays — out of scope
  - Ensure `Lab-01-Tech-Insights/mcp-scripts/` has an `__init__.py` if needed for Python imports

  **Must NOT do**:
  - Do NOT move or modify `social_insight_tools.py`
  - Do NOT move or modify `social_insight_workflow.yaml`
  - Do NOT modify `tech_insight_tools.py` logic — only move the file
  - Do NOT delete `input/` or `frontend/`

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: File moves and import path updates — straightforward
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 6, 8)
  - **Blocks**: Tasks 9, 11
  - **Blocked By**: Tasks 2, 5

  **References** (CRITICAL):

  **Pattern References**:
  - `Lab-01-Tech-Insights/generated/tech_insight_workflow/` — Directory listing to understand what remains after Task 5 deletions
  - `Lab-01-Tech-Insights/shared_tools/` — Directory listing
  - `Lab-01-Tech-Insights/mcp-scripts/` — Directory created in Task 2

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: tech_insight_tools.py moved to mcp-scripts/
    Tool: Bash (test)
    Preconditions: Move completed
    Steps:
      1. test -f Lab-01-Tech-Insights/mcp-scripts/tech_insight_tools.py
      2. test ! -f Lab-01-Tech-Insights/generated/tech_insight_workflow/tech_insight_tools.py
    Expected Result: File exists in new location, absent from old location
    Failure Indicators: File in wrong location or duplicated
    Evidence: .sisyphus/evidence/task-7-file-moves.txt

  Scenario: MCP script wrappers can import tech_insight_tools
    Tool: Bash (python)
    Preconditions: Files moved and imports updated
    Steps:
      1. cd Lab-01-Tech-Insights/mcp-scripts && python -c "import tech_insight_tools; print('OK')"
    Expected Result: Import succeeds, prints "OK"
    Failure Indicators: ImportError
    Evidence: .sisyphus/evidence/task-7-import-check.txt

  Scenario: MAF workflow YAML deleted
    Tool: Bash (test)
    Preconditions: Deletion executed
    Steps:
      1. test ! -f Lab-01-Tech-Insights/workflows/tech_insight_workflow.yaml
      2. test -f Lab-01-Tech-Insights/workflows/social_insight_workflow.yaml (preserved — out of scope)
    Expected Result: Tech workflow deleted, social workflow preserved
    Failure Indicators: Tech workflow still exists or social workflow accidentally deleted
    Evidence: .sisyphus/evidence/task-7-workflow-yaml.txt
  ```

  **Commit**: YES (Commit 6)
  - Message: `refactor(lab01): restructure directory layout for gh-aw`
  - Files: moved files, deleted `workflows/tech_insight_workflow.yaml`
  - Pre-commit: `test -f Lab-01-Tech-Insights/mcp-scripts/tech_insight_tools.py`

- [x] 8. Handle Social Insight Orphaned Files

  **What to do**:
  - Review what's left in `generated/tech_insight_workflow/` after Tasks 5 and 7:
    - `social_insight_tools.py` should be the only remaining file
    - If `__init__.py` or `__pycache__/` exist, leave them
  - Review what's left in `shared_tools/` after Task 7:
    - `maf_shared_tools_registry.py` may still exist — if social workflow uses it, leave as-is
    - `__init__.py` — leave as-is
  - Add a brief comment or README note in `generated/tech_insight_workflow/` explaining:
    - "The social_insight_tools.py file belongs to the social insight workflow which has not been migrated yet"
  - Do NOT modify, move, or delete any social insight files
  - Review `workflows/` directory — `social_insight_workflow.yaml` should still exist there

  **Must NOT do**:
  - Do NOT modify `social_insight_tools.py`
  - Do NOT modify `social_insight_workflow.yaml`
  - Do NOT delete `shared_tools/maf_shared_tools_registry.py` (social workflow may depend on it)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Minor cleanup and verification — no code changes
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 6, 7)
  - **Blocks**: Task 11
  - **Blocked By**: Task 5

  **References** (CRITICAL):

  **Pattern References**:
  - `Lab-01-Tech-Insights/generated/tech_insight_workflow/social_insight_tools.py:1-20` — Verify this file exists and what it does
  - `Lab-01-Tech-Insights/workflows/social_insight_workflow.yaml:1-10` — Verify this file exists

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Social insight files preserved
    Tool: Bash (test)
    Preconditions: Tasks 5, 7 completed
    Steps:
      1. test -f Lab-01-Tech-Insights/generated/tech_insight_workflow/social_insight_tools.py
      2. test -f Lab-01-Tech-Insights/workflows/social_insight_workflow.yaml
    Expected Result: Both social insight files still exist
    Failure Indicators: Either file missing
    Evidence: .sisyphus/evidence/task-8-social-preserved.txt
  ```

  **Commit**: NO (groups with Commit 6)

- [x] 9. Rewrite Lab-01 README.md for gh-aw

  **What to do**:
  - Completely rewrite `Lab-01-Tech-Insights/README.md` for the gh-aw architecture
  - New README should include:
    - **Title**: Lab-01: Tech Insights — GitHub Agentic Workflows
    - **Overview**: What the lab does (tech signal aggregation → clustering → insights → report)
    - **Architecture diagram**: Text-based diagram showing gh-aw workflow → MCP Scripts → tools → output
    - **Prerequisites**:
      - GitHub CLI (`gh`) installed
      - gh-aw extension installed (`gh extension install github/gh-aw`)
      - Python 3.10+ (for MCP scripts)
      - Repository with GitHub Actions enabled
    - **Quick Start**:
      - `gh aw compile .github/workflows/tech-insight.md` — compile the workflow
      - Manual trigger via GitHub Actions UI or `gh workflow run`
    - **Directory Structure**: Explain the new layout (mcp-scripts/, input/, frontend/)
    - **How It Works**: Step-by-step pipeline explanation (signals → clusters → insights → report)
    - **MCP Scripts**: List all 7 scripts with brief descriptions
    - **Configuration**: Explain `.env.example` variables
    - **Output**: Where to find the report (`frontend/report.md`) and GitHub Pages deployment
    - **Local Development**: How to test tools locally (run Python scripts directly) and view report locally via `frontend/index.html`
  - Write in Chinese (zh-CN) to match the existing Lab documentation style and root README
  - Remove ALL references to Azure, MAF, Azure AI Foundry, OIDC, etc.

  **Must NOT do**:
  - Do NOT write in English (existing docs are Chinese)
  - Do NOT reference Azure, MAF, or any removed technology
  - Do NOT include setup steps for Azure CLI or Azure accounts
  - Do NOT add features not in the migrated pipeline

  **Recommended Agent Profile**:
  - **Category**: `writing`
    - Reason: Documentation rewrite — needs clear technical writing in Chinese
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Task 10)
  - **Blocks**: Task 11
  - **Blocked By**: Tasks 4, 5, 7

  **References** (CRITICAL):

  **Pattern References**:
  - `Lab-01-Tech-Insights/README.md:1-250` — Current README showing existing structure and Chinese writing style to follow
  - Root `README.md:1-80` — Root README showing Lab-01 section that references this README

  **External References**:
  - https://github.github.com/gh-aw/setup/quick-start/ — gh-aw quick start instructions to adapt
  - https://github.github.com/gh-aw/reference/mcp-scripts/ — MCP Script documentation to reference

  **WHY Each Reference Matters**:
  - Current README shows the Chinese documentation style to maintain
  - Root README shows how Lab-01 is referenced (needs consistent description)
  - gh-aw docs provide the setup steps to document

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: README has no Azure references
    Tool: Bash (grep)
    Preconditions: README rewritten
    Steps:
      1. grep -i "azure" Lab-01-Tech-Insights/README.md
      2. grep -i "foundry" Lab-01-Tech-Insights/README.md
      3. grep -i "MAF" Lab-01-Tech-Insights/README.md
      4. grep -i "oidc" Lab-01-Tech-Insights/README.md
    Expected Result: All greps return no matches
    Failure Indicators: Any Azure/Foundry/MAF/OIDC reference remaining
    Evidence: .sisyphus/evidence/task-9-no-azure-readme.txt

  Scenario: README contains required sections
    Tool: Bash (grep)
    Preconditions: README rewritten
    Steps:
      1. grep -c "gh-aw\|gh aw\|GitHub Agentic" Lab-01-Tech-Insights/README.md (verify gh-aw mentions)
      2. grep -c "mcp-scripts\|MCP" Lab-01-Tech-Insights/README.md (verify MCP references)
      3. grep "quick.start\|快速开始\|Quick Start" Lab-01-Tech-Insights/README.md (verify quick start section)
      4. grep "compile\|编译" Lab-01-Tech-Insights/README.md (verify compile instructions)
    Expected Result: All sections present with non-zero match counts
    Failure Indicators: Missing key sections
    Evidence: .sisyphus/evidence/task-9-readme-sections.txt

  Scenario: README is in Chinese
    Tool: Bash (python)
    Preconditions: README rewritten
    Steps:
      1. python3 -c "
         content = open('Lab-01-Tech-Insights/README.md').read()
         chinese_chars = sum(1 for c in content if '\u4e00' <= c <= '\u9fff')
         print(f'Chinese characters: {chinese_chars}')
         assert chinese_chars > 50, f'Too few Chinese chars: {chinese_chars}'
         print('PASS')
         "
    Expected Result: More than 50 Chinese characters present
    Failure Indicators: README written in English instead of Chinese
    Evidence: .sisyphus/evidence/task-9-readme-language.txt
  ```

  **Commit**: YES (Commit 7)
  - Message: `docs(lab01): rewrite .env.example and README for gh-aw`
  - Files: `Lab-01-Tech-Insights/README.md`, `Lab-01-Tech-Insights/.env.example`
  - Pre-commit: `grep -ic "azure" Lab-01-Tech-Insights/README.md` → expect 0

- [x] 10. Update Root README.md Lab-01 Section

  **What to do**:
  - Edit the root `README.md` to update the Lab-01-Tech-Insights section
  - Replace all Azure references with gh-aw equivalents:
    - Remove mentions of `run.py`, `--mock-agents`, Azure AI Foundry
    - Replace with gh-aw workflow compile and run instructions
    - Update the "最短本地验证" (shortest local verification) section
  - Update the quick start commands:
    - Old: `./scripts/install_deps.sh --python-only && python3 generated/tech_insight_workflow/run.py --mock-agents --non-interactive`
    - New: `gh aw compile .github/workflows/tech-insight.md` (or equivalent gh-aw command)
  - Keep the Chinese language and existing format consistent with other Lab sections

  **Must NOT do**:
  - Do NOT modify Lab-02 or Lab-03 sections
  - Do NOT change the overall README structure

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Small section edit in an existing file
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with Task 9)
  - **Blocks**: Task 11
  - **Blocked By**: None (can reference planned changes)

  **References** (CRITICAL):

  **Pattern References**:
  - Root `README.md:1-80` — Current Lab-01 section showing what to update
  - Root `README.md:80-end` — Lab-02 and Lab-03 sections to NOT touch (preserve format)

  **WHY Each Reference Matters**:
  - Root README has the Lab-01 section that references Azure-specific commands
  - Other Lab sections show the format to maintain consistency

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Root README Lab-01 section has no Azure references
    Tool: Bash (python)
    Preconditions: Root README updated
    Steps:
      1. python3 -c "
         content = open('README.md').read()
         lab01_section = content.split('## Lab-01')[1].split('## Lab-02')[0]
         azure_refs = lab01_section.lower().count('azure')
         mock_refs = lab01_section.count('mock-agents')
         run_py_refs = lab01_section.count('run.py')
         print(f'Azure refs: {azure_refs}, mock-agents: {mock_refs}, run.py: {run_py_refs}')
         assert azure_refs == 0, f'Found {azure_refs} Azure references'
         assert mock_refs == 0, f'Found mock-agents reference'
         print('PASS')
         "
    Expected Result: Zero Azure, mock-agents, and run.py references in Lab-01 section
    Failure Indicators: Any stale references
    Evidence: .sisyphus/evidence/task-10-root-readme.txt

  Scenario: Lab-02 and Lab-03 sections unchanged
    Tool: Bash
    Preconditions: Root README updated
    Steps:
      1. grep "## Lab-02-Podcast" README.md
      2. grep "## Lab-03-GitHub-Copilot" README.md
    Expected Result: Both Lab sections still present
    Failure Indicators: Other Lab sections accidentally modified or deleted
    Evidence: .sisyphus/evidence/task-10-other-labs.txt
  ```

  **Commit**: YES (groups with Commit 7)
  - Message: grouped into `docs(lab01): rewrite .env.example and README for gh-aw`
  - Files: `README.md`

- [x] 11. End-to-End Verification — Azure-Free Migration Complete

  **What to do**:
  - Run comprehensive verification to confirm the migration is complete and correct:
  - **Azure reference scan**: `grep -ri "azure" Lab-01-Tech-Insights/ --include="*.py" --include="*.txt" --include="*.yaml" --include="*.yml" --include="*.json" --include="*.sh" --include="*.ps1" | grep -v README` — expect zero hits
  - **Foundry reference scan**: `grep -ri "foundry" Lab-01-Tech-Insights/ --include="*.py" --include="*.txt" --include="*.yaml" --include="*.yml" | grep -v README` — expect zero hits
  - **Deleted files verification**: Run `test ! -f` for all 10+ deleted files
  - **New files verification**: Run `test -f` for all new files (mcp-scripts/, gh-aw workflow)
  - **Preserved files verification**: Run `test -f` for all preserved files (rss_list.json, frontend/, tech_insight_tools.py in new location)
  - **Python syntax check**: Run `python -m py_compile` on all Python files in mcp-scripts/
  - **Requirements validation**: Verify `pip install -r requirements.txt` has no Azure packages
  - **gh-aw workflow structure**: Verify `.github/workflows/tech-insight.md` has valid frontmatter and all pipeline stages
  - **GitHub Actions workflows**: Verify no Azure references in `.github/workflows/`
  - **Social insight preservation**: Verify `social_insight_tools.py` and `social_insight_workflow.yaml` are untouched
  - Generate a comprehensive verification report

  **Must NOT do**:
  - Do NOT modify any files — this is verification only
  - Do NOT skip any verification step

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Comprehensive multi-step verification requiring careful cross-referencing
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 4 (sequential — after all implementation)
  - **Blocks**: F1-F4
  - **Blocked By**: ALL Tasks 1-10

  **References** (CRITICAL):

  **Pattern References**:
  - This plan's "Definition of Done" section — contains all verification commands
  - This plan's "Success Criteria" section — contains final checklist

  **Acceptance Criteria**:

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Complete Azure removal verification
    Tool: Bash
    Preconditions: All Tasks 1-10 completed
    Steps:
      1. grep -ri "azure" Lab-01-Tech-Insights/ --include="*.py" --include="*.txt" --include="*.yaml" --include="*.yml" --include="*.json" --include="*.sh" --include="*.ps1" | grep -v README | grep -v ".md" | tee /dev/stderr | wc -l
      2. grep -ri "foundry" Lab-01-Tech-Insights/ --include="*.py" --include="*.txt" --include="*.yaml" --include="*.yml" | grep -v README | grep -v ".md" | tee /dev/stderr | wc -l
    Expected Result: Both counts are 0 — zero Azure/Foundry references in code files
    Failure Indicators: Any non-zero count
    Evidence: .sisyphus/evidence/task-11-azure-scan.txt

  Scenario: Full file inventory check
    Tool: Bash
    Preconditions: All Tasks 1-10 completed
    Steps:
      1. Verify 10 deleted files are absent (test ! -f for each)
      2. Verify 7 MCP scripts exist in mcp-scripts/
      3. Verify tech_insight_tools.py exists in mcp-scripts/
      4. Verify gh-aw workflow exists at .github/workflows/tech-insight.md
      5. Verify rss_list.json untouched (exists)
      6. Verify frontend/ files untouched (index.html, main.js, styles.css, report.md)
      7. Verify social_insight_tools.py and social_insight_workflow.yaml preserved
    Expected Result: All file checks pass
    Failure Indicators: Any unexpected file present/absent
    Evidence: .sisyphus/evidence/task-11-file-inventory.txt

  Scenario: Python files have valid syntax
    Tool: Bash
    Preconditions: All Python files in final locations
    Steps:
      1. Find all .py files in Lab-01-Tech-Insights/mcp-scripts/
      2. Run python -m py_compile on each
    Expected Result: All files compile without errors
    Failure Indicators: SyntaxError from any file
    Evidence: .sisyphus/evidence/task-11-syntax-check.txt
  ```

  **Commit**: YES (Commit 8)
  - Message: `test(lab01): verify Azure-free migration complete`
  - Files: evidence files only (`.sisyphus/evidence/task-11-*.txt`)
  - Pre-commit: all verification commands pass

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.
>
> **Do NOT auto-proceed after verification. Wait for user's explicit approval before marking work complete.**

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run linter on all Python files. Review all changed/new files for: empty catches, console.log in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names. Verify `tech_insight_tools.py` is UNMODIFIED from original (diff against git).
  Output: `Lint [PASS/FAIL] | Files [N clean/N issues] | tech_insight_tools.py [UNMODIFIED/MODIFIED] | VERDICT`

- [x] F3. **Real Manual QA** — `unspecified-high`
  Start from clean state. Run `gh aw compile` on the workflow. Verify `.lock.yml` is generated. Run `grep -ri "azure"` across entire Lab-01 directory (excluding README.md). Verify all deleted files are absent. Verify all new files exist. Check `requirements.txt` has zero Azure packages. Verify `rss_list.json` is untouched (checksum). Verify `frontend/` is untouched (checksum). Save evidence to `.sisyphus/evidence/final-qa/`.
  Output: `Compile [PASS/FAIL] | Azure refs [0/N found] | Deleted [N/N confirmed] | New [N/N present] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (git log/diff). Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance. Detect cross-task contamination. Flag unaccounted changes. Specifically verify: `social_insight_tools.py` NOT modified, `social_insight_workflow.yaml` NOT modified, `rss_list.json` NOT modified, `frontend/*` NOT modified.
  Output: `Tasks [N/N compliant] | Scope [CLEAN/N issues] | Out-of-scope files [CLEAN/N touched] | VERDICT`

---

## Commit Strategy

| Order | Message | Files | Pre-commit Check |
|-------|---------|-------|-----------------|
| 1 | `feat(lab01): add gh-aw workflow definition for tech-insight pipeline` | `.github/workflows/tech-insight.md` | `cat .github/workflows/tech-insight.md` (verify syntax) |
| 2 | `feat(lab01): convert tech insight tools to MCP scripts` | `Lab-01-Tech-Insights/mcp-scripts/*` | `python -c "import mcp_scripts"` or file existence check |
| 3 | `chore(lab01): remove Azure dependencies from requirements.txt` | `Lab-01-Tech-Insights/requirements.txt` | `grep -c azure requirements.txt` → expect 0 |
| 4 | `chore(lab01): remove Azure-specific files and scripts` | 10+ deletions | `test ! -f` for each deleted file |
| 5 | `chore(lab01): replace GitHub Actions workflow with gh-aw trigger` | `.github/workflows/tech_insight_workflow.yml`, `.github/workflows/deploy_frontend_swa.yml` | file existence/absence checks |
| 6 | `refactor(lab01): restructure directory layout for gh-aw` | move `tech_insight_tools.py` → `mcp-scripts/`, cleanup | import checks |
| 7 | `docs(lab01): rewrite README and config for gh-aw migration` | `README.md`, `.env.example`, root README | content verification |
| 8 | `test(lab01): add Azure-free migration verification` | verification evidence | all grep/test commands pass |

---

## Success Criteria

### Verification Commands
```bash
# Zero Azure references (excluding documentation)
grep -ri "azure" Lab-01-Tech-Insights/ --include="*.py" --include="*.txt" --include="*.yaml" --include="*.yml" --include="*.json" --include="*.sh" --include="*.ps1" | grep -v README  # Expected: no output

# Zero Foundry references
grep -ri "foundry" Lab-01-Tech-Insights/ --include="*.py" --include="*.txt" --include="*.yaml" --include="*.yml" | grep -v README  # Expected: no output

# Requirements install cleanly
pip install -r Lab-01-Tech-Insights/requirements.txt  # Expected: success, zero azure packages

# gh-aw workflow compiles
gh aw compile .github/workflows/tech-insight.md  # Expected: generates .lock.yml

# Deleted files are gone
test ! -f Lab-01-Tech-Insights/generated/tech_insight_workflow/run.py  # Expected: exit 0
test ! -f Lab-01-Tech-Insights/generated/tech_insight_workflow/maf_declarative_runtime.py  # Expected: exit 0
test ! -f Lab-01-Tech-Insights/generated/tech_insight_workflow/create_agents_from_workflow.py  # Expected: exit 0

# Preserved files exist
test -f Lab-01-Tech-Insights/input/api/rss_list.json  # Expected: exit 0
test -f Lab-01-Tech-Insights/frontend/index.html  # Expected: exit 0
test -f Lab-01-Tech-Insights/frontend/report.md  # Expected: exit 0
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] gh-aw workflow compiles without errors
- [ ] Zero Azure references in code/config files
- [ ] All 10+ Azure files deleted
- [ ] `tech_insight_tools.py` logic unmodified (only wrapped)
- [ ] `rss_list.json` untouched
- [ ] `frontend/` untouched
- [ ] README fully rewritten for gh-aw
- [ ] Chinese (zh-CN) prompts preserved in gh-aw workflow
