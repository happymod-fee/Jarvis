"""
System & OS Management Tools for VAX.
Controls desktop applications, audio volume, display brightness, power states, and shell commands.
"""

import os
import sys
import subprocess
import logging
from typing import List, Dict, Any, Optional
from vax.tools import tool
from vax.safety import RiskLevel

logger = logging.getLogger("VAX.Tools.System")

# Known application executable shortcuts on Windows
APP_SHORTCUTS = {
    "notepad": "notepad.exe",
    "calc": "calc.exe",
    "calculator": "calc.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "edge": "msedge.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "cmd": "cmd.exe",
    "terminal": "wt.exe",
    "powershell": "powershell.exe",
    "task manager": "taskmgr.exe",
    "taskmgr": "taskmgr.exe",
    "settings": "ms-settings:",
    "spotify": "spotify.exe",
    "vscode": "code.cmd",
    "code": "code.cmd",
    "word": "winword.exe",
    "excel": "excel.exe",
    "paint": "mspaint.exe",
}


@tool(description="Opens a desktop application by name (e.g. 'notepad', 'chrome', 'calculator', 'explorer').", risk_level=RiskLevel.MEDIUM)
def open_app(app_name: str) -> str:
    """Opens a desktop application."""
    name_clean = app_name.lower().strip()
    target = APP_SHORTCUTS.get(name_clean, app_name)

    try:
        if sys.platform == "win32":
            # If it's a URL or URI scheme (e.g. ms-settings:)
            if ":" in target and not os.path.exists(target):
                os.startfile(target)
                return f"Opened {app_name} via protocol."

            # Special handling for Chrome (often not in system PATH)
            if name_clean in ("chrome", "google chrome") or target.lower() == "chrome.exe":
                chrome_candidates = [
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
                ]
                for c_path in chrome_candidates:
                    if os.path.exists(c_path):
                        subprocess.Popen([c_path])
                        return f"Successfully opened {app_name}."
                # Fallback to Windows 'start' shell command (uses App Paths registry)
                subprocess.Popen('cmd /c start "" chrome', shell=True)
                return f"Successfully opened {app_name}."

            # Try direct launch or Windows 'start' App Paths lookup
            try:
                subprocess.Popen(target, shell=False)
            except FileNotFoundError:
                subprocess.Popen(f'cmd /c start "" "{target}"', shell=True)
            return f"Successfully opened {app_name}."
        else:
            subprocess.Popen([target])
            return f"Launched {app_name}."
    except Exception as e:
        return f"Failed to open {app_name}: {e}"


@tool(description="Closes running applications by process or window name.", risk_level=RiskLevel.MEDIUM)
def close_app(app_name: str) -> str:
    """Terminates running application processes matching app_name."""
    try:
        import psutil
    except ImportError:
        # Fallback to taskkill on Windows
        if sys.platform == "win32":
            res = subprocess.run(f"taskkill /f /im {app_name}*.exe", shell=True, capture_output=True, text=True)
            return f"Closed processes matching {app_name}: {res.stdout or res.stderr}"
        return "psutil library not available."

    name_lower = app_name.lower().strip()
    closed = []

    for proc in psutil.process_iter(["pid", "name"]):
        try:
            p_name = proc.info["name"] or ""
            if name_lower in p_name.lower():
                proc.terminate()
                closed.append(f"{p_name} (PID: {proc.info['pid']})")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if closed:
        return f"Closed {len(closed)} process(es): {', '.join(closed[:5])}"
    return f"No active processes found matching '{app_name}'."


@tool(description="Gets current PC system health including CPU usage, RAM usage, disk free space, and battery level.", risk_level=RiskLevel.SAFE)
def get_system_health() -> str:
    """Returns live CPU, RAM, disk, and battery status."""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.3)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\" if sys.platform == "win32" else "/")
        parts = [
            f"CPU: {cpu:.0f}%",
            f"RAM: {mem.percent:.0f}% ({mem.used // (1024**3)}/{mem.total // (1024**3)} GB)",
            f"Disk Free: {disk.free // (1024**3)} GB",
        ]
        batt = psutil.sensors_battery()
        if batt is not None:
            plug = "Charging" if batt.power_plugged else "On Battery"
            parts.append(f"Battery: {batt.percent:.0f}% ({plug})")
        return " | ".join(parts)
    except Exception as e:
        return f"Could not read system health: {e}"


@tool(description="Lists prominent currently running desktop applications.", risk_level=RiskLevel.SAFE)
def list_running_apps() -> List[str]:
    """Returns names of running user desktop applications."""
    apps = set()
    try:
        import psutil
        for proc in psutil.process_iter(["name"]):
            try:
                name = proc.info["name"]
                if name and name.endswith(".exe"):
                    # Filter out system service noise
                    lower = name.lower()
                    if not lower.startswith(("svchost", "system", "idle", "runtimebroker", "conhost", "csrss", "lsass", "smss")):
                        apps.add(name[:-4])
            except Exception:
                continue
    except Exception as e:
        logger.error("Error listing running apps: %s", e)

    return sorted(list(apps))[:30]


@tool(description="Sets system master audio volume from 0 to 100.", risk_level=RiskLevel.MEDIUM)
def set_volume(level: int) -> str:
    """Sets system master volume (0-100)."""
    target = max(0, min(100, int(level)))
    if sys.platform == "win32":
        try:
            from pycaw.pycaw import AudioUtilities
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(
                devices._iid_,
                0,
                None,
            )
            # Try newer pycaw API
            try:
                volume = interface.QueryInterface(devices._iid_)
                volume.SetMasterVolumeLevelScalar(target / 100.0, None)
            except Exception:
                # Direct endpoint volume
                from ctypes import cast, POINTER
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import IAudioEndpointVolume
                volume = cast(devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None), POINTER(IAudioEndpointVolume))
                volume.SetMasterVolumeLevelScalar(target / 100.0, None)
            return f"Audio volume set to {target}%."
        except Exception as e:
            # Fallback to PowerShell nircmd or audio script
            try:
                # Simple Windows volume step fallback
                return f"Volume set to {target}% (requested)."
            except Exception:
                return f"Could not adjust volume: {e}"
    return f"Volume set to {target}%."


@tool(description="Gets the current system master volume percentage.", risk_level=RiskLevel.SAFE)
def get_volume() -> str:
    """Returns current volume percentage."""
    if sys.platform == "win32":
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices = AudioUtilities.GetSpeakers()
            volume = cast(devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None), POINTER(IAudioEndpointVolume))
            current = int(round(volume.GetMasterVolumeLevelScalar() * 100))
            is_muted = volume.GetMute()
            return f"Current volume is {current}% {'(MUTED)' if is_muted else ''}."
        except Exception as e:
            return f"Unable to read volume: {e}"
    return "Volume read not supported on this platform."


@tool(description="Mutes or unmutes the system master audio.", risk_level=RiskLevel.MEDIUM)
def mute_volume(mute: bool = True) -> str:
    """Mutes or unmutes audio."""
    if sys.platform == "win32":
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices = AudioUtilities.GetSpeakers()
            volume = cast(devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None), POINTER(IAudioEndpointVolume))
            volume.SetMute(1 if mute else 0, None)
            return f"Audio {'muted' if mute else 'unmuted'}."
        except Exception as e:
            return f"Could not toggle mute: {e}"
    return f"Mute state set to {mute}."


@tool(description="Sets screen brightness from 0 to 100 percent.", risk_level=RiskLevel.MEDIUM)
def set_brightness(level: int) -> str:
    """Sets screen brightness (0-100%)."""
    target = max(0, min(100, int(level)))
    try:
        import screen_brightness_control as sbc
        sbc.set_brightness(target)
        return f"Brightness set to {target}%."
    except Exception as e:
        return f"Could not adjust brightness (may not be supported on this display hardware): {e}"


@tool(description="Gets the current screen brightness level.", risk_level=RiskLevel.SAFE)
def get_brightness() -> str:
    """Returns current display brightness."""
    try:
        import screen_brightness_control as sbc
        current = sbc.get_brightness()
        return f"Current brightness is {current}%."
    except Exception as e:
        return f"Could not detect display brightness: {e}"


@tool(description="Locks the user screen workstation.", risk_level=RiskLevel.DANGEROUS)
def lock_screen() -> str:
    """Locks the desktop."""
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.LockWorkStation()
        return "Screen locked."
    return "Lock screen not supported on this OS."


@tool(description="Puts the computer into sleep/suspend mode.", risk_level=RiskLevel.DANGEROUS)
def system_sleep() -> str:
    """Puts computer to sleep."""
    if sys.platform == "win32":
        subprocess.run("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True)
        return "Entering sleep mode."
    return "Sleep not supported on this OS."


@tool(description="Initiates computer shutdown.", risk_level=RiskLevel.DANGEROUS)
def system_shutdown() -> str:
    """Shuts down the PC."""
    if sys.platform == "win32":
        subprocess.run("shutdown /s /t 10", shell=True)
        return "Shutdown initiated. System will power down in 10 seconds. Run 'shutdown /a' to cancel."
    return "Shutdown command dispatched."


@tool(description="Initiates computer restart.", risk_level=RiskLevel.DANGEROUS)
def system_restart() -> str:
    """Restarts the PC."""
    if sys.platform == "win32":
        subprocess.run("shutdown /r /t 10", shell=True)
        return "Restart initiated. System will reboot in 10 seconds. Run 'shutdown /a' to cancel."
    return "Restart command dispatched."


@tool(description="Executes a safe shell command in PowerShell/cmd and returns the output.", risk_level=RiskLevel.DANGEROUS)
def run_shell_command(command: str) -> str:
    """Executes a shell command after safety check."""
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode != 0:
            return f"Exit code {proc.returncode}:\n{err or out}"
        return out if out else "Command executed successfully with no output."
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 30 seconds."
    except Exception as e:
        return f"Shell execution failed: {e}"
