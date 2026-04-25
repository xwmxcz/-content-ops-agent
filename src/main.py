"""Content Ops Agent 主入口"""

import sys
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from src.graph.workflow import ContentOpsAgent


console = Console()


def print_welcome():
    welcome_text = """
# 🚀 Content Ops Agent - 智能内容运营助手

欢迎使用 Content Ops Agent！我可以帮助你：

- 📝 **内容生成**: "帮我写一篇小红书文案，主题是如何提高工作效率"
- ✨ **内容优化**: "这个文案太正式了，换一种更轻松的风格"
- 📅 **日历管理**: "把这篇内容安排到明天发布"
- 📊 **数据统计**: "查看我的内容统计"

输入 `help` 查看更多命令，输入 `quit` 或 `exit` 退出。
"""
    console.print(Markdown(welcome_text))


def print_help():
    help_text = """
## 📚 使用指南

### 快捷命令
- `help` - 显示帮助
- `quit` / `exit` - 退出程序
- `clear` - 清屏
- `recent` - 查看最近的内容
- `stats` - 查看内容统计
- `calendar` - 查看发布日历

### 示例
- "帮我生成小红书文案，主题是健康饮食"
- "把 ID 为 1 的内容改写得更专业一些"
- "查看未来 7 天的发布日历"
"""
    console.print(Markdown(help_text))


def main():
    print_welcome()

    try:
        agent = ContentOpsAgent()
        console.print("[green]✓ Agent 初始化成功[/green]\n")
    except Exception as e:
        console.print(f"[red]✗ Agent 初始化失败: {e}[/red]")
        console.print("[yellow]请检查 .env 文件中的配置是否正确[/yellow]")
        sys.exit(1)

    while True:
        try:
            user_input = Prompt.ask("\n[bold blue]你[/bold blue]")

            if not user_input.strip():
                continue

            command = user_input.strip().lower()

            if command in ["quit", "exit", "q"]:
                console.print("\n[yellow]再见！👋[/yellow]")
                break

            if command == "help":
                print_help()
                continue

            if command == "clear":
                console.clear()
                print_welcome()
                continue

            if command == "recent":
                user_input = "列出最近的 10 条内容"
            if command == "stats":
                user_input = "查看内容统计"
            if command == "calendar":
                user_input = "查看未来 7 天的发布日历"

            console.print()
            with console.status("[bold green]思考中...[/bold green]"):
                response = agent.chat(user_input)

            console.print(Panel(
                Markdown(response),
                title="[bold green]Content Ops Agent[/bold green]",
                border_style="green"
            ))

        except KeyboardInterrupt:
            console.print("\n\n[yellow]再见！👋[/yellow]")
            break
        except Exception as e:
            console.print(f"\n[red]发生错误: {e}[/red]")


if __name__ == "__main__":
    main()
