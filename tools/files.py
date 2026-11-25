"""
File System Management Tools for VAX.
Implements safe search, read, write, copy, move, zip/unzip, and deletion.
Strictly sends deleted files/folders to the Windows Recycle Bin (via send2trash) to prevent data loss.
"""

import os
import shutil
import zipfile
import fnmatch
import logging
from pathlib import Path
from typing import List, Optional
import send2trash

from vax.tools import tool
from vax.safety import RiskLevel

logger = logging.getLogger("VAX.Tools.Files")


@tool(description="Searches for files matching a pattern (e.g. '*.pdf', 'budget*') in a directory (defaults to user home).", risk_level=RiskLevel.SAFE)
def search_files(pattern: str, search_dir: str = "") -> List[str]:
    """Finds files matching pattern."""
    root = Path(search_dir).expanduser() if search_dir else Path.home()
    if not root.exists():
        return [f"Directory '{root}' does not exist."]

    matches = []
    # Limit search depth to avoid hanging on entire drive scans
    try:
        for current_root, dirs, files in os.walk(root):
            # Skip hidden / heavy developer directories
            dirs[:] = [d for d in dirs if not d.startswith((".", "node_modules", "AppData", "$Recycle.Bin"))]
            for file in files:
                if fnmatch.fnmatch(file.lower(), pattern.lower()):
                    full_p = os.path.join(current_root, file)
                    matches.append(full_p)
                    if len(matches) >= 30:
                        return matches
    except Exception as e:
        matches.append(f"Error during search: {e}")

    return matches if matches else [f"No files matching '{pattern}' found in {root}."]


@tool(description="Reads and returns the text content of a file (up to max_lines).", risk_level=RiskLevel.SAFE)
def read_file(path: str, max_lines: int = 100) -> str:
    """Reads text file contents."""
    p = Path(path).expanduser()
    if not p.exists():
        return f"File '{p}' does not exist."
    if not p.is_file():
        return f"Path '{p}' is a directory, not a file."

    try:
        lines = []
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                lines.append(line)
                if len(lines) >= max_lines:
                    break
        content = "".join(lines)
        if len(lines) >= max_lines:
            content += f"\n... [Truncated after {max_lines} lines]"
        return content
    except Exception as e:
        return f"Failed to read file: {e}"


@tool(description="Creates a new file with the specified text content.", risk_level=RiskLevel.MEDIUM)
def create_file(path: str, content: str = "") -> str:
    """Creates a text file."""
    p = Path(path).expanduser()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Created file: {p} ({len(content)} characters written)."
    except Exception as e:
        return f"Failed to create file: {e}"


@tool(description="Creates a new directory/folder.", risk_level=RiskLevel.MEDIUM)
def create_folder(path: str) -> str:
    """Creates a folder."""
    p = Path(path).expanduser()
    try:
        p.mkdir(parents=True, exist_ok=True)
        return f"Created folder: {p}"
    except Exception as e:
        return f"Failed to create folder: {e}"


@tool(description="Copies a file to a new destination.", risk_level=RiskLevel.MEDIUM)
def copy_file(source: str, destination: str) -> str:
    """Copies file from source to destination."""
    src = Path(source).expanduser()
    dst = Path(destination).expanduser()
    if not src.exists():
        return f"Source '{src}' does not exist."
    try:
        if dst.is_dir():
            shutil.copy2(src, dst / src.name)
        else:
            shutil.copy2(src, dst)
        return f"Copied '{src.name}' to '{dst}'."
    except Exception as e:
        return f"Copy failed: {e}"


@tool(description="Moves a file or directory to a new location.", risk_level=RiskLevel.MEDIUM)
def move_file(source: str, destination: str) -> str:
    """Moves a file or directory."""
    src = Path(source).expanduser()
    dst = Path(destination).expanduser()
    if not src.exists():
        return f"Source '{src}' does not exist."
    try:
        shutil.move(str(src), str(dst))
        return f"Moved '{src}' to '{dst}'."
    except Exception as e:
        return f"Move failed: {e}"


@tool(description="Renames a file or folder.", risk_level=RiskLevel.MEDIUM)
def rename_file(old_path: str, new_name: str) -> str:
    """Renames file or folder in place."""
    p = Path(old_path).expanduser()
    if not p.exists():
        return f"Path '{p}' does not exist."
    new_p = p.parent / new_name
    try:
        p.rename(new_p)
        return f"Renamed to '{new_p.name}'."
    except Exception as e:
        return f"Rename failed: {e}"


@tool(description="Safely deletes a file by sending it to the Windows Recycle Bin (reversible).", risk_level=RiskLevel.DANGEROUS)
def delete_file(path: str) -> str:
    """Moves a file to the Recycle Bin."""
    p = Path(path).expanduser()
    if not p.exists():
        return f"File '{p}' does not exist."
    if not p.is_file():
        return f"Path '{p}' is a folder, use delete_folder instead."
    try:
        send2trash.send2trash(str(p))
        return f"File '{p.name}' moved to Recycle Bin (can be restored)."
    except Exception as e:
        return f"Failed to delete file: {e}"


@tool(description="Safely deletes a directory by sending it to the Windows Recycle Bin (reversible).", risk_level=RiskLevel.DANGEROUS)
def delete_folder(path: str) -> str:
    """Moves a folder to the Recycle Bin."""
    p = Path(path).expanduser()
    if not p.exists():
        return f"Folder '{p}' does not exist."
    if not p.is_dir():
        return f"Path '{p}' is a file, use delete_file instead."
    try:
        send2trash.send2trash(str(p))
        return f"Folder '{p.name}' moved to Recycle Bin (can be restored)."
    except Exception as e:
        return f"Failed to delete folder: {e}"


@tool(description="Creates a zip archive from a file or folder.", risk_level=RiskLevel.MEDIUM)
def zip_files(folder_path: str, zip_path: str = "") -> str:
    """Zips folder contents."""
    src = Path(folder_path).expanduser()
    if not src.exists():
        return f"Source path '{src}' does not exist."
    out_zip = Path(zip_path).expanduser() if zip_path else src.with_suffix(".zip")
    try:
        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            if src.is_file():
                zf.write(src, arcname=src.name)
            else:
                for root, _, files in os.walk(src):
                    for file in files:
                        full_p = Path(root) / file
                        arcname = full_p.relative_to(src)
                        zf.write(full_p, arcname=arcname)
        return f"Created zip archive: {out_zip}"
    except Exception as e:
        return f"Zip creation failed: {e}"


@tool(description="Extracts a zip archive into a destination folder.", risk_level=RiskLevel.MEDIUM)
def unzip_file(zip_path: str, extract_to: str = "") -> str:
    """Extracts a zip file."""
    src = Path(zip_path).expanduser()
    if not src.exists():
        return f"Zip file '{src}' does not exist."
    out_dir = Path(extract_to).expanduser() if extract_to else src.parent / src.stem
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(src, "r") as zf:
            zf.extractall(out_dir)
        return f"Extracted {len(zf.namelist())} files to: {out_dir}"
    except Exception as e:
        return f"Unzip failed: {e}"
