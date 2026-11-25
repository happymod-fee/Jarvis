"""
VAX Plugin Auto-Loader.
Dynamically discovers and imports all Python files from plugins directories,
registering any functions decorated with @tool into the central ToolRegistry.
"""

import sys
import os
import importlib.util
from pathlib import Path
import logging

from vax.config import get_vax_dir

logger = logging.getLogger("VAX.Plugins")


def load_all_plugins():
    """
    Scans internal and user plugin folders, loading any valid Python modules.
    """
    plugin_dirs = [
        Path(__file__).parent.resolve(),              # Built-in /plugins
        get_vax_dir() / "plugins",                   # User ~/.vax/plugins
    ]

    loaded_count = 0
    for p_dir in plugin_dirs:
        if not p_dir.exists():
            try:
                p_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                continue

        for py_file in p_dir.glob("*.py"):
            if py_file.name == "__init__.py":
                continue

            module_name = f"vax_plugin_{py_file.stem}"
            try:
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = mod
                    spec.loader.exec_module(mod)
                    loaded_count += 1
                    logger.info("Loaded plugin module: %s (%s)", py_file.name, py_file)
            except Exception as e:
                logger.error("Failed to load plugin '%s': %s", py_file.name, e)

    logger.info("Plugin loading complete. Loaded %d plugin files.", loaded_count)
