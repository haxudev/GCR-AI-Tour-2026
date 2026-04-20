# Overview

这是一个用于学习 GitHub Copilot 与 Copilot SDK 中 skill 工作方式的 Lab。

## Lab 1

在 VS Code 的聊天窗口中，通过自然语言对话调用工作区内已经配置好的 `url2ppt` 和 `pptx` skill，把单个网页 URL 转成 PowerPoint。

### Lab 目标

- 理解 GitHub Copilot 如何在聊天过程中自动发现并调用 skill
- 学会通过自然语言给出网页地址、页数和风格要求
- 观察从网页内容抓取、整理大纲到生成 `.pptx` 文件的完整流程

### 如何使用

1. 在 VS Code 中打开本Lab工作区（文件夹Lab-03-GitHub-Copilot）。
2. 打开 GitHub Copilot Chat 聊天窗口。
3. 直接输入你的需求，例如提供一个网页 URL，并说明希望生成几页 PPT。
4. 如果你没有指定风格，Copilot 会根据 skill 配置继续询问你偏好的呈现风格。
5. 等待 Copilot 完成网页内容整理与 PPT 生成。

示例提示词：

```text
请把这个网页整理成 8 页 PPT：url=https://example.com
```

```text
请基于这个网页生成 8 页 PPT，风格用咨询风：url=https://example.com
```

```text
把这个页面做成适合培训分享的 PPT，10 页，风格偏极客风：url=https://example.com
```

### 生成流程

在这个 Lab 中，Copilot 会按如下思路完成任务：

1. 识别用户是在请求“基于网页内容生成 PPT”。
2. 直接调用 `url2ppt` skill。
3. 抓取网页主要内容，并整理成适合演示文稿的分页 Markdown 大纲。
4. 调用 `pptx` skill，把大纲进一步生成为 `.pptx` 文件。

### 输出位置

- 生成的 `.pptx` 文件会写入 `./output/`
- 生成过程中产生的中间文件也可能保留在 `./output/` 下的子目录中

### 你会观察到什么

- Copilot 会根据你的提示自动选择合适的 skill
- 当风格信息不足时，Copilot 会先追问，而不是直接假设
- 最终输出不是简单摘抄网页，而是会重组为适合汇报或分享的演示结构
- 可通过修改`.github/url2ppt/SKILL.md`添加或更新风格

## Lab 2

Lab 2 聚焦“在一个 Web 程序内通过 Copilot SDK 创建 PPT”。

在这个 Lab 中，用户不再直接在聊天窗口里完成全部流程，而是通过前端页面发起请求，后端使用 Copilot SDK 调用 agent/skill 生成 PPT，并把过程事件流式返回给前端。

### 目标

- 理解如何在 Web 应用中接入 Copilot SDK
- 学会通过前后端联动触发 URL 转 PPT 任务

### 启动前准备

请先确认以下条件已经满足：

- 已安装 Node.js 24 或更高版本

环境变量配置：

1. 在 GitHub 右上角进入 `Settings` -> `Developer settings` -> `Personal access tokens` -> `Fine-grained tokens`，然后点击 `Generate new token`。为 token 填写名称和过期时间，点击 `Generate token`，复制生成后的 token。
2. 在项目根目录创建 `.env` 文件；可直接复制 `.env.example` 作为模板。
3. 在 `.env` 中填写你的 token：

```bash
COPILOT_GITHUB_TOKEN=你的_github_pat
```

如果你选择的是组织作为 `Resource owner`，且组织启用了 fine-grained token 审批流程，那么 token 在管理员批准之前可能无法正常使用。

### 如何启动

在vscode的聊天窗口直接输入：启动该程序

或者在命令行执行以下命令：
```bash
npm install
npm run dev
```

启动成功后，默认访问地址为：`http://localhost:3000`

### 如何使用

1. 在浏览器打开 `http://localhost:3000`。
2. 输入一个 `http` 或 `https` 网页地址。
3. 选择一种 PPT 风格。
4. 点击“开始生成 PPT”。
5. 等待前端实时展示生成进度并拿到下载链接。

### 参考内容

copiot sdk源码参考：https://github.com/github/copilot-sdk

