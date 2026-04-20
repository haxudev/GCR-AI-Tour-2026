"""
Microsoft Agent Framework Workflow - Podcast Generator
使用 GitHub Copilot 作为 LLM 提供方，结合 MAF Workflow 进行编排

工作流拓扑（顺序执行）：
    PodcastSearchExecutor -> PodcastContentExecutor -> PodcastScriptExecutor
    (生成大纲)              (生成脚本草稿)             (润色并保存)

环境变量（可选）：
- GITHUB_COPILOT_CLI_PATH - Copilot CLI 可执行文件路径
- GITHUB_COPILOT_MODEL    - 使用的模型（如 "gpt-5", "claude-sonnet-4"）
- GITHUB_COPILOT_TIMEOUT  - 请求超时（秒）
"""

import asyncio
import argparse
import uuid
from pathlib import Path
from typing import cast
from typing_extensions import Never

from agent_framework import (
    Executor,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    handler,
)
from agent_framework.github import GitHubCopilotAgent
from dotenv import load_dotenv


def save_podcast_content(content: str, output_dir: str = "podcast") -> str:
    """保存播客内容到文件"""
    podcast_dir = Path(output_dir)
    podcast_dir.mkdir(exist_ok=True)

    file_uuid = str(uuid.uuid4())[:8]
    filename = f"2p_podcast_{file_uuid}.txt"
    file_path = podcast_dir / filename

    file_path.write_text(content, encoding="utf-8")
    print(f"内容已保存到文件: {file_path}")
    return str(file_path)


# ---------------------------------------------------------------------------
# Executor 定义 — 每个 Executor 封装一个 GitHubCopilotAgent 调用
# ---------------------------------------------------------------------------


class PodcastSearchExecutor(Executor):
    """播客搜索 Agent：根据用户主题生成播客大纲"""

    def __init__(self):
        super().__init__(id="podcast-search-agent")

    @handler
    async def generate_outline(self, topic: str, ctx: WorkflowContext[str]) -> None:
        agent = GitHubCopilotAgent(
            instructions=(
                "你是一位专业的播客内容策划人。根据用户提供的主题，"
                "生成一份详细的播客大纲，包括：\n"
                "1. 开场引入\n"
                "2. 3-5 个核心讨论点\n"
                "3. 结尾总结\n"
                "请用中文回复。"
            ),
            name="podcast-search-agent",
        )
        async with agent:
            result = await agent.run(f"请根据这个主题生成播客大纲：{topic}")

        outline = str(result)
        print(f"\n[podcast-search-agent] 播客大纲已生成")
        await ctx.send_message(outline)


class PodcastContentExecutor(Executor):
    """播客内容 Agent：根据大纲生成两人对话风格播客脚本"""

    def __init__(self):
        super().__init__(id="podcast-content-agent")

    @handler
    async def generate_script(self, outline: str, ctx: WorkflowContext[str]) -> None:
        agent = GitHubCopilotAgent(
            instructions=(
                "你是一位专业的播客内容撰稿人。根据提供的播客大纲，"
                "撰写一份完整的两人对话风格播客脚本。\n"
                "角色分别为 Host（主持人）和 Guest（嘉宾），\n"
                "对话应自然流畅、内容深入、生动有趣。\n"
                "请用中文回复。"
            ),
            name="podcast-content-agent",
        )
        async with agent:
            result = await agent.run(
                f"请根据以下播客大纲撰写完整的播客脚本：\n\n{outline}"
            )

        content = str(result)
        print(f"\n[podcast-content-agent] 播客脚本草稿已生成")
        await ctx.send_message(content)


class PodcastScriptExecutor(Executor):
    """播客脚本 Agent：润色并保存最终播客脚本"""

    def __init__(self):
        super().__init__(id="podcast-script-agent")

    @handler
    async def finalize_script(self, draft: str, ctx: WorkflowContext[Never, str]) -> None:
        agent = GitHubCopilotAgent(
            instructions=(
                "你是一位播客脚本编辑。对提供的播客脚本草稿进行最终润色，"
                "确保对话自然流畅、内容结构清晰、开场和结尾完整。\n"
                "请直接输出最终版本的脚本，不要添加额外说明。请用中文回复。"
            ),
            name="podcast-script-agent",
        )
        async with agent:
            result = await agent.run(
                f"请润色以下播客脚本并输出最终版本：\n\n{draft}"
            )

        final_script = str(result)
        save_podcast_content(final_script)
        print(f"\n[podcast-script-agent] 最终播客脚本已保存")
        await ctx.yield_output(final_script)


# ---------------------------------------------------------------------------
# Workflow 构建与运行
# ---------------------------------------------------------------------------


def create_podcast_workflow() -> Workflow:
    """
    创建播客生成工作流

    使用 WorkflowBuilder 将三个 Executor 按顺序串联：
        search -> content -> script
    """
    search = PodcastSearchExecutor()
    content = PodcastContentExecutor()
    script = PodcastScriptExecutor()

    return (
        WorkflowBuilder(start_executor=search)
        .add_edge(search, content)
        .add_edge(content, script)
        .build()
    )


async def run_podcast_workflow(input_topic: str) -> str:
    """运行播客生成工作流并通过流式事件输出进度"""
    workflow = create_podcast_workflow()

    print(f"开始生成播客内容，主题: {input_topic}")
    print("=" * 60)

    outputs: list[str] = []
    async for event in workflow.run(input_topic, stream=True):
        if event.type == "executor_invoked":
            executor_id = getattr(event, "executor_id", "")
            print(f"  -> 正在执行: {executor_id}")
        elif event.type == "executor_completed":
            executor_id = getattr(event, "executor_id", "")
            print(f"  <- 完成执行: {executor_id}")
        elif event.type == "output":
            outputs.append(cast(str, event.data))

    print("=" * 60)
    print("工作流执行完成！")
    return outputs[0] if outputs else ""


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="生成播客内容的工作流脚本（GitHub Copilot + MAF Workflow）"
    )
    parser.add_argument(
        "--topic", "-t",
        type=str,
        required=True,
        help="播客主题",
    )
    args = parser.parse_args()

    load_dotenv(".env")

    result = asyncio.run(run_podcast_workflow(input_topic=args.topic))

    if result:
        print("\n播客内容生成完成!")


if __name__ == "__main__":
    main()
