"""
Action Log & History Viewer for VAX.
Displays a searchable, filterable table of all actions executed by the assistant.
Modernized for PySide6 scoped enums.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPushButton,
    QLineEdit,
    QLabel,
    QMessageBox,
)

from vax.action_log import action_logger
from vax.ui.styles import DARK_THEME_QSS


class LogViewerDialog(QDialog):
    """
    Dialog for inspecting historical assistant actions.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("VAX Action History & Audit Log")
        self.resize(780, 480)
        self.setStyleSheet(DARK_THEME_QSS)
        self._setup_ui()
        self._load_logs()

    def showEvent(self, event):
        super().showEvent(event)
        self._load_logs()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Controls Bar
        ctrl_bar = QHBoxLayout()
        self.in_filter = QLineEdit(self)
        self.in_filter.setPlaceholderText("Filter by tool name or status...")
        self.in_filter.textChanged.connect(self._filter_rows)

        btn_refresh = QPushButton("🔄 Refresh", self)
        btn_refresh.clicked.connect(self._load_logs)

        btn_clear = QPushButton("🗑️ Clear History", self)
        btn_clear.clicked.connect(self._clear_logs)

        ctrl_bar.addWidget(QLabel("Search:"))
        ctrl_bar.addWidget(self.in_filter, stretch=1)
        ctrl_bar.addWidget(btn_refresh)
        ctrl_bar.addWidget(btn_clear)
        layout.addLayout(ctrl_bar)

        # Table
        self.table = QTableWidget(self)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Time",
            "Tool",
            "Risk",
            "Status",
            "Arguments",
            "Result / Summary",
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)

        layout.addWidget(self.table)

    def _load_logs(self):
        try:
            logs = action_logger.get_recent_logs(limit=100)
            self.table.setRowCount(len(logs))

            for row_idx, row in enumerate(logs):
                self.table.setItem(row_idx, 0, QTableWidgetItem(str(row["timestamp"])))
                self.table.setItem(row_idx, 1, QTableWidgetItem(str(row["tool_name"])))

                risk_item = QTableWidgetItem(str(row["risk_level"]))
                if row["risk_level"] == "DANGEROUS":
                    risk_item.setForeground(QColor("#ef4444"))
                elif row["risk_level"] == "MEDIUM":
                    risk_item.setForeground(QColor("#f59e0b"))
                else:
                    risk_item.setForeground(QColor("#00d2ff"))
                self.table.setItem(row_idx, 2, risk_item)

                status_item = QTableWidgetItem(str(row["status"]))
                if row["status"] == "success":
                    status_item.setForeground(QColor("#10b981"))
                elif row["status"] in ("blocked", "failed"):
                    status_item.setForeground(QColor("#ef4444"))
                self.table.setItem(row_idx, 3, status_item)

                self.table.setItem(row_idx, 4, QTableWidgetItem(str(row["arguments"])))
                self.table.setItem(row_idx, 5, QTableWidgetItem(str(row["result_summary"])))

            self.table.resizeColumnsToContents()
        except Exception:
            pass

    def _filter_rows(self, query: str):
        q = query.lower().strip()
        for row in range(self.table.rowCount()):
            tool_item = self.table.item(row, 1)
            status_item = self.table.item(row, 3)
            summary_item = self.table.item(row, 5)
            tool = tool_item.text().lower() if tool_item else ""
            status = status_item.text().lower() if status_item else ""
            summary = summary_item.text().lower() if summary_item else ""
            match = q in tool or q in status or q in summary
            self.table.setRowHidden(row, not match)

    def _clear_logs(self):
        confirm = QMessageBox.question(
            self,
            "Clear Logs",
            "Are you sure you want to delete all historical action records?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            action_logger.clear_logs()
            self._load_logs()
