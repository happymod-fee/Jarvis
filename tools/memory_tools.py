"""
Long-Term Memory Tools for VAX.
Allows the assistant to permanently remember user preferences, names, notes, and facts.
"""

from vax.tools import tool
from vax.safety import RiskLevel
from vax.memory import memory_manager


@tool(description="Permanently remembers a fact, preference, name, or note about the user across all sessions.", risk_level=RiskLevel.SAFE)
def remember_user_info(key: str, value: str) -> str:
    """Stores a permanent fact in VAX long-term memory."""
    return memory_manager.remember_fact(key, value)


@tool(description="Recalls all saved facts and preferences from VAX long-term memory.", risk_level=RiskLevel.SAFE)
def recall_user_info() -> str:
    """Returns all remembered user facts."""
    facts = memory_manager.get_all_facts()
    if not facts:
        return "No saved user memories yet."
    return "\n".join(f"- {k}: {v}" for k, v in facts.items())


@tool(description="Forgets a previously remembered fact by its key name.", risk_level=RiskLevel.SAFE)
def forget_user_info(key: str) -> str:
    """Deletes a fact from long-term memory."""
    return memory_manager.forget_fact(key)
