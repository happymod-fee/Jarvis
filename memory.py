"""
Persistent Short-Term & Long-Term Memory for VAX.
Stores recent conversation turns (~20 turns) and permanent user facts/preferences
in ~/.vax/ so VAX remembers you across sessions.
"""

import json
import logging
from collections import deque
from pathlib import Path
from typing import Dict, List, Any

from vax.config import get_vax_dir
from vax.providers.base import ChatMessage

logger = logging.getLogger("VAX.Memory")


class PersistentMemoryManager:
    """Manages both rolling conversation history and permanent user facts."""

    def __init__(self, max_turns: int = 20):
        self.max_turns = max_turns
        self.history: deque = deque(maxlen=max_turns * 2)
        self.facts: Dict[str, str] = {}
        self._history_path = get_vax_dir() / "chat_history.json"
        self._facts_path = get_vax_dir() / "long_term_memory.json"
        self._load()

    def _load(self):
        try:
            if self._facts_path.exists():
                data = json.loads(self._facts_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self.facts = {str(k): str(v) for k, v in data.items()}
        except Exception as e:
            logger.debug("Could not load long-term memory: %s", e)

        try:
            if self._history_path.exists():
                items = json.loads(self._history_path.read_text(encoding="utf-8"))
                if isinstance(items, list):
                    for item in items[-(self.max_turns * 2):]:
                        if isinstance(item, dict) and item.get("role") in ("user", "assistant"):
                            self.history.append(
                                ChatMessage(role=item["role"], content=str(item.get("content", "")))
                            )
        except Exception as e:
            logger.debug("Could not load chat history: %s", e)

    def _save_history(self):
        try:
            payload = [{"role": m.role, "content": m.content} for m in self.history]
            self._history_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.debug("Could not save chat history: %s", e)

    def _save_facts(self):
        try:
            self._facts_path.write_text(json.dumps(self.facts, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.debug("Could not save long-term memory: %s", e)

    def add_user_message(self, text: str):
        self.history.append(ChatMessage(role="user", content=text))
        self._save_history()

    def add_assistant_message(self, text: str):
        self.history.append(ChatMessage(role="assistant", content=text))
        self._save_history()

    def get_messages(self) -> List[ChatMessage]:
        return list(self.history)

    def clear_history(self):
        self.history.clear()
        self._save_history()

    def remember_fact(self, key: str, value: str) -> str:
        clean_key = key.strip().lower().replace(" ", "_")
        clean_val = value.strip()
        if not clean_key or not clean_val:
            return "Both key and value are required."
        self.facts[clean_key] = clean_val
        self._save_facts()
        logger.info("Remembered fact: %s = %s", clean_key, clean_val)
        return f"Remembered: {clean_key} = {clean_val}"

    def forget_fact(self, key: str) -> str:
        clean_key = key.strip().lower().replace(" ", "_")
        if clean_key in self.facts:
            del self.facts[clean_key]
            self._save_facts()
            return f"Forgot '{clean_key}'."
        return f"No memory found for '{clean_key}'."

    def get_all_facts(self) -> Dict[str, str]:
        return dict(self.facts)

    def format_facts_for_prompt(self) -> str:
        if not self.facts:
            return ""
        lines = [f"- {k}: {v}" for k, v in self.facts.items()]
        return "\n\n[USER LONG-TERM MEMORY (ALWAYS REMEMBER THIS ABOUT THE USER)]\n" + "\n".join(lines)


memory_manager = PersistentMemoryManager(max_turns=20)
