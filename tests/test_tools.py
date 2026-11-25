"""
Unit Tests for VAX Tools.
Tests calculator, clipboard, safe file operations, and sample todo plugin.
"""

import os
from pathlib import Path
import pytest
from vax.tools.web_info import calculate
from vax.tools.clipboard import write_clipboard, read_clipboard
from vax.tools.files import create_file, read_file, delete_file
from vax.plugins.sample_plugin import add_todo, list_todos, complete_todo, clear_all_todos


def test_safe_calculator():
    assert "200" in calculate("25 * 4 + 100")
    assert "256" in calculate("2 ** 8")
    assert "50.0" in calculate("100 / 2")

    # Reject dangerous injection
    res = calculate("__import__('os').system('dir')")
    assert "error" in res.lower() or "unsupported" in res.lower()


def test_clipboard_operations():
    test_str = "VAX_TEST_CLIPBOARD_CONTENT_12345"
    write_res = write_clipboard(test_str)
    assert "successfully" in write_res.lower()

    read_back = read_clipboard()
    assert test_str in read_back


def test_file_create_and_read(tmp_path):
    test_file = tmp_path / "vax_test.txt"
    create_res = create_file(str(test_file), "Hello VAX Voice Assistant!")
    assert "created" in create_res.lower()

    content = read_file(str(test_file))
    assert "Hello VAX Voice Assistant!" in content


def test_todo_plugin():
    clear_all_todos()
    add_todo("Buy groceries")
    add_todo("Test VAX voice assistant")

    todos = list_todos()
    assert "Buy groceries" in todos
    assert "Test VAX voice assistant" in todos

    done_res = complete_todo(1)
    assert "completed" in done_res.lower()

    updated = list_todos()
    assert "[✓] Buy groceries" in updated
    clear_all_todos()
