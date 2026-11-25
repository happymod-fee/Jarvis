"""
VAX Persistent Action Log.
Records every tool invocation, arguments, risk level, and execution status into a local SQLite database.
"""

import sqlite3
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import logging

from vax.config import get_vax_dir
from vax.safety import safety_engine

logger = logging.getLogger("VAX.ActionLog")


def get_db_path() -> Path:
    return get_vax_dir() / "action_history.db"


class ActionLogger:
    """
    SQLite-backed action history logger.
    """
    def __init__(self):
        self.db_path = get_db_path()
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS action_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        tool_name TEXT NOT NULL,
                        risk_level TEXT NOT NULL,
                        arguments TEXT,
                        status TEXT NOT NULL,
                        result_summary TEXT
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.error("Failed to initialize SQLite action log: %s", e)

    def log_action(
        self,
        tool_name: str,
        risk_level: str,
        arguments: Dict[str, Any],
        status: str,
        result_summary: str = "",
    ) -> int:
        """
        Record a tool action into the database.
        Returns the row id.
        """
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sanitized_summary = safety_engine.sanitize_for_output(result_summary)
        # Redact any sensitive keys in arguments
        try:
            args_str = json.dumps(arguments, ensure_ascii=False)
            args_str = safety_engine.sanitize_for_output(args_str)
        except Exception:
            args_str = str(arguments)

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO action_logs (timestamp, tool_name, risk_level, arguments, status, result_summary)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (now, tool_name, risk_level, args_str, status, sanitized_summary[:1000]))
                conn.commit()
                return cursor.lastrowid or 0
        except Exception as e:
            logger.error("Failed to log action: %s", e)
            return 0

    def get_recent_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Retrieve recent action history.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, timestamp, tool_name, risk_level, arguments, status, result_summary
                    FROM action_logs
                    ORDER BY id DESC
                    LIMIT ?
                """, (limit,))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error("Failed to query action logs: %s", e)
            return []

    def clear_logs(self) -> bool:
        """Clears all stored action logs."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM action_logs")
                conn.commit()
                return True
        except Exception as e:
            logger.error("Failed to clear action logs: %s", e)
            return False


action_logger = ActionLogger()
