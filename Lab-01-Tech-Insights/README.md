# Social Insight Multi-Agent Workflow

> ⚠️ 说明：本仓库已完成向 **Tech Insight Workflow** 的重构落地（RSS/Sitemap/HTML 源聚合 → 技术趋势/公司雷达/工具更新/研究趋势 → 报告）。
> 
> - Tech 输入：`input/api/rss_list.json`
> - 本地快速跑通（mock + 确定性兜底）：`./.venv/bin/python generated/tech_insight_workflow/run.py --mock-agents --non-interactive`
> - 使用 Azure AI Foundry Agents：`./.venv/bin/python generated/tech_insight_workflow/run.py --azure-ai --non-interactive`

**一句话概述**: 将「多平台热点信号」→「可追踪的核心热点」→「结构化社会洞察」→「平台级内容投放决策建议」

这是一个基于 Microsoft Agent Framework (MAF) 的**分析型 Agent 工作流（Analysis → Insight → Decision）**，而不是生成型内容工厂。

## 核心设计原则

1. **Agent 只负责"认知决策"，不负责 IO**
2. **所有关键中间结果必须结构化并落盘**
3. **每一步都允许 LLM 失败 → 本地工具兜底**
4. **最终输出是"建议报告"，而不是内容成品**

## 工作流架构

```text
[多平台 APIs]
    ↓
SignalIngestionAgent (LocalToolExecutorAgent - 确定性工具)
    ↓ raw_signals.json
HotspotClusteringAgent (LLM-first + Tool-fallback)
    ↓ hotspots.json
InsightAgent (高认知密度 LLM)
    ↓ insights.json
ContentStrategyAgent (决策转译 Agent)
    ↓ report.md
```

### Agent 角色

#### 0️⃣ Orchestrator（隐式 / Workflow 层）

通过 YAML 工作流定义执行顺序，注入上下文，决定是否中断或继续 fallback。

#### 1️⃣ SignalIngestionAgent（LocalToolExecutorAgent）

- **类型**: 确定性工具，不调用模型
- **职责**: 把"外部世界的热度噪声"转成**可回放的原始信号集**
- **输入**: `input/api/rss_list.json`（Tech Insight）或 `hot_api_list.json`（历史 Social Insight 兼容）
- **输出**: `raw_signals.json`, `signals/*.json`

#### 2️⃣ HotspotClusteringAgent

- **类型**: LLM-first + Tool-fallback
- **职责**: 判断「哪些信号其实在说同一件事」（主题判别 + 热度合并）
- **输入**: `raw_signals.json`
- **输出**: `hotspots.json`

#### 3️⃣ InsightAgent

- **类型**: 高认知密度 LLM Agent
- **职责**: 回答「这件事为什么在此刻、以这种方式火了」
- **输入**: `hotspots.json`
- **输出**: `insights.json`

#### 4️⃣ ContentStrategyAgent

- **职责**: 把洞察翻译成「不同平台该不该追、怎么追、追到什么程度」
- **输入**: `hotspots.json` + `insights.json`
- **输出**: `report.md`

## Hands-on Lab：用 Azure 订阅在 GitHub Actions 跑通

目标：让学员用自己的 Azure 订阅 + 自己 fork 的仓库，在 GitHub Actions 上自动跑通本工作流（真实 Azure AI Foundry Agents）。

你将得到：
- GitHub Actions 每次 push 到 `main` 自动生成的报告 `report.md`
- 可下载的完整输出目录（Artifacts）

本仓库已内置：
- GitHub Actions workflow（位于仓库根目录）：`.github/workflows/tech_insight_workflow.yml`
- 一键 OIDC + 变量配置脚本：`./scripts/setup_github_actions_oidc.sh` / `./scripts/setup_github_actions_oidc.ps1`
- 本地依赖安装脚本：`./scripts/install_deps.sh` / `./scripts/install_deps.ps1`

## 最短路径（推荐）：脚本一键配置 + push 即跑

这个路径尽量避免手动点 Portal；但有一件事目前仍需要你在 Foundry Portal 先做：创建 Project 并拿到 Project endpoint。

### 0) Fork 仓库

在 GitHub 上 fork 本仓库到你自己的账号（后续 OIDC 绑定的是你 fork 后的 `owner/repo`）。

### 0.5) Clone 到本地（必做一次）

在你自己的电脑上把 fork 后的仓库 clone 下来：

```bash
git clone https://github.com/<your-github-user>/gcr-ai-tour.git
cd gcr-ai-tour/lab01
```

说明：
- 下面的脚本会优先从本地 `git remote` 自动推断 `owner/repo`，在 `lab01/` 目录运行即可。

### 0.6) 环境初始化（本地一次，推荐）

这一步的目标：把“跑脚本需要的 CLI + Python 依赖”准备好。

Linux（Debian/Ubuntu，推荐）：

```bash
./scripts/install_deps.sh

# 如果你只想装 Python 依赖（不碰 az/gh）：
# ./scripts/install_deps.sh --python-only
```

说明：
- `install_deps.sh` 会在检测到 `apt-get` 时，尝试安装 Azure CLI（`az`）和 GitHub CLI（`gh`），然后创建 `lab01/.venv` 并安装 `lab01/requirements.txt`。
- 如果你不是 Debian/Ubuntu（没有 `apt-get`），脚本会跳过 CLI 安装并提示安装链接；你仍可以继续用它安装 Python 依赖。

Windows（PowerShell，推荐）：

```powershell
# 允许当前会话执行本地脚本（不改系统全局策略）
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# 进入 lab01 目录（本仓库可运行内容都在这里）
# Set-Location gcr-ai-tour\lab01

./scripts/install_deps.ps1

# 只装 Python 依赖（不安装 az/gh）：
# ./scripts/install_deps.ps1 -PythonOnly
```

说明：
- `install_deps.ps1` 会优先用 `winget` 安装 `az`/`gh`（可选），并创建 `lab01/.venv` 安装 Python 依赖。

### 1)（必须）在 Azure AI Foundry Portal 创建 Project + 模型部署

1. 打开 https://ai.azure.com
2. 创建一个 Project（按向导完成即可）
3. 在 Project 内创建/选择一个模型部署（Deployment）
   - 默认部署名推荐：`gpt-5-mini`（CI 默认值就是它）
4. 从 Project 详情页/设置页复制 `AZURE_AI_PROJECT_ENDPOINT`
   - 形如：`https://<your-foundry-resource>.services.ai.azure.com/api/projects/<your-project>`

说明：
- 学员不需要手工创建每个 Agent。本工作流会在 CI 运行时按名称创建/复用 agents，并写入 `generated/tech_insight_workflow/agent_id_map.json`。

### 2)（推荐）本地运行脚本：配置 Azure OIDC + 自动写入 GitHub Variables

前置条件：
- 已完成上一步“环境初始化”（推荐）
- 或者你已自行安装并能使用：Azure CLI（`az`）与（可选）GitHub CLI（`gh`）

如果你还没装这些 CLI：
- Azure CLI： https://learn.microsoft.com/cli/azure/install-azure-cli
- GitHub CLI： https://cli.github.com/

Windows（推荐用 `winget`）：

```powershell
winget install -e --id Git.Git
winget install -e --id Microsoft.AzureCLI
winget install -e --id GitHub.cli
```

在你 fork 的仓库本地 clone 后（或 Codespaces / Dev Container 中），执行：

重要：不要用 `sudo` 运行下面的脚本。
- `az login` / `gh auth login` 的认证信息是“当前用户”级别的；用 `sudo` 会切到 root 用户，导致脚本看不到你的登录态。

```bash
az login
gh auth login

# 推荐：将权限收窄到资源组（resource group）
./scripts/setup_github_actions_oidc.sh \
  --branch main \
  --resource-group <your-rg> \
  --enable-swa \
  --configure-github \
  --ai-project-endpoint "https://<your-foundry-resource>.services.ai.azure.com/api/projects/<your-project>"

# 如你的模型部署名不是 gpt-5-mini，再额外传：
#   --ai-model-deployment-name "<your-model-deployment>"
```

Windows PowerShell 等价命令（功能一致）：

```powershell
az login
gh auth login

./scripts/setup_github_actions_oidc.ps1 \
  -Branch main \
  -ResourceGroup <your-rg> \
  -EnableSwa \
  -ConfigureGitHub \
  -AiProjectEndpoint "https://<your-foundry-resource>.services.ai.azure.com/api/projects/<your-project>"
```

脚本会自动完成：
- 创建/复用 Entra App + Service Principal
- 创建 Federated Credential（GitHub Actions OIDC，限定 `main` 分支）
- 为该 SP 分配 RBAC（默认 `Cognitive Services User`，作用域默认建议用资源组）
- （可选）为该 SP 分配 Static Web Apps 相关角色（当传入 `--enable-swa` / `-EnableSwa`）
  - 脚本会优先使用 `Website Contributor`（官方内置角色），并自动回退到 `Contributor`
  - 如需强制指定角色，可传 `--swa-role "<role name>"` / `-SwaRole "<role name>"`
- 自动写入 GitHub Actions Variables（不需要 secrets）

新增的 GitHub Actions Variables（用于 SWA 部署）：
- `AZURE_RESOURCE_GROUP`（来自 `--resource-group` / `-ResourceGroup`）

常见踩坑（会导致“没有自动写入 Variables”）：
- 忘了加 `--configure-github` / `-ConfigureGitHub`：脚本会只打印“Next step: set GitHub Repository Variables …”的手工步骤。
- 在错误的目录/错误的 remote 上运行：脚本会从 `git remote get-url origin` 推断目标仓库。
  - 建议先执行：`git remote get-url origin`，确认指向你 fork 的仓库（而不是上游仓库）。
  - 如果你不想依赖推断，可以显式指定：
    - Bash：`--github-repo <your-github-user>/gcr-ai-tour`
    - PowerShell：`-GitHubRepo <your-github-user>/gcr-ai-tour`

### 3) push 到 main，GitHub Actions 自动跑真实 Azure AI

从此开始：
- push 到 `main` → 自动跑真实 Azure AI（会消耗额度）
- PR → 只跑 mock（更便宜，且 fork PR 通常拿不到变量/权限）

运行结束后：
- GitHub → Actions → 进入该 run → Artifacts 下载 `report.md` 和完整 output

### 4)（可选）手动部署前端到 Azure Static Web Apps

本仓库已提供一个手动触发的 workflow：
- `.github/workflows/deploy_frontend_swa.yml`

使用方式：
1. 打开 GitHub → Actions → 选择 `deploy-frontend-swa`
2. 点击 “Run workflow”
3. 只需填写 `swa_name`（可留空，自动生成随机名称）
  - 如已通过 OIDC 脚本写入 `AZURE_RESOURCE_GROUP`，则无需再填写 `resource_group`

workflow 会：
- 若 SWA 不存在则创建（同一个 resource group）
- 发布 `frontend/` 到 SWA
- 在 Actions summary 中输出 SWA 名称与 URL（同时暴露 workflow outputs）

## 备选路径：不用 GitHub CLI（仍然尽量少点 Portal）

如果你不想装 `gh`：

1. 仍建议用脚本完成 Azure 侧 OIDC（需要 `az login`）：

```bash
./scripts/setup_github_actions_oidc.sh --branch main --resource-group <your-rg>
```

2. 然后在 GitHub 仓库 UI 手动配置 Variables：

Settings → Secrets and variables → Actions → Variables

必填：
- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_AI_PROJECT_ENDPOINT`

可选：
- `AZURE_AI_MODEL_DEPLOYMENT_NAME`（不填则默认 `gpt-5-mini`）

## 本地验证（可选）：先跑 mock 再上云

如果你希望先本地确认工作流链路没问题：

```bash
./scripts/install_deps.sh --python-only
cp .env.sample .env
cd generated/tech_insight_workflow
python run.py --non-interactive --mock-agents
```

Windows PowerShell：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

./scripts/install_deps.ps1 -PythonOnly
Copy-Item .env.sample .env
Set-Location generated/tech_insight_workflow
python run.py --non-interactive --mock-agents
```

## 常见问题（排障最短路径）

### 1) GitHub Actions 里 Azure 登录失败

- 确认 workflow 顶层有 `permissions: id-token: write`
- 确认 Entra App 有 Federated Credential，subject 绑定的是你 fork 的仓库与分支：
  - `repo:<your-github-user>/<your-repo>:ref:refs/heads/main`

### 2) 401/403（没权限）

- 确认已给 Service Principal 分配 RBAC：`Cognitive Services User`
- 如果你把 scope 收窄到资源组，请确保 Foundry 相关资源也在该资源组范围内

### 3) 找不到模型部署 / 模型名不对

- 默认部署名：`gpt-5-mini`
- 如果你的部署名不同，设置 GitHub Variable：`AZURE_AI_MODEL_DEPLOYMENT_NAME`

## 附录：实现与文件索引

- 工作流 YAML：`workflows/tech_insight_workflow.yaml`
- 生成的可执行 runner：`generated/tech_insight_workflow/run.py`
- Agents spec / id map：
  - `generated/tech_insight_workflow/agents.yaml`
  - `generated/tech_insight_workflow/agent_id_map.json`
- 输出目录：`output/<timestamp>/report.md`
