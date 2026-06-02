"""
NEXA -- Module Dispatcher  v2.0
Receives JSON commands from the reasoning engine and routes them to the
correct handler.  Now includes:

 - Intelligent app search via nexa_app_finder (cross-platform)
 - Clipboard, network, notifications, screen-lock, brightness, battery,
   service management, scheduled tasks, and more
 - Full Windows + Linux parity for every action
"""

import json
import subprocess
import platform
import os
import sys
import datetime
import shutil
import shlex
import re
import textwrap

try:
    import psutil
except ImportError:
    psutil = None

from nexa_app_finder import app_index, AppEntry
from nexa_smart_actions import (
    web_search, open_website, multi_search, smart_open,
    download_url, web_scrape_text, chain_actions,
    list_web_services, list_direct_sites,
    WEB_SERVICES, DIRECT_URLS,
)

SYSTEM = platform.system()  # 'Darwin', 'Windows', 'Linux'

# ======================================================================
# HELPERS
# ======================================================================

def _expand(p: str) -> str:
    return os.path.expanduser(os.path.expandvars(p))


def _popen_detached(cmd_list, cwd=None):
    """Start a process fully detached from the current terminal."""
    if SYSTEM == "Windows":
        CREATE_NEW = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        return subprocess.Popen(cmd_list, cwd=cwd, creationflags=CREATE_NEW, close_fds=True)
    return subprocess.Popen(
        cmd_list, cwd=cwd,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

# ======================================================================
# system_control HANDLER
# ======================================================================

# ── Common alias tables (kept for instant resolution before search) ──

ALIASES_WIN = {
    "chrome": "chrome", "google chrome": "chrome", "google": "chrome",
    "firefox": "firefox", "mozilla firefox": "firefox", "mozilla": "firefox",
    "edge": "msedge", "microsoft edge": "msedge",
    "brave": "brave", "opera": "opera",
    "notepad": "notepad", "notepad++": "notepad++", "bloc de notas": "notepad",
    "explorer": "explorer", "file explorer": "explorer",
    "explorador de archivos": "explorer", "explorador": "explorer",
    "cmd": "cmd", "command prompt": "cmd",
    "powershell": "powershell",
    "terminal": "wt", "windows terminal": "wt",
    "task manager": "taskmgr", "administrador de tareas": "taskmgr",
    "control panel": "control", "panel de control": "control",
    "settings": "ms-settings:", "configuracion": "ms-settings:",
    "registry": "regedit", "registro": "regedit",
    "word": "winword", "microsoft word": "winword",
    "excel": "excel", "microsoft excel": "excel",
    "powerpoint": "powerpnt", "microsoft powerpoint": "powerpnt",
    "outlook": "outlook", "microsoft outlook": "outlook",
    "onenote": "onenote",
    "vscode": "code", "visual studio code": "code", "vs code": "code",
    "visual studio": "devenv",
    "git": "git-bash",
    "spotify": "spotify", "discord": "discord", "steam": "steam",
    "vlc": "vlc", "paint": "mspaint",
    "calculator": "calc", "calculadora": "calc",
    "snipping tool": "snippingtool", "recortes": "snippingtool",
    "photos": "ms-photos:", "fotos": "ms-photos:",
    "camera": "microsoft.windows.camera:", "camara": "microsoft.windows.camera:",
    "maps": "bingmaps:", "mapas": "bingmaps:",
    "mail": "outlookmail:", "correo": "outlookmail:",
    "store": "ms-windows-store:", "tienda": "ms-windows-store:",
    "xbox": "xbox:",
    "3d viewer": "microsoft3dviewer",
    "clock": "ms-clock:", "reloj": "ms-clock:",
    "weather": "bingweather:", "tiempo": "bingweather:",
}

ALIASES_LINUX = {
    "chrome": ["google-chrome", "chromium-browser", "chromium"],
    "google chrome": ["google-chrome", "chromium-browser", "chromium"],
    "firefox": ["firefox"], "mozilla firefox": ["firefox"],
    "terminal": ["gnome-terminal", "xterm", "konsole", "xfce4-terminal"],
    "file manager": ["nautilus", "dolphin", "thunar", "nemo"],
    "text editor": ["gedit", "kate", "mousepad"],
    "vscode": ["code"], "visual studio code": ["code"],
    "spotify": ["spotify"], "discord": ["discord"],
    "calculator": ["gnome-calculator", "kcalc", "xcalc"],
}

ALIASES_MAC = {
    "chrome": "Google Chrome", "google chrome": "Google Chrome",
    "firefox": "Firefox",
    "terminal": "Terminal",
    "finder": "Finder",
    "vscode": "Visual Studio Code", "visual studio code": "Visual Studio Code",
    "spotify": "Spotify", "discord": "Discord",
    "calculator": "Calculator", "safari": "Safari",
    "notes": "Notes", "calendar": "Calendar",
}


def _open_app_smart(name: str) -> str:
    """
    Resolve an app name and launch it.
    Strategy:
      1. Alias table (instant)
      2. nexa_app_finder search (system-wide)
      3. Legacy fallbacks (shutil.which, xdg-open, os.startfile, etc.)
    """
    if not name:
        return "Error: no app name provided"

    name_lower = name.lower().strip()

    try:
        # ── macOS ────────────────────────────────────────────────────
        if SYSTEM == "Darwin":
            app_name = ALIASES_MAC.get(name_lower, name)
            result = subprocess.run(["open", "-a", app_name],
                                    capture_output=True, text=True)
            if result.returncode != 0:
                # search fallback
                found = app_index.find_best(name)
                if found:
                    subprocess.run(["open", "-a", found.name], capture_output=True, text=True)
                    return f"Opening {found.name} (found via search)"
                result2 = subprocess.run(["open", name], capture_output=True, text=True)
                if result2.returncode != 0:
                    return f"Could not open '{name}': {result.stderr.strip() or result2.stderr.strip()}"
            return f"Opening {app_name}"

        # ── Windows ──────────────────────────────────────────────────
        elif SYSTEM == "Windows":
            # URLs and existing paths
            if name.startswith(("http://", "https://")):
                os.startfile(name)
                return f"Opening {name}"
            if os.path.exists(_expand(name)):
                os.startfile(_expand(name))
                return f"Opening {name}"

            # 1. Alias lookup
            cmd_name = ALIASES_WIN.get(name_lower)

            # 2. App-finder search if alias missed
            if not cmd_name:
                found = app_index.find_best(name)
                if found:
                    if found.source == "uwp":
                        # UWP: use explorer shell:AppsFolder trick
                        subprocess.Popen(
                            ["explorer.exe", f"shell:AppsFolder\\{found.exec_cmd}"],
                            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                        )
                        return f"Opening {found.name} (UWP, found via search)"
                    cmd_name = found.exec_cmd

            if not cmd_name:
                cmd_name = name  # raw fallback

            # ms- URI schemes
            if isinstance(cmd_name, str) and (cmd_name.endswith(":") or "ms-" in cmd_name
                    or "bing" in cmd_name or "microsoft." in cmd_name):
                try:
                    os.startfile(cmd_name)
                    return f"Opening {name}"
                except Exception as e:
                    return f"Error opening {name}: {e}"

            # PATH lookup
            binpath = shutil.which(cmd_name) or shutil.which(cmd_name + ".exe")
            if binpath:
                _popen_detached([binpath])
                return f"Opening {name} ({binpath})"

            # os.startfile (shell association)
            try:
                os.startfile(cmd_name)
                return f"Opening {name}"
            except OSError:
                pass

            # PowerShell Start-Process
            r = subprocess.run(
                ["powershell", "-WindowStyle", "Hidden", "-NonInteractive",
                 "-Command", f'Start-Process "{cmd_name}"'],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                return f"Opening {name}"

            # Shell start
            subprocess.Popen(f'start "" "{cmd_name}"', shell=True)
            return f"Opening {name} (via shell)"

        # ── Linux ────────────────────────────────────────────────────
        else:
            # URLs and existing paths
            if name.startswith(("http://", "https://")) or os.path.exists(name):
                subprocess.Popen(["xdg-open", name],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"Opening {name}"

            # 1. Alias list
            candidates = ALIASES_LINUX.get(name_lower, [])
            for candidate in candidates:
                binpath = shutil.which(candidate)
                if binpath:
                    _popen_detached([binpath])
                    return f"Opening {name} ({binpath})"

            # 2. App-finder search (parses .desktop files, Flatpak, Snap)
            found = app_index.find_best(name)
            if found:
                if found.desktop_file and found.desktop_file.endswith(".desktop"):
                    # Use gtk-launch or gio for proper .desktop execution
                    gtk_launch = shutil.which("gtk-launch")
                    if gtk_launch:
                        desktop_id = os.path.basename(found.desktop_file)
                        _popen_detached([gtk_launch, desktop_id])
                        return f"Opening {found.name} (via gtk-launch, found via search)"
                    gio = shutil.which("gio")
                    if gio:
                        _popen_detached([gio, "launch", found.desktop_file])
                        return f"Opening {found.name} (via gio, found via search)"
                # Direct exec
                exe = shutil.which(found.exec_cmd) or found.exec_cmd
                _popen_detached([exe] + found.exec_args)
                return f"Opening {found.name} ({exe}, found via search)"

            # 3. Direct binary name
            binpath = shutil.which(name_lower) or shutil.which(name)
            if binpath:
                _popen_detached([binpath])
                return f"Opening {name} ({binpath})"

            # 4. xdg-open last resort
            subprocess.Popen(f"xdg-open '{name}' 2>/dev/null || {name} &",
                             shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Attempted to open {name} (verify it launched)"

    except Exception as e:
        return f"Error opening '{name}': {e}"


def handle_system_control(action, params):
    """Route system_control actions."""

    # ── APP LAUNCH ────────────────────────────────────────────────

    if action == "open_app":
        return _open_app_smart(params.get("name", ""))

    elif action == "open_app_advanced":
        name = params.get("name", "")
        args = params.get("args", []) or []
        cwd = params.get("cwd")
        background = params.get("background", True)
        try:
            if cwd:
                cwd = _expand(cwd)

            # Try to resolve via finder first
            resolved = None
            found = app_index.find_best(name)
            if found:
                resolved = shutil.which(found.exec_cmd) or found.exec_cmd
            if not resolved:
                resolved = shutil.which(name) or name

            if SYSTEM == "Darwin":
                if args:
                    subprocess.Popen(["open", "-a", resolved, "--args"] + args, cwd=cwd)
                else:
                    subprocess.Popen(["open", "-a", resolved], cwd=cwd)
            elif SYSTEM == "Windows":
                if background:
                    _popen_detached([resolved] + args, cwd=cwd)
                else:
                    subprocess.run([resolved] + args, cwd=cwd, check=True)
            else:
                if background:
                    _popen_detached([resolved] + args, cwd=cwd)
                else:
                    subprocess.run([resolved] + args, cwd=cwd, check=True)
            return f"Launched {name} with arguments: {' '.join(map(str, args))}"
        except Exception as e:
            return f"Error launching {name}: {e}"

    # ── APP / PROCESS SEARCH ──────────────────────────────────────

    elif action == "search_apps":
        query = params.get("query", "")
        limit = int(params.get("limit", 10))
        results = app_index.search(query, limit=limit)
        if not results:
            return f"No apps found matching '{query}'"
        lines = []
        for entry, score in results:
            lines.append(f"  {entry.name}  ({entry.exec_cmd})  [score={score:.0f}, src={entry.source}]")
        return f"Found {len(results)} apps for '{query}':\n" + "\n".join(lines)

    elif action == "list_installed_apps":
        category = params.get("category", "")
        limit = int(params.get("limit", 50))
        if category:
            apps = app_index.by_category(category, limit=limit)
        else:
            apps = app_index.list_all()[:limit]
        if not apps:
            return "No installed apps found (try refreshing: search_apps with a query)"
        lines = [f"  {a.name}  ({a.source})" for a in apps]
        return f"Installed apps ({len(apps)}):\n" + "\n".join(lines)

    elif action == "list_app_categories":
        cats = app_index.list_categories()
        return f"Categories ({len(cats)}): {', '.join(cats)}" if cats else "No categories indexed"

    elif action == "refresh_app_index":
        count = app_index.refresh(force=True)
        return f"App index refreshed: {count} applications indexed"

    elif action == "find_and_open_app":
        """Search for an app; open it if found, otherwise install then open."""
        name = params.get("name", "")
        if not name:
            return "Error: 'name' parameter required"
        # 1. Search locally
        results = app_index.search(name, limit=5)
        if results:
            best, score = results[0]
            open_result = _open_app_smart(best.name)
            return f"Found '{best.name}' (score={score:.0f}). {open_result}"
        # 2. Not found — try to install
        install_result = handle_system_control(
            "install_package", {"name": name, "manager": "auto"}
        )
        # 3. Refresh index and try to open
        app_index.refresh(force=True)
        results = app_index.search(name, limit=3)
        if results:
            best, score = results[0]
            open_result = _open_app_smart(best.name)
            return f"{install_result}\n{open_result}"
        return f"{install_result}\nNote: installed but could not auto-open. Try: open_app"

    # ── COMMAND EXECUTION ─────────────────────────────────────────

    elif action == "execute_command":
        cmd = params.get("command", "")
        args = params.get("args", [])
        shell = params.get("shell", False)
        background = params.get("background", False)
        timeout = int(params.get("timeout", 60))
        working_dir = params.get("cwd")
        if working_dir:
            working_dir = _expand(working_dir)
        try:
            if isinstance(args, list):
                full_cmd_list = [cmd] + args
                full_cmd_str = " ".join(shlex.quote(str(x)) for x in full_cmd_list)
            else:
                full_cmd_str = f"{cmd} {args}".strip()

            if background:
                if SYSTEM == "Windows":
                    subprocess.Popen(full_cmd_str, shell=True, cwd=working_dir,
                                     creationflags=0x08000000)
                else:
                    subprocess.Popen(full_cmd_str, shell=True, cwd=working_dir,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     start_new_session=True)
                return f"Command '{cmd}' started in background"

            if shell or isinstance(args, str):
                result = subprocess.run(full_cmd_str, shell=True, capture_output=True,
                                        text=True, timeout=timeout, cwd=working_dir)
            elif isinstance(args, list):
                result = subprocess.run([cmd] + args, shell=False, capture_output=True,
                                        text=True, timeout=timeout, cwd=working_dir)
            else:
                result = subprocess.run(full_cmd_str, shell=True, capture_output=True,
                                        text=True, timeout=timeout, cwd=working_dir)
            output = result.stdout.strip() or result.stderr.strip()
            return output or f"Command '{cmd}' executed (exit {result.returncode})"
        except subprocess.TimeoutExpired:
            return f"Command '{cmd}' timed out after {timeout}s"
        except Exception as e:
            return f"Error executing command: {e}"

    # ── PIPE / CHAIN COMMANDS ─────────────────────────────────────

    elif action == "execute_pipe":
        """Execute a piped shell command string (e.g. 'ls -la | grep .py | wc -l')."""
        command_string = params.get("command", "")
        timeout = int(params.get("timeout", 60))
        try:
            result = subprocess.run(command_string, shell=True, capture_output=True,
                                    text=True, timeout=timeout)
            output = result.stdout.strip() or result.stderr.strip()
            return output or f"Pipe executed (exit {result.returncode})"
        except subprocess.TimeoutExpired:
            return f"Pipe timed out after {timeout}s"
        except Exception as e:
            return f"Error: {e}"

    # ── SCREENSHOT / RECORDING ────────────────────────────────────

    elif action == "screenshot":
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = _expand(params.get("output", f"~/Desktop/nexa_screenshot_{ts}.png"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if SYSTEM == "Darwin":
            subprocess.run(["screencapture", path])
        elif SYSTEM == "Linux":
            # Try multiple screenshot tools
            for tool_cmd in [
                ["scrot", path],
                ["gnome-screenshot", "-f", path],
                ["import", "-window", "root", path],   # ImageMagick
                ["xfce4-screenshooter", "-f", "-s", path],
            ]:
                if shutil.which(tool_cmd[0]):
                    subprocess.run(tool_cmd)
                    break
            else:
                try:
                    from PIL import ImageGrab
                    ImageGrab.grab().save(path)
                except ImportError:
                    return "No screenshot tool found. Install scrot: sudo apt install scrot"
        elif SYSTEM == "Windows":
            try:
                from PIL import ImageGrab
                ImageGrab.grab().save(path)
            except ImportError:
                return "Install Pillow for screenshots: pip install pillow"
        return f"Screenshot saved to {path}"

    elif action == "record_screen":
        operation = params.get("operation", "start")
        duration = params.get("duration_seconds", 0)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = _expand(params.get("output", f"~/Desktop/nexa_recording_{ts}.mp4"))
        try:
            if SYSTEM == "Darwin":
                if operation == "start":
                    cmd_args = ["screencapture", "-V", str(duration) if duration else "3600", out_path]
                    proc = subprocess.Popen(cmd_args)
                    return f"Screen recording started -> {out_path}  (PID {proc.pid})"
                else:
                    subprocess.run(["pkill", "-f", "screencapture"])
                    return "Screen recording stopped."
            elif SYSTEM == "Linux":
                ffmpeg = shutil.which("ffmpeg")
                if operation == "start":
                    if not ffmpeg:
                        return "ffmpeg not found. Install: sudo apt install ffmpeg"
                    display = os.environ.get("DISPLAY", ":0")
                    cmd_args = [ffmpeg, "-y", "-f", "x11grab", "-framerate", "30",
                                "-i", display, "-c:v", "libx264", "-preset", "ultrafast", out_path]
                    if duration:
                        cmd_args.insert(cmd_args.index("-i"), "-t")
                        cmd_args.insert(cmd_args.index("-t") + 1, str(duration))
                    proc = subprocess.Popen(cmd_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return f"Screen recording started -> {out_path}  (PID {proc.pid})"
                else:
                    subprocess.run(["pkill", "-f", "ffmpeg"])
                    return "Screen recording stopped."
            elif SYSTEM == "Windows":
                ffmpeg = shutil.which("ffmpeg")
                if operation == "start":
                    if ffmpeg:
                        cmd_args = [ffmpeg, "-y", "-f", "gdigrab", "-framerate", "30",
                                    "-i", "desktop", "-c:v", "libx264", "-preset", "ultrafast", out_path]
                        proc = subprocess.Popen(cmd_args, creationflags=0x08000000)
                        return f"Screen recording started -> {out_path}  (PID {proc.pid})"
                    else:
                        subprocess.run(["powershell", "-Command",
                            "Add-Type -AssemblyName System.Windows.Forms; "
                            "[System.Windows.Forms.SendKeys]::SendWait('%{F9}')"])
                        return "Triggered Xbox Game Bar recording. Install ffmpeg for full control."
                else:
                    subprocess.run(["taskkill", "/f", "/im", "ffmpeg.exe"], shell=True)
                    return "Screen recording stopped."
        except Exception as e:
            return f"Error with screen recording: {e}"

    # ── VOLUME ────────────────────────────────────────────────────

    elif action == "set_volume":
        level = int(params.get("level", 50))
        level = max(0, min(100, level))
        if SYSTEM == "Darwin":
            subprocess.run(["osascript", "-e", f"set volume output volume {level}"])
        elif SYSTEM == "Linux":
            # Try multiple tools
            if shutil.which("pactl"):
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"])
            elif shutil.which("amixer"):
                subprocess.run(["amixer", "-q", "sset", "Master", f"{level}%"])
            else:
                return "No volume control found. Install pulseaudio or alsa-utils."
        elif SYSTEM == "Windows":
            try:
                from ctypes import cast, POINTER
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = cast(interface, POINTER(IAudioEndpointVolume))
                volume.SetMasterVolumeLevelScalar(level / 100, None)
            except ImportError:
                return "Install pycaw: pip install pycaw comtypes"
        return f"Volume set to {level}%"

    elif action == "get_volume":
        try:
            if SYSTEM == "Linux":
                if shutil.which("pactl"):
                    r = subprocess.run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
                                       capture_output=True, text=True)
                    return r.stdout.strip()
                elif shutil.which("amixer"):
                    r = subprocess.run(["amixer", "get", "Master"], capture_output=True, text=True)
                    return r.stdout.strip()
            elif SYSTEM == "Darwin":
                r = subprocess.run(["osascript", "-e", "output volume of (get volume settings)"],
                                   capture_output=True, text=True)
                return f"Volume: {r.stdout.strip()}%"
            elif SYSTEM == "Windows":
                from ctypes import cast, POINTER
                from comtypes import CLSCTX_ALL
                from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                devices = AudioUtilities.GetSpeakers()
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = cast(interface, POINTER(IAudioEndpointVolume))
                level = volume.GetMasterVolumeLevelScalar() * 100
                return f"Volume: {level:.0f}%"
        except Exception as e:
            return f"Error getting volume: {e}"

    # ── MUTE / UNMUTE ─────────────────────────────────────────────

    elif action == "toggle_mute":
        try:
            if SYSTEM == "Linux":
                if shutil.which("pactl"):
                    subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
                elif shutil.which("amixer"):
                    subprocess.run(["amixer", "-q", "sset", "Master", "toggle"])
                return "Mute toggled"
            elif SYSTEM == "Darwin":
                subprocess.run(["osascript", "-e",
                    "set volume with output muted not (output muted of (get volume settings))"])
                return "Mute toggled"
            elif SYSTEM == "Windows":
                # nircmd alternative or pycaw
                subprocess.run(["powershell", "-Command",
                    "(New-Object -ComObject WScript.Shell).SendKeys([char]173)"])
                return "Mute toggled"
        except Exception as e:
            return f"Error toggling mute: {e}"

    # ── PROCESS MANAGEMENT ────────────────────────────────────────

    elif action == "close_app":
        name = params.get("name", "")
        if SYSTEM == "Darwin":
            subprocess.run(["pkill", "-x", name])
        elif SYSTEM == "Linux":
            subprocess.run(["pkill", name])
        elif SYSTEM == "Windows":
            subprocess.run(["taskkill", "/f", "/im", f"{name}.exe"], shell=True)
        return f"Closed {name}"

    elif action == "kill_process":
        pid = params.get("pid")
        name = params.get("name")
        signal_num = params.get("signal", "9")
        if pid:
            try:
                if SYSTEM == "Windows":
                    subprocess.run(["taskkill", "/f", "/pid", str(pid)], shell=True)
                else:
                    subprocess.run(["kill", f"-{signal_num}", str(pid)])
                return f"Process {pid} terminated (signal {signal_num})"
            except Exception as e:
                return f"Error killing process: {e}"
        elif name:
            if SYSTEM == "Windows":
                subprocess.run(["taskkill", "/f", "/im", f"{name}.exe"], shell=True)
            else:
                subprocess.run(["pkill", f"-{signal_num}", name])
            return f"Process '{name}' terminated"
        return "Provide either 'pid' or 'name'"

    elif action == "list_processes":
        top_n = int(params.get("limit", 30))
        sort_by = params.get("sort", "cpu")  # cpu | memory | name
        try:
            if psutil:
                procs = []
                for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
                    info = p.info
                    procs.append(info)
                if sort_by == "memory":
                    procs.sort(key=lambda x: x.get("memory_percent", 0) or 0, reverse=True)
                elif sort_by == "name":
                    procs.sort(key=lambda x: (x.get("name") or "").lower())
                else:
                    procs.sort(key=lambda x: x.get("cpu_percent", 0) or 0, reverse=True)
                lines = [f"{'PID':>7}  {'CPU%':>5}  {'MEM%':>5}  {'STATUS':<10}  NAME"]
                for p in procs[:top_n]:
                    lines.append(
                        f"{p.get('pid','?'):>7}  "
                        f"{p.get('cpu_percent',0) or 0:>5.1f}  "
                        f"{p.get('memory_percent',0) or 0:>5.1f}  "
                        f"{(p.get('status') or '?'):<10}  "
                        f"{p.get('name','?')}"
                    )
                return "\n".join(lines)
            else:
                if SYSTEM == "Windows":
                    r = subprocess.run(["tasklist"], capture_output=True, text=True)
                else:
                    r = subprocess.run(["ps", "aux", "--sort=-%cpu"], capture_output=True, text=True)
                return "\n".join(r.stdout.splitlines()[:top_n + 1])
        except Exception as e:
            return f"Error listing processes: {e}"

    # ── FILE OPERATIONS ───────────────────────────────────────────

    elif action == "open_file":
        path = _expand(params.get("path", ""))
        if SYSTEM == "Darwin":
            subprocess.Popen(["open", path])
        elif SYSTEM == "Windows":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Opening file: {path}"

    elif action == "open_directory":
        path = _expand(params.get("path", ""))
        try:
            if SYSTEM == "Darwin":
                subprocess.Popen(["open", path])
            elif SYSTEM == "Windows":
                os.startfile(path)
            else:
                subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Opened directory: {path}"
        except Exception as e:
            return f"Error opening directory: {e}"

    elif action == "open_url":
        url = params.get("url", "")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            if SYSTEM == "Darwin":
                subprocess.Popen(["open", url])
            elif SYSTEM == "Windows":
                os.startfile(url)
            else:
                subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Opening URL: {url}"
        except Exception as e:
            return f"Error opening URL: {e}"

    elif action == "create_file":
        path = _expand(params.get("path", ""))
        content = params.get("content", "")
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w") as f:
                f.write(content)
            return f"File created: {path}"
        except Exception as e:
            return f"Error creating file: {e}"

    elif action == "read_file":
        path = _expand(params.get("path", ""))
        max_lines = params.get("max_lines", 50)
        encoding = params.get("encoding", "utf-8")
        try:
            with open(path, "r", encoding=encoding, errors="replace") as f:
                lines = f.readlines()[:max_lines]
            return "".join(lines)
        except Exception as e:
            return f"Error reading file: {e}"

    elif action == "delete_file":
        path = _expand(params.get("path", ""))
        try:
            if os.path.isfile(path):
                os.remove(path)
                return f"File deleted: {path}"
            elif os.path.isdir(path):
                shutil.rmtree(path)
                return f"Directory deleted: {path}"
            return f"Not found: {path}"
        except Exception as e:
            return f"Error deleting: {e}"

    elif action == "copy_file":
        src = _expand(params.get("src", ""))
        dst = _expand(params.get("dst", ""))
        try:
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
                shutil.copy2(src, dst)
            return f"Copied: {src} -> {dst}"
        except Exception as e:
            return f"Error copying: {e}"

    elif action == "move_file":
        src = _expand(params.get("src", ""))
        dst = _expand(params.get("dst", ""))
        try:
            shutil.move(src, dst)
            return f"Moved: {src} -> {dst}"
        except Exception as e:
            return f"Error moving: {e}"

    elif action == "list_directory":
        path = _expand(params.get("path", "."))
        recursive = params.get("recursive", False)
        pattern = params.get("pattern", "")
        try:
            if recursive:
                items = []
                for root, dirs, files in os.walk(path):
                    for f in files:
                        rel = os.path.relpath(os.path.join(root, f), path)
                        if not pattern or re.search(pattern, rel, re.I):
                            items.append(rel)
                return f"Files ({len(items)}):\n" + "\n".join(items[:200])
            else:
                entries = os.listdir(path)
                dirs = sorted(d for d in entries if os.path.isdir(os.path.join(path, d)))
                files = sorted(f for f in entries if os.path.isfile(os.path.join(path, f)))
                if pattern:
                    dirs = [d for d in dirs if re.search(pattern, d, re.I)]
                    files = [f for f in files if re.search(pattern, f, re.I)]
                return f"Directories ({len(dirs)}): {dirs}\nFiles ({len(files)}): {files}"
        except Exception as e:
            return f"Error listing directory: {e}"

    elif action == "create_directory":
        path = _expand(params.get("path", ""))
        try:
            os.makedirs(path, exist_ok=True)
            return f"Directory created: {path}"
        except Exception as e:
            return f"Error creating directory: {e}"

    elif action == "find_files":
        """Search for files by name pattern."""
        path = _expand(params.get("path", "."))
        pattern = params.get("pattern", "*")
        max_results = int(params.get("limit", 50))
        results = []
        try:
            for root, dirs, files in os.walk(path):
                for f in files:
                    if re.search(pattern, f, re.I):
                        results.append(os.path.join(root, f))
                    if len(results) >= max_results:
                        break
                if len(results) >= max_results:
                    break
            return f"Found {len(results)} files:\n" + "\n".join(results)
        except Exception as e:
            return f"Error searching files: {e}"

    elif action == "get_file_info":
        """Get detailed file metadata."""
        path = _expand(params.get("path", ""))
        try:
            stat = os.stat(path)
            info = {
                "path": path,
                "size_bytes": stat.st_size,
                "size_human": _human_size(stat.st_size),
                "created": datetime.datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "modified": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "is_file": os.path.isfile(path),
                "is_dir": os.path.isdir(path),
                "is_symlink": os.path.islink(path),
                "permissions": oct(stat.st_mode)[-3:],
            }
            return json.dumps(info, indent=2)
        except Exception as e:
            return f"Error: {e}"

    # ── CLIPBOARD ─────────────────────────────────────────────────

    elif action == "get_clipboard":
        try:
            if SYSTEM == "Linux":
                for tool in ["xclip -selection clipboard -o", "xsel --clipboard --output",
                             "wl-paste"]:
                    prog = tool.split()[0]
                    if shutil.which(prog):
                        r = subprocess.run(tool.split(), capture_output=True, text=True, timeout=5)
                        return r.stdout
                return "No clipboard tool found. Install xclip or xsel."
            elif SYSTEM == "Darwin":
                r = subprocess.run(["pbpaste"], capture_output=True, text=True)
                return r.stdout
            elif SYSTEM == "Windows":
                r = subprocess.run(["powershell", "-Command", "Get-Clipboard"],
                                   capture_output=True, text=True)
                return r.stdout.strip()
        except Exception as e:
            return f"Error reading clipboard: {e}"

    elif action == "set_clipboard":
        text = params.get("text", "")
        try:
            if SYSTEM == "Linux":
                for tool_cmd in [
                    ["xclip", "-selection", "clipboard"],
                    ["xsel", "--clipboard", "--input"],
                    ["wl-copy"],
                ]:
                    if shutil.which(tool_cmd[0]):
                        subprocess.run(tool_cmd, input=text, text=True, timeout=5)
                        return f"Clipboard set ({len(text)} chars)"
                return "No clipboard tool found. Install xclip or xsel."
            elif SYSTEM == "Darwin":
                subprocess.run(["pbcopy"], input=text, text=True)
                return f"Clipboard set ({len(text)} chars)"
            elif SYSTEM == "Windows":
                subprocess.run(["powershell", "-Command", f"Set-Clipboard -Value '{text}'"],
                               timeout=5)
                return f"Clipboard set ({len(text)} chars)"
        except Exception as e:
            return f"Error setting clipboard: {e}"

    # ── NOTIFICATIONS ─────────────────────────────────────────────

    elif action == "notify":
        title = params.get("title", "NEXA")
        message = params.get("message", "")
        urgency = params.get("urgency", "normal")  # low | normal | critical
        try:
            if SYSTEM == "Linux":
                cmd = ["notify-send"]
                if urgency:
                    cmd.extend(["-u", urgency])
                cmd.extend([title, message])
                subprocess.run(cmd)
            elif SYSTEM == "Darwin":
                subprocess.run(["osascript", "-e",
                    f'display notification "{message}" with title "{title}"'])
            elif SYSTEM == "Windows":
                ps = textwrap.dedent(f"""
                    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
                    $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
                    $text = $template.GetElementsByTagName('text')
                    $text[0].AppendChild($template.CreateTextNode('{title}')) | Out-Null
                    $text[1].AppendChild($template.CreateTextNode('{message}')) | Out-Null
                    $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
                    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('NEXA').Show($toast)
                """)
                subprocess.run(["powershell", "-Command", ps], capture_output=True)
            return f"Notification sent: {title}"
        except Exception as e:
            return f"Error sending notification: {e}"

    # ── SCREEN LOCK ───────────────────────────────────────────────

    elif action == "lock_screen":
        try:
            if SYSTEM == "Linux":
                # Try multiple lock tools
                for cmd in [
                    ["loginctl", "lock-session"],
                    ["xdg-screensaver", "lock"],
                    ["gnome-screensaver-command", "-l"],
                    ["xscreensaver-command", "-lock"],
                ]:
                    if shutil.which(cmd[0]):
                        subprocess.run(cmd)
                        return "Screen locked"
                return "No screen locker found."
            elif SYSTEM == "Darwin":
                subprocess.run(["pmset", "displaysleepnow"])
                return "Screen locked"
            elif SYSTEM == "Windows":
                subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"])
                return "Screen locked"
        except Exception as e:
            return f"Error locking screen: {e}"

    # ── BRIGHTNESS ────────────────────────────────────────────────

    elif action == "set_brightness":
        level = int(params.get("level", 50))
        level = max(0, min(100, level))
        try:
            if SYSTEM == "Linux":
                if shutil.which("brightnessctl"):
                    subprocess.run(["brightnessctl", "set", f"{level}%"])
                elif shutil.which("xrandr"):
                    # Normalize 0-100 to 0.0-1.0
                    val = level / 100
                    r = subprocess.run(["xrandr", "--query"], capture_output=True, text=True)
                    for line in r.stdout.splitlines():
                        if " connected" in line:
                            display = line.split()[0]
                            subprocess.run(["xrandr", "--output", display, "--brightness", str(val)])
                            break
                else:
                    return "No brightness tool found. Install brightnessctl."
            elif SYSTEM == "Darwin":
                # brightness via osascript isn't natively supported easily
                return "macOS brightness control requires a third-party tool."
            elif SYSTEM == "Windows":
                subprocess.run(["powershell", "-Command",
                    f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{level})"],
                    capture_output=True)
            return f"Brightness set to {level}%"
        except Exception as e:
            return f"Error setting brightness: {e}"

    # ── NETWORK INFO ──────────────────────────────────────────────

    elif action == "get_network_info":
        try:
            info = {}
            if psutil:
                addrs = psutil.net_if_addrs()
                stats = psutil.net_if_stats()
                nets = {}
                for iface, addr_list in addrs.items():
                    ips = []
                    for addr in addr_list:
                        if addr.family.name in ("AF_INET", "AF_INET6"):
                            ips.append(f"{addr.family.name}: {addr.address}")
                    if ips:
                        is_up = stats.get(iface, None)
                        nets[iface] = {
                            "addresses": ips,
                            "is_up": is_up.isup if is_up else "unknown",
                            "speed_mbps": is_up.speed if is_up else 0,
                        }
                info["interfaces"] = nets
                io = psutil.net_io_counters()
                info["total_sent_mb"] = round(io.bytes_sent / 1024 / 1024, 2)
                info["total_recv_mb"] = round(io.bytes_recv / 1024 / 1024, 2)
            else:
                if SYSTEM == "Windows":
                    r = subprocess.run(["ipconfig"], capture_output=True, text=True)
                else:
                    r = subprocess.run(["ip", "addr"], capture_output=True, text=True)
                info["raw"] = r.stdout[:2000]
            return json.dumps(info, indent=2)
        except Exception as e:
            return f"Error getting network info: {e}"

    elif action == "get_wifi_networks":
        """Scan and list available Wi-Fi networks."""
        try:
            if SYSTEM == "Linux":
                r = subprocess.run(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list"],
                                   capture_output=True, text=True, timeout=15)
                return r.stdout.strip() or "No networks found (or nmcli not available)"
            elif SYSTEM == "Windows":
                r = subprocess.run(["netsh", "wlan", "show", "networks", "mode=bssid"],
                                   capture_output=True, text=True)
                return r.stdout.strip()[:3000]
            elif SYSTEM == "Darwin":
                r = subprocess.run(["/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport", "-s"],
                                   capture_output=True, text=True)
                return r.stdout.strip()
        except Exception as e:
            return f"Error scanning Wi-Fi: {e}"

    elif action == "connect_wifi":
        ssid = params.get("ssid", "")
        password = params.get("password", "")
        try:
            if SYSTEM == "Linux":
                cmd = ["nmcli", "dev", "wifi", "connect", ssid]
                if password:
                    cmd += ["password", password]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                return r.stdout.strip() or r.stderr.strip()
            elif SYSTEM == "Windows":
                # Create profile XML, then connect
                profile = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{ssid}</name><SSIDConfig><SSID><name>{ssid}</name></SSID></SSIDConfig>
    <connectionType>ESS</connectionType><connectionMode>auto</connectionMode>
    <MSM><security><authEncryption><authentication>WPA2PSK</authentication>
    <encryption>AES</encryption></authEncryption><sharedKey><keyType>passPhrase</keyType>
    <protected>false</protected><keyMaterial>{password}</keyMaterial></sharedKey>
    </security></MSM></WLANProfile>"""
                import tempfile
                with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as f:
                    f.write(profile)
                    tmp = f.name
                subprocess.run(["netsh", "wlan", "add", "profile", f"filename={tmp}"], capture_output=True)
                r = subprocess.run(["netsh", "wlan", "connect", f"name={ssid}"], capture_output=True, text=True)
                os.unlink(tmp)
                return r.stdout.strip() or r.stderr.strip()
        except Exception as e:
            return f"Error connecting to Wi-Fi: {e}"

    # ── BATTERY ───────────────────────────────────────────────────

    elif action == "get_battery_info":
        try:
            if psutil and hasattr(psutil, "sensors_battery"):
                bat = psutil.sensors_battery()
                if bat:
                    return json.dumps({
                        "percent": bat.percent,
                        "power_plugged": bat.power_plugged,
                        "time_left_minutes": round(bat.secsleft / 60, 1) if bat.secsleft > 0 else "unlimited/unknown",
                    }, indent=2)
                return "No battery detected (desktop?)"
            if SYSTEM == "Linux":
                r = subprocess.run(["upower", "-i", "/org/freedesktop/UPower/devices/battery_BAT0"],
                                   capture_output=True, text=True)
                return r.stdout.strip()[:2000] if r.stdout else "No battery info"
            elif SYSTEM == "Windows":
                r = subprocess.run(["powershell", "-Command",
                    "(Get-WmiObject Win32_Battery | Select-Object EstimatedChargeRemaining, BatteryStatus | ConvertTo-Json)"],
                    capture_output=True, text=True)
                return r.stdout.strip() or "No battery info"
        except Exception as e:
            return f"Error getting battery info: {e}"

    # ── SYSTEM INFO ───────────────────────────────────────────────

    elif action == "get_system_info":
        try:
            info = {
                "platform": SYSTEM,
                "platform_release": platform.release(),
                "platform_version": platform.version(),
                "architecture": platform.machine(),
                "processor": platform.processor(),
                "hostname": platform.node(),
                "python_version": platform.python_version(),
            }
            if psutil:
                mem = psutil.virtual_memory()
                disk = psutil.disk_usage("/")
                info.update({
                    "cpu_count_physical": psutil.cpu_count(logical=False),
                    "cpu_count_logical": psutil.cpu_count(logical=True),
                    "cpu_percent": psutil.cpu_percent(interval=0.5),
                    "memory_total_gb": round(mem.total / (1024 ** 3), 2),
                    "memory_available_gb": round(mem.available / (1024 ** 3), 2),
                    "memory_percent": mem.percent,
                    "disk_total_gb": round(disk.total / (1024 ** 3), 2),
                    "disk_used_gb": round(disk.used / (1024 ** 3), 2),
                    "disk_free_gb": round(disk.free / (1024 ** 3), 2),
                    "disk_percent": disk.percent,
                    "boot_time": datetime.datetime.fromtimestamp(psutil.boot_time()).isoformat(),
                })
                if hasattr(psutil, "sensors_temperatures"):
                    temps = psutil.sensors_temperatures()
                    if temps:
                        info["temperatures"] = {k: [{"label": s.label, "current": s.current}
                                                    for s in v] for k, v in temps.items()}
            return json.dumps(info, indent=2)
        except Exception as e:
            return f"Error getting system info: {e}"

    elif action == "get_disk_usage":
        path = _expand(params.get("path", "/"))
        try:
            if psutil:
                usage = psutil.disk_usage(path)
                return json.dumps({
                    "path": path,
                    "total_gb": round(usage.total / (1024**3), 2),
                    "used_gb": round(usage.used / (1024**3), 2),
                    "free_gb": round(usage.free / (1024**3), 2),
                    "percent": usage.percent,
                }, indent=2)
            if SYSTEM == "Windows":
                r = subprocess.run(["powershell", "-Command",
                    f"Get-PSDrive -PSProvider FileSystem | Select-Object Name,Used,Free | ConvertTo-Json"],
                    capture_output=True, text=True)
                return r.stdout.strip()
            else:
                r = subprocess.run(["df", "-h", path], capture_output=True, text=True)
                return r.stdout.strip()
        except Exception as e:
            return f"Error: {e}"

    # ── ENVIRONMENT VARIABLES ─────────────────────────────────────

    elif action == "set_environment_variable":
        key = params.get("key", "")
        value = params.get("value", "")
        persistent = params.get("persistent", False)
        try:
            os.environ[key] = value
            if persistent:
                if SYSTEM == "Linux":
                    with open(os.path.expanduser("~/.profile"), "a") as f:
                        f.write(f'\nexport {key}="{value}"\n')
                elif SYSTEM == "Windows":
                    subprocess.run(["setx", key, value], capture_output=True)
            return f"Environment variable set: {key}={value}" + (" (persistent)" if persistent else "")
        except Exception as e:
            return f"Error: {e}"

    elif action == "get_environment_variable":
        key = params.get("key", "")
        default = params.get("default", "not set")
        return os.environ.get(key, default)

    elif action == "list_environment_variables":
        pattern = params.get("pattern", "")
        env = dict(os.environ)
        if pattern:
            env = {k: v for k, v in env.items() if re.search(pattern, k, re.I)}
        lines = [f"{k}={v[:100]}{'...' if len(v) > 100 else ''}" for k, v in sorted(env.items())]
        return "\n".join(lines[:100])

    # ── POWER ACTIONS ─────────────────────────────────────────────

    elif action == "power_action":
        action_type = params.get("type", "").lower()
        force = params.get("force", False)
        delay = int(params.get("delay_seconds", 60))
        try:
            if action_type == "shutdown":
                if SYSTEM == "Windows":
                    t = "0" if force else str(delay)
                    subprocess.run(["shutdown", "/s", "/t", t], shell=True)
                elif SYSTEM == "Darwin":
                    subprocess.run(["osascript", "-e", 'tell application "System Events" to shut down'])
                else:
                    mins = max(1, delay // 60)
                    subprocess.run(["shutdown", "-h", f"+{mins}"])
                return f"Shutdown initiated (delay: {delay}s)"
            elif action_type == "reboot":
                if SYSTEM == "Windows":
                    subprocess.run(["shutdown", "/r", "/t", str(delay)], shell=True)
                elif SYSTEM == "Darwin":
                    subprocess.run(["osascript", "-e", 'tell application "System Events" to restart'])
                else:
                    mins = max(1, delay // 60)
                    subprocess.run(["shutdown", "-r", f"+{mins}"])
                return f"Reboot initiated (delay: {delay}s)"
            elif action_type == "sleep":
                if SYSTEM == "Windows":
                    subprocess.run(["rundll32", "powrprof.dll,SetSuspendState", "0,1,0"], shell=True)
                elif SYSTEM == "Darwin":
                    subprocess.run(["osascript", "-e", 'tell application "System Events" to sleep'])
                else:
                    subprocess.run(["systemctl", "suspend"])
                return "System entering sleep mode"
            elif action_type == "cancel":
                if SYSTEM == "Windows":
                    subprocess.run(["shutdown", "/a"], shell=True)
                else:
                    subprocess.run(["shutdown", "-c"])
                return "Shutdown/reboot cancelled"
            return f"Unknown power action: {action_type}"
        except Exception as e:
            return f"Error: {e}"

    # ── SERVICE MANAGEMENT ────────────────────────────────────────

    elif action == "manage_service":
        service = params.get("name", "")
        operation = params.get("operation", "status")  # start | stop | restart | status | enable | disable
        try:
            if SYSTEM == "Linux":
                r = subprocess.run(["systemctl", operation, service], capture_output=True, text=True, timeout=30)
                return r.stdout.strip() or r.stderr.strip() or f"Service {service}: {operation} done"
            elif SYSTEM == "Windows":
                if operation == "start":
                    r = subprocess.run(["net", "start", service], capture_output=True, text=True, shell=True)
                elif operation == "stop":
                    r = subprocess.run(["net", "stop", service], capture_output=True, text=True, shell=True)
                elif operation == "status":
                    r = subprocess.run(["sc", "query", service], capture_output=True, text=True, shell=True)
                else:
                    return f"Use 'start', 'stop', or 'status' on Windows"
                return r.stdout.strip() or r.stderr.strip()
        except Exception as e:
            return f"Error managing service: {e}"

    elif action == "list_services":
        try:
            if SYSTEM == "Linux":
                r = subprocess.run(["systemctl", "list-units", "--type=service", "--state=running", "--no-pager"],
                                   capture_output=True, text=True)
                return r.stdout[:3000]
            elif SYSTEM == "Windows":
                r = subprocess.run(["powershell", "-Command",
                    "Get-Service | Where-Object {$_.Status -eq 'Running'} | Select-Object Name,DisplayName | Format-Table -AutoSize"],
                    capture_output=True, text=True)
                return r.stdout[:3000]
        except Exception as e:
            return f"Error: {e}"

    # ── SCHEDULED TASKS ───────────────────────────────────────────

    elif action == "schedule_command":
        """Schedule a command to run at a specific time."""
        command = params.get("command", "")
        time_str = params.get("time", "")  # HH:MM or 'now +5 minutes'
        repeat = params.get("repeat", "once")  # once | daily | weekly
        try:
            if SYSTEM == "Linux":
                if shutil.which("at"):
                    proc = subprocess.run(f'echo "{command}" | at {time_str}',
                                         shell=True, capture_output=True, text=True)
                    return proc.stdout.strip() or proc.stderr.strip()
                else:
                    return "Install 'at': sudo apt install at"
            elif SYSTEM == "Windows":
                r = subprocess.run(["schtasks", "/create", "/sc", repeat.upper(),
                                    "/tn", f"NEXA_{datetime.datetime.now().strftime('%H%M%S')}",
                                    "/tr", command, "/st", time_str],
                                   capture_output=True, text=True, shell=True)
                return r.stdout.strip() or r.stderr.strip()
        except Exception as e:
            return f"Error scheduling: {e}"

    # ── WALLPAPER ─────────────────────────────────────────────────

    elif action == "set_wallpaper":
        path = _expand(params.get("path", ""))
        try:
            if SYSTEM == "Linux":
                # Try GNOME, then generic
                if shutil.which("gsettings"):
                    subprocess.run(["gsettings", "set", "org.gnome.desktop.background",
                                    "picture-uri", f"file://{path}"])
                    subprocess.run(["gsettings", "set", "org.gnome.desktop.background",
                                    "picture-uri-dark", f"file://{path}"])
                elif shutil.which("feh"):
                    subprocess.run(["feh", "--bg-fill", path])
                elif shutil.which("nitrogen"):
                    subprocess.run(["nitrogen", "--set-zoom-fill", path])
                else:
                    return "No wallpaper tool found. Install feh or use GNOME."
            elif SYSTEM == "Windows":
                import ctypes
                ctypes.windll.user32.SystemParametersInfoW(20, 0, path, 3)
            elif SYSTEM == "Darwin":
                subprocess.run(["osascript", "-e",
                    f'tell application "Finder" to set desktop picture to POSIX file "{path}"'])
            return f"Wallpaper set: {path}"
        except Exception as e:
            return f"Error setting wallpaper: {e}"

    # ── SYSTEM UPTIME ─────────────────────────────────────────────

    elif action == "get_uptime":
        try:
            if psutil:
                boot = datetime.datetime.fromtimestamp(psutil.boot_time())
                delta = datetime.datetime.now() - boot
                hours, rem = divmod(int(delta.total_seconds()), 3600)
                mins, secs = divmod(rem, 60)
                return f"Uptime: {hours}h {mins}m {secs}s (booted: {boot.isoformat()})"
            if SYSTEM != "Windows":
                r = subprocess.run(["uptime"], capture_output=True, text=True)
                return r.stdout.strip()
            else:
                r = subprocess.run(["powershell", "-Command",
                    "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime"],
                    capture_output=True, text=True)
                return f"Last boot: {r.stdout.strip()}"
        except Exception as e:
            return f"Error: {e}"

    # ── USER INFO ─────────────────────────────────────────────────

    elif action == "get_user_info":
        try:
            info = {
                "username": os.getlogin() if hasattr(os, "getlogin") else os.environ.get("USER", "unknown"),
                "home": os.path.expanduser("~"),
                "cwd": os.getcwd(),
            }
            if psutil:
                users = psutil.users()
                info["logged_in_users"] = [{"name": u.name, "terminal": u.terminal, "host": u.host}
                                           for u in users]
            return json.dumps(info, indent=2)
        except Exception as e:
            return f"Error: {e}"

    # ── OPEN WITH SPECIFIC APP ────────────────────────────────────

    elif action == "open_with":
        """Open a file with a specific application."""
        file_path = _expand(params.get("path", ""))
        app_name = params.get("app", "")
        try:
            found = app_index.find_best(app_name) if app_name else None
            exe = found.exec_cmd if found else app_name

            if SYSTEM == "Darwin":
                subprocess.Popen(["open", "-a", exe, file_path])
            elif SYSTEM == "Windows":
                _popen_detached([exe, file_path])
            else:
                resolved = shutil.which(exe) or exe
                _popen_detached([resolved, file_path])
            return f"Opening {file_path} with {app_name}"
        except Exception as e:
            return f"Error: {e}"

    # ------------------------------------------------------------------
    # SMART / WEB ACTIONS
    # ------------------------------------------------------------------

    elif action == "web_search":
        service = params.get("service", "google")
        query = params.get("query", "")
        if not query:
            return "Missing 'query' parameter"
        return web_search(service, query)

    elif action == "open_website":
        site = params.get("site", params.get("name", params.get("url", "")))
        if not site:
            return "Missing 'site' parameter"
        return open_website(site)

    elif action == "multi_search":
        queries = params.get("queries", [])
        if not queries:
            return "Missing 'queries' parameter (list of {service, query})"
        return multi_search(queries)

    elif action == "smart_open":
        target = params.get("target", params.get("url", params.get("name", "")))
        if not target:
            return "Missing 'target' parameter"
        return smart_open(target)

    elif action == "download":
        url = params.get("url", "")
        save_path = params.get("path", params.get("save_path", ""))
        if not url:
            return "Missing 'url' parameter"
        return download_url(url, save_path)

    elif action == "fetch_text":
        url = params.get("url", "")
        if not url:
            return "Missing 'url' parameter"
        return web_scrape_text(url)

    elif action == "fetch_url":
        """Alias for fetch_text — fetch and extract text content from a URL."""
        url = params.get("url", "")
        if not url:
            return "Error: 'url' parameter required"
        if not url.startswith("http"):
            url = "https://" + url
        try:
            import requests as _req
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            }
            resp = _req.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            import re as _re
            text = resp.text
            text = _re.sub(r'<(script|style)[^>]*>.*?</\1>', '', text, flags=_re.DOTALL)
            text = _re.sub(r'<[^>]+>', ' ', text)
            text = _re.sub(r'\s+', ' ', text).strip()
            if len(text) > 8000:
                text = text[:8000] + "\n... (truncated)"
            return f"Content from {url}:\n\n{text}"
        except Exception as e:
            return f"Error fetching {url}: {e}"

    elif action == "chain":
        steps = params.get("steps", [])
        if not steps:
            return "Missing 'steps' parameter (list of command dicts)"
        return chain_actions(steps)

    elif action == "list_web_services":
        services = list_web_services()
        return f"Available services ({len(services)}): " + ", ".join(services)

    elif action == "list_websites":
        sites = list_direct_sites()
        return f"Known websites ({len(sites)}): " + ", ".join(sites)

    # ------------------------------------------------------------------
    # INSTALL PACKAGE
    # ------------------------------------------------------------------

    elif action == "install_package":
        """Install a package using the system package manager or pip."""
        package = params.get("name", "")
        manager = params.get("manager", "auto")
        if not package:
            return "Error: 'name' parameter required"

        if manager == "pip" or manager == "pip3":
            try:
                r = subprocess.run(
                    [sys.executable, "-m", "pip", "install", package],
                    capture_output=True, text=True, timeout=300
                )
                if r.returncode == 0:
                    return f"'{package}' installed via pip"
                return f"pip install failed: {r.stderr.strip()}"
            except Exception as e:
                return f"Error: {e}"

        if manager == "auto":
            if SYSTEM == "Linux":
                managers = ["apt"]
                if shutil.which("snap"):
                    managers.append("snap")
                if shutil.which("flatpak"):
                    managers.append("flatpak")
            elif SYSTEM == "Windows":
                managers = []
                if shutil.which("winget"):
                    managers.append("winget")
                if shutil.which("choco"):
                    managers.append("choco")
                if not managers:
                    return "No package manager found (winget/choco). Install one first."
            elif SYSTEM == "Darwin":
                managers = ["brew"] if shutil.which("brew") else []
            else:
                return f"Unsupported OS: {SYSTEM}"
        else:
            managers = [manager]

        for mgr in managers:
            try:
                if mgr == "apt":
                    cmd = f"sudo apt-get update -qq && sudo apt-get install -y {package}"
                elif mgr == "snap":
                    cmd = f"sudo snap install {package}"
                elif mgr == "flatpak":
                    cmd = f"flatpak install -y flathub {package}"
                elif mgr == "winget":
                    cmd = (
                        f"winget install --accept-package-agreements "
                        f"--accept-source-agreements {package}"
                    )
                elif mgr == "choco":
                    cmd = f"choco install -y {package}"
                elif mgr == "brew":
                    cmd = f"brew install {package}"
                else:
                    continue
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
                if r.returncode == 0:
                    return f"'{package}' installed via {mgr}"
            except subprocess.TimeoutExpired:
                continue
            except Exception:
                continue
        return f"Failed to install '{package}' with available package managers"

    # ------------------------------------------------------------------
    # CREATE SCRIPT
    # ------------------------------------------------------------------

    elif action == "create_script":
        """Create a script file with the given content."""
        path = _expand(params.get("path", ""))
        content = params.get("content", "")
        make_executable = params.get("executable", True)
        if not path or not content:
            return "Error: 'path' and 'content' parameters required"
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            if make_executable and SYSTEM != "Windows":
                import stat
                st = os.stat(path)
                os.chmod(path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
            return f"Script created: {path}"
        except Exception as e:
            return f"Error creating script: {e}"

    # ------------------------------------------------------------------
    # KEYBOARD / MOUSE AUTOMATION
    # ------------------------------------------------------------------

    elif action == "type_text":
        """Type text using keyboard automation."""
        text = params.get("text", "")
        interval = float(params.get("interval", 0.02))
        if not text:
            return "Error: 'text' parameter required"
        try:
            import pyautogui
            pyautogui.FAILSAFE = True
            pyautogui.write(text, interval=interval)
            preview = f"{text[:50]}..." if len(text) > 50 else text
            return f"Typed: '{preview}'"
        except ImportError:
            return "Error: pyautogui not installed. Run: pip install pyautogui"
        except Exception as e:
            return f"Error typing: {e}"

    elif action == "press_key":
        """Press a keyboard key or key combination."""
        key = params.get("key", "")
        if not key:
            return "Error: 'key' parameter required"
        try:
            import pyautogui
            pyautogui.FAILSAFE = True
            pyautogui.press(key)
            return f"Key pressed: {key}"
        except ImportError:
            return "Error: pyautogui not installed. Run: pip install pyautogui"
        except Exception as e:
            return f"Error pressing key: {e}"

    elif action == "hotkey":
        """Press a keyboard shortcut (e.g., ctrl+c, alt+tab)."""
        keys = params.get("keys", [])
        if not keys:
            return "Error: 'keys' parameter required (list of keys)"
        try:
            import pyautogui
            pyautogui.FAILSAFE = True
            pyautogui.hotkey(*keys)
            return f"Hotkey pressed: {'+'.join(keys)}"
        except ImportError:
            return "Error: pyautogui not installed. Run: pip install pyautogui"
        except Exception as e:
            return f"Error: {e}"

    elif action == "mouse_click":
        """Click at screen coordinates."""
        x = int(params.get("x", 0))
        y = int(params.get("y", 0))
        button = params.get("button", "left")
        clicks = int(params.get("clicks", 1))
        try:
            import pyautogui
            pyautogui.FAILSAFE = True
            pyautogui.click(x, y, clicks=clicks, button=button)
            return f"Clicked ({button}) at ({x}, {y}) x{clicks}"
        except ImportError:
            return "Error: pyautogui not installed. Run: pip install pyautogui"
        except Exception as e:
            return f"Error clicking: {e}"

    elif action == "mouse_move":
        """Move mouse to screen coordinates."""
        x = int(params.get("x", 0))
        y = int(params.get("y", 0))
        try:
            import pyautogui
            pyautogui.FAILSAFE = True
            pyautogui.moveTo(x, y)
            return f"Mouse moved to ({x}, {y})"
        except ImportError:
            return "Error: pyautogui not installed. Run: pip install pyautogui"
        except Exception as e:
            return f"Error moving mouse: {e}"

    elif action == "mouse_scroll":
        """Scroll the mouse wheel."""
        amount = int(params.get("amount", 3))
        try:
            import pyautogui
            pyautogui.FAILSAFE = True
            pyautogui.scroll(amount)
            direction = "up" if amount > 0 else "down"
            return f"Scrolled {direction} ({abs(amount)} clicks)"
        except ImportError:
            return "Error: pyautogui not installed. Run: pip install pyautogui"
        except Exception as e:
            return f"Error scrolling: {e}"

    elif action == "get_mouse_position":
        """Get current mouse cursor position."""
        try:
            import pyautogui
            pos = pyautogui.position()
            return f"Mouse position: ({pos.x}, {pos.y})"
        except ImportError:
            return "Error: pyautogui not installed. Run: pip install pyautogui"
        except Exception as e:
            return f"Error: {e}"

    elif action == "get_screen_size":
        """Get screen resolution."""
        try:
            import pyautogui
            size = pyautogui.size()
            return f"Screen size: {size.width}x{size.height}"
        except ImportError:
            return "Error: pyautogui not installed. Run: pip install pyautogui"
        except Exception as e:
            return f"Error: {e}"

    return f"Unknown system_control action: {action}"


# ======================================================================
# HELPER FUNCTIONS
# ======================================================================

def _human_size(nbytes):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} PB"


# ======================================================================
# OTHER MODULE HANDLERS
# ======================================================================

def handle_automation(action, params):
    params = params or {}
    if action == "start_routine":
        name = params.get("name", "")
        duration = params.get("duration_minutes", 0)
        print(f"[AUTOMATION] Starting routine '{name}' for {duration} minutes")
        return f"Routine '{name}' started ({duration} min)"

    elif action == "run_script":
        script = _expand(params.get("path", ""))
        interpreter = params.get("interpreter", "")
        timeout = int(params.get("timeout", 120))
        try:
            if interpreter:
                result = subprocess.run([interpreter, script], capture_output=True, text=True, timeout=timeout)
            elif script.endswith(".py"):
                result = subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=timeout)
            elif script.endswith((".sh", ".bash")):
                result = subprocess.run(["bash", script], capture_output=True, text=True, timeout=timeout)
            elif script.endswith((".ps1",)):
                result = subprocess.run(["powershell", "-File", script], capture_output=True, text=True, timeout=timeout)
            elif script.endswith((".bat", ".cmd")):
                result = subprocess.run(["cmd", "/c", script], capture_output=True, text=True, timeout=timeout)
            else:
                result = subprocess.run(["bash", script], capture_output=True, text=True, timeout=timeout)
            output = result.stdout.strip() or result.stderr.strip()
            return output or f"Script executed (exit {result.returncode})"
        except subprocess.TimeoutExpired:
            return f"Script timed out after {timeout}s"
        except Exception as e:
            return f"Error running script: {e}"

    elif action == "create_cron_job":
        schedule = params.get("schedule", "")  # cron format: "0 9 * * *"
        command = params.get("command", "")
        try:
            if SYSTEM == "Windows":
                return "Use schedule_command for Windows task scheduling."
            r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            existing = r.stdout.strip()
            new_cron = f"{existing}\n{schedule} {command}\n"
            subprocess.run(["crontab", "-"], input=new_cron, text=True)
            return f"Cron job created: {schedule} {command}"
        except Exception as e:
            return f"Error creating cron job: {e}"

    return f"Unknown automation action: {action}"


def handle_voice_interface(action, params):
    params = params or {}
    if action == "activate":
        wake = params.get("wake_word", "NEXA")
        return f"Voice interface active, wake word: {wake}"

    elif action == "speak":
        text = params.get("text", "")
        rate = params.get("rate", "")  # words per minute
        if SYSTEM == "Darwin":
            cmd = ["say"]
            if rate:
                cmd.extend(["-r", str(rate)])
            cmd.append(text)
            subprocess.Popen(cmd)
        elif SYSTEM == "Linux":
            if shutil.which("espeak-ng"):
                subprocess.Popen(["espeak-ng", text])
            elif shutil.which("espeak"):
                subprocess.Popen(["espeak", text])
            elif shutil.which("spd-say"):
                subprocess.Popen(["spd-say", text])
            else:
                return "No TTS engine found. Install espeak-ng: sudo apt install espeak-ng"
        elif SYSTEM == "Windows":
            subprocess.Popen(["PowerShell", "-Command",
                f"Add-Type -AssemblyName System.Speech; "
                f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"{'$s.Rate = ' + str(rate) + '; ' if rate else ''}"
                f"$s.Speak('{text}')"])
        return f"Speaking: {text}"

    return f"Unknown voice_interface action: {action}"


def handle_gesture_interface(action, params):
    params = params or {}
    gesture = params.get("gesture", params.get("direction", ""))
    print(f"[GESTURE] Action: {action}, gesture/direction: {gesture}")
    return f"Gesture '{action}' processed: {gesture}"


def handle_memory(action, params):
    params = params or {}
    memory_file = os.path.expanduser("~/.nexa_memory.json")
    data = {}

    if os.path.exists(memory_file):
        try:
            with open(memory_file) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {}

    if action == "store_preference":
        key = params.get("key", "")
        value = params.get("value", "")
        data[key] = {"value": value, "updated": datetime.datetime.now().isoformat()}
        with open(memory_file, "w") as f:
            json.dump(data, f, indent=2)
        return f"Saved preference: {key} = {value}"

    elif action == "get_preference":
        key = params.get("key", "")
        entry = data.get(key)
        if isinstance(entry, dict):
            return f"{key} = {entry.get('value', 'not set')}"
        return f"{key} = {entry}" if entry else f"{key} = not set"

    elif action == "list_preferences":
        return json.dumps(data, indent=2)

    elif action == "delete_preference":
        key = params.get("key", "")
        if key in data:
            del data[key]
            with open(memory_file, "w") as f:
                json.dump(data, f, indent=2)
            return f"Deleted preference: {key}"
        return f"Preference not found: {key}"

    elif action == "clear_memory":
        with open(memory_file, "w") as f:
            json.dump({}, f)
        return "All preferences cleared"

    return f"Unknown memory action: {action}"


def handle_knowledge(action, params):
    """Handle knowledge/reasoning requests."""
    params = params or {}
    if action == "explain":
        return params.get("text", "Knowledge module ready.")
    elif action == "summarize":
        return f"Summary: {params.get('text', '')[:200]}..."
    return f"Knowledge action '{action}' dispatched"


def handle_sensors(action, params):
    print(f"[SENSORS] Action: {action}, params: {params}")
    if action == "get_cpu_temperature":
        try:
            if psutil and hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                if temps:
                    return json.dumps({k: [{"label": s.label, "current": s.current, "high": s.high}
                                           for s in v] for k, v in temps.items()}, indent=2)
            return "Temperature sensors not available"
        except Exception as e:
            return f"Error: {e}"
    return f"Sensor action '{action}' dispatched"


def handle_extensions(action, params):
    print(f"[EXTENSIONS] Action: {action}, params: {params}")
    return f"Extension action '{action}' dispatched -- implement in extensions/"


# ======================================================================
# ROUTER
# ======================================================================

HANDLERS = {
    "system_control":    handle_system_control,
    "automation":        handle_automation,
    "voice_interface":   handle_voice_interface,
    "gesture_interface": handle_gesture_interface,
    "memory":            handle_memory,
    "knowledge":         handle_knowledge,
    "sensors":           handle_sensors,
    "extensions":        handle_extensions,
}


def dispatch(command: dict) -> str:
    try:
        module = command.get("module", "")
        action = command.get("action", "")
        params = command.get("parameters") or {}

        handler = HANDLERS.get(module)
        if not handler:
            return f"[NEXA] Unknown module: '{module}'"

        print(f"\n[NEXA] -> {module} / {action} / {params}")
        try:
            result = handler(action, params)
        except Exception as e:
            result = f"Handler error in {module}/{action}: {e}"
        print(f"[NEXA] done: {result[:200]}")
        return result
    except Exception as e:
        return f"[NEXA] Dispatch error: {e}"


# ======================================================================
# STDIN LOOP (for piping JSON commands)
# ======================================================================

if __name__ == "__main__":
    print("NEXA Dispatcher v2.0 ready. Paste JSON commands (Ctrl+C to exit).\n")
    # Pre-index apps at startup
    count = app_index.refresh(force=True)
    print(f"[NEXA] Indexed {count} applications.\n")
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                cmd = json.loads(line)
                dispatch(cmd)
            except json.JSONDecodeError as e:
                print(f"[ERROR] Invalid JSON: {e}")
    except KeyboardInterrupt:
        print("\nNEXA Dispatcher stopped.")
