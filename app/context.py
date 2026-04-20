from dataclasses import dataclass

from app.llm import ToolExecutor


@dataclass(frozen=True)
class AppContext:
    tool_executor: ToolExecutor | None
