"""
Sample VAX Plugin: Quick Todo & Reminders Manager.
Demonstrates how simple it is to add custom tools using the @tool decorator.
"""

import json
from pathlib import Path
from typing import List

from vax.tools import tool
from vax.safety import RiskLevel
from vax.config import get_vax_dir


def _get_todo_file() -> Path:
    todo_path = get_vax_dir() / "todos.json"
    if not todo_path.exists():
        todo_path.write_text("[]", encoding="utf-8")
    return todo_path


@tool(description="Adds a new task or reminder item to the user's todo list.", risk_level=RiskLevel.MEDIUM)
def add_todo(task: str) -> str:
    """Adds a todo item."""
    p = _get_todo_file()
    try:
        todos = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        todos = []

    todos.append({"task": task, "done": False})
    p.write_text(json.dumps(todos, indent=2), encoding="utf-8")
    return f"Added to todo list: '{task}'"


@tool(description="Lists all current tasks and reminders on the user's todo list.", risk_level=RiskLevel.SAFE)
def list_todos() -> str:
    """Lists pending and completed todos."""
    p = _get_todo_file()
    try:
        todos = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        todos = []

    if not todos:
        return "Your todo list is currently empty."

    lines = []
    for idx, item in enumerate(todos, 1):
        status = "✓" if item.get("done") else "○"
        lines.append(f"{idx}. [{status}] {item.get('task')}")

    return "\n".join(lines)


@tool(description="Marks a task on the todo list as done by its index number (e.g. 1, 2).", risk_level=RiskLevel.MEDIUM)
def complete_todo(item_number: int) -> str:
    """Marks todo done."""
    p = _get_todo_file()
    try:
        todos = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        todos = []

    idx = int(item_number) - 1
    if 0 <= idx < len(todos):
        todos[idx]["done"] = True
        p.write_text(json.dumps(todos, indent=2), encoding="utf-8")
        return f"Marked task #{item_number} as completed: '{todos[idx]['task']}'"
    return f"Invalid task number {item_number}. Total tasks: {len(todos)}."


@tool(description="Clears all tasks from the todo list.", risk_level=RiskLevel.DANGEROUS)
def clear_all_todos() -> str:
    """Clears todos."""
    p = _get_todo_file()
    p.write_text("[]", encoding="utf-8")
    return "All tasks have been cleared from your todo list."
