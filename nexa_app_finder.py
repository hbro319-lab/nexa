"""
NEXA -- Cross-Platform Application Finder
Scans the system for installed applications on Windows and Linux,
builds a searchable index, and provides fuzzy-match lookup.

Supports:
  Linux  : .desktop files, PATH binaries, Flatpak, Snap
  Windows: Start Menu shortcuts (.lnk), App Paths registry,
           PATH executables, WindowsApps (UWP/MSIX)
"""

import os
import re
import glob
import shutil
import platform
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

SYSTEM = platform.system()

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class AppEntry:
    name: str                              # display name
    exec_cmd: str                          # command / path to launch
    exec_args: list[str] = field(default_factory=list)
    icon: str = ""
    comment: str = ""
    categories: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    source: str = ""                       # e.g. "desktop", "start_menu", "path", "snap"
    desktop_file: str = ""                 # path to .desktop or .lnk

    def launch_cmd(self) -> list[str]:
        """Return a list suitable for subprocess.Popen."""
        parts = [self.exec_cmd] + self.exec_args
        return parts

# ---------------------------------------------------------------------------
# Linux scanner
# ---------------------------------------------------------------------------

_DESKTOP_DIRS_LINUX = [
    "/usr/share/applications",
    "/usr/local/share/applications",
    os.path.expanduser("~/.local/share/applications"),
    "/var/lib/flatpak/exports/share/applications",
    os.path.expanduser("~/.local/share/flatpak/exports/share/applications"),
    "/var/lib/snapd/desktop/applications",
    "/snap/current/share/applications",
]


def _parse_desktop_file(path: str) -> Optional[AppEntry]:
    """Parse a freedesktop .desktop file into an AppEntry."""
    try:
        with open(path, "r", errors="replace") as fh:
            lines = fh.readlines()
    except (OSError, PermissionError):
        return None

    in_entry = False
    vals: dict[str, str] = {}
    for line in lines:
        line = line.strip()
        if line == "[Desktop Entry]":
            in_entry = True
            continue
        if line.startswith("[") and in_entry:
            break
        if not in_entry or "=" not in line:
            continue
        key, _, value = line.partition("=")
        vals[key.strip()] = value.strip()

    if vals.get("Type") != "Application":
        return None
    if vals.get("NoDisplay", "").lower() == "true":
        return None

    name = vals.get("Name", "")
    exec_raw = vals.get("Exec", "")
    if not name or not exec_raw:
        return None

    # Strip field codes (%f %F %u %U %d %D %n %N %i %c %k %v %m)
    exec_clean = re.sub(r"%[fFuUdDnNickvm]", "", exec_raw).strip()
    parts = exec_clean.split()
    exe = parts[0] if parts else exec_raw
    args = parts[1:] if len(parts) > 1 else []

    categories_raw = vals.get("Categories", "")
    categories = [c for c in categories_raw.split(";") if c]

    keywords_raw = vals.get("Keywords", "")
    keywords = [k for k in keywords_raw.split(";") if k]

    generic_name = vals.get("GenericName", "")
    if generic_name and generic_name.lower() not in [k.lower() for k in keywords]:
        keywords.append(generic_name)

    return AppEntry(
        name=name,
        exec_cmd=exe,
        exec_args=args,
        icon=vals.get("Icon", ""),
        comment=vals.get("Comment", ""),
        categories=categories,
        keywords=keywords,
        source="desktop",
        desktop_file=path,
    )


def _scan_linux_desktop_files() -> list[AppEntry]:
    apps: list[AppEntry] = []
    seen_execs: set[str] = set()
    for d in _DESKTOP_DIRS_LINUX:
        if not os.path.isdir(d):
            continue
        for fp in glob.glob(os.path.join(d, "*.desktop")):
            entry = _parse_desktop_file(fp)
            if entry and entry.exec_cmd not in seen_execs:
                seen_execs.add(entry.exec_cmd)
                apps.append(entry)
    return apps


def _scan_linux_path_binaries() -> list[AppEntry]:
    """Scan PATH for executables not already covered by .desktop files."""
    apps: list[AppEntry] = []
    seen: set[str] = set()
    path_dirs = os.environ.get("PATH", "").split(":")
    for d in path_dirs:
        if not os.path.isdir(d):
            continue
        try:
            entries = os.listdir(d)
        except PermissionError:
            continue
        for name in entries:
            fp = os.path.join(d, name)
            if name in seen:
                continue
            if os.path.isfile(fp) and os.access(fp, os.X_OK):
                seen.add(name)
                apps.append(AppEntry(
                    name=name,
                    exec_cmd=fp,
                    source="path",
                ))
    return apps

# ---------------------------------------------------------------------------
# Windows scanner
# ---------------------------------------------------------------------------

def _scan_windows_start_menu() -> list[AppEntry]:
    """Scan Start Menu folders for .lnk shortcut files."""
    apps: list[AppEntry] = []
    start_dirs = []

    # Common + user start menu
    for env in ("PROGRAMDATA", "APPDATA"):
        base = os.environ.get(env, "")
        if base:
            sm = os.path.join(base, "Microsoft", "Windows", "Start Menu", "Programs")
            if os.path.isdir(sm):
                start_dirs.append(sm)

    # Resolve .lnk targets via PowerShell (batch for speed)
    lnk_files: list[str] = []
    for sd in start_dirs:
        for root, _dirs, files in os.walk(sd):
            for f in files:
                if f.lower().endswith(".lnk"):
                    lnk_files.append(os.path.join(root, f))

    if not lnk_files:
        return apps

    # Use a single PowerShell call to resolve all links
    import subprocess
    ps_script_lines = [
        "$sh = New-Object -ComObject WScript.Shell",
    ]
    for lnk in lnk_files:
        safe = lnk.replace("'", "''")
        ps_script_lines.append(
            f"try {{ $s = $sh.CreateShortcut('{safe}'); "
            f"Write-Output ('{safe}|' + $s.TargetPath + '|' + $s.Arguments + '|' + $s.Description) }} "
            f"catch {{ Write-Output '{safe}|||' }}"
        )
    ps_script = "\n".join(ps_script_lines)

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True, text=True, timeout=30,
        )
        for line in result.stdout.strip().splitlines():
            parts = line.split("|", 3)
            if len(parts) < 4:
                continue
            lnk_path, target, arguments, description = parts
            if not target or not os.path.exists(target):
                continue
            display_name = os.path.splitext(os.path.basename(lnk_path))[0]
            args = arguments.split() if arguments else []
            apps.append(AppEntry(
                name=display_name,
                exec_cmd=target,
                exec_args=args,
                comment=description,
                source="start_menu",
                desktop_file=lnk_path,
            ))
    except Exception:
        pass

    return apps


def _scan_windows_app_paths() -> list[AppEntry]:
    """Read HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths."""
    apps: list[AppEntry] = []
    try:
        import winreg
        key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    i += 1
                    with winreg.OpenKey(key, subkey_name) as sk:
                        try:
                            val, _ = winreg.QueryValueEx(sk, "")
                            if val and os.path.exists(val):
                                display = os.path.splitext(subkey_name)[0]
                                apps.append(AppEntry(
                                    name=display,
                                    exec_cmd=val,
                                    source="app_paths",
                                ))
                        except OSError:
                            pass
                except OSError:
                    break
    except Exception:
        pass
    return apps


def _scan_windows_path_executables() -> list[AppEntry]:
    """Scan PATH for .exe/.cmd/.bat files."""
    apps: list[AppEntry] = []
    seen: set[str] = set()
    exts = {".exe", ".cmd", ".bat", ".com"}
    path_dirs = os.environ.get("PATH", "").split(";")
    for d in path_dirs:
        if not os.path.isdir(d):
            continue
        try:
            entries = os.listdir(d)
        except PermissionError:
            continue
        for name in entries:
            low = name.lower()
            stem, ext = os.path.splitext(low)
            if ext not in exts or stem in seen:
                continue
            fp = os.path.join(d, name)
            if os.path.isfile(fp):
                seen.add(stem)
                apps.append(AppEntry(
                    name=stem,
                    exec_cmd=fp,
                    source="path",
                ))
    return apps


def _scan_windows_uwp_apps() -> list[AppEntry]:
    """List UWP / MSIX apps via PowerShell Get-StartApps."""
    apps: list[AppEntry] = []
    try:
        import subprocess
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json"],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode == 0 and result.stdout.strip():
            import json
            data = json.loads(result.stdout)
            if isinstance(data, dict):
                data = [data]
            for item in data:
                name = item.get("Name", "")
                app_id = item.get("AppID", "")
                if name and app_id:
                    apps.append(AppEntry(
                        name=name,
                        exec_cmd=app_id,
                        source="uwp",
                    ))
    except Exception:
        pass
    return apps

# ---------------------------------------------------------------------------
# Fuzzy search scoring
# ---------------------------------------------------------------------------

def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower())


def _score_match(query: str, entry: AppEntry) -> float:
    """Return 0-100 relevance score. 0 means no match."""
    q = _normalize(query)
    if not q:
        return 0.0

    best = 0.0

    # Check display name
    name_n = _normalize(entry.name)
    if q == name_n:
        best = max(best, 100.0)
    elif name_n.startswith(q):
        best = max(best, 90.0)
    elif q in name_n:
        best = max(best, 75.0)
    else:
        # token match
        q_tokens = set(q.split())
        name_tokens = set(name_n.split())
        if q_tokens and q_tokens.issubset(name_tokens):
            best = max(best, 80.0)
        elif q_tokens & name_tokens:
            overlap = len(q_tokens & name_tokens) / len(q_tokens)
            best = max(best, 50.0 + overlap * 20)

    # Check exec command basename
    exec_base = _normalize(os.path.basename(entry.exec_cmd))
    exec_stem = _normalize(os.path.splitext(os.path.basename(entry.exec_cmd))[0])
    if q == exec_stem or q == exec_base:
        best = max(best, 95.0)
    elif exec_stem.startswith(q):
        best = max(best, 85.0)
    elif q in exec_stem:
        best = max(best, 65.0)

    # Check keywords
    for kw in entry.keywords:
        kw_n = _normalize(kw)
        if q == kw_n:
            best = max(best, 88.0)
        elif q in kw_n or kw_n in q:
            best = max(best, 55.0)

    # Check categories
    for cat in entry.categories:
        cat_n = _normalize(cat)
        if q in cat_n:
            best = max(best, 40.0)

    # Check comment
    if entry.comment:
        comment_n = _normalize(entry.comment)
        if q in comment_n:
            best = max(best, 30.0)

    # Subsequence match on name (typo tolerance)
    if best < 25.0:
        qi = 0
        for ch in name_n:
            if qi < len(q) and ch == q[qi]:
                qi += 1
        if qi == len(q):
            ratio = len(q) / max(len(name_n), 1)
            best = max(best, 20.0 + ratio * 30)

    return best

# ---------------------------------------------------------------------------
# Main index
# ---------------------------------------------------------------------------

class AppIndex:
    """Thread-safe, cached application index with fuzzy search."""

    def __init__(self, cache_ttl: int = 300):
        self._apps: list[AppEntry] = []
        self._lock = threading.Lock()
        self._last_scan: float = 0.0
        self._cache_ttl = cache_ttl  # seconds

    # -- scanning --

    def refresh(self, force: bool = False) -> int:
        """Rebuild the index. Returns number of apps found."""
        now = time.time()
        if not force and (now - self._last_scan) < self._cache_ttl and self._apps:
            return len(self._apps)

        apps: list[AppEntry] = []

        if SYSTEM == "Linux":
            apps.extend(_scan_linux_desktop_files())
            desktop_execs = {a.exec_cmd for a in apps}
            for pa in _scan_linux_path_binaries():
                if pa.exec_cmd not in desktop_execs:
                    apps.append(pa)

        elif SYSTEM == "Windows":
            apps.extend(_scan_windows_start_menu())
            sm_execs = {a.exec_cmd.lower() for a in apps}
            for pa in _scan_windows_app_paths():
                if pa.exec_cmd.lower() not in sm_execs:
                    apps.append(pa)
                    sm_execs.add(pa.exec_cmd.lower())
            for pa in _scan_windows_path_executables():
                if pa.exec_cmd.lower() not in sm_execs:
                    apps.append(pa)
                    sm_execs.add(pa.exec_cmd.lower())
            apps.extend(_scan_windows_uwp_apps())

        elif SYSTEM == "Darwin":
            # macOS: scan /Applications and ~/Applications
            for base in ["/Applications", os.path.expanduser("~/Applications")]:
                if not os.path.isdir(base):
                    continue
                for item in os.listdir(base):
                    if item.endswith(".app"):
                        display = item[:-4]
                        apps.append(AppEntry(
                            name=display,
                            exec_cmd=display,
                            source="applications_dir",
                            desktop_file=os.path.join(base, item),
                        ))

        with self._lock:
            self._apps = apps
            self._last_scan = time.time()

        return len(apps)

    # -- search --

    def search(self, query: str, limit: int = 10, min_score: float = 15.0) -> list[tuple[AppEntry, float]]:
        """Fuzzy search. Returns [(AppEntry, score)] sorted by score desc."""
        self.refresh()
        with self._lock:
            snapshot = list(self._apps)

        results: list[tuple[AppEntry, float]] = []
        for entry in snapshot:
            score = _score_match(query, entry)
            if score >= min_score:
                results.append((entry, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def find_best(self, query: str) -> Optional[AppEntry]:
        """Return the single best match, or None."""
        hits = self.search(query, limit=1, min_score=30.0)
        return hits[0][0] if hits else None

    def list_all(self, source_filter: str = "") -> list[AppEntry]:
        """Return all indexed apps, optionally filtered by source."""
        self.refresh()
        with self._lock:
            snapshot = list(self._apps)
        if source_filter:
            snapshot = [a for a in snapshot if a.source == source_filter]
        return snapshot

    def list_categories(self) -> list[str]:
        """Return sorted list of unique categories."""
        self.refresh()
        cats: set[str] = set()
        with self._lock:
            for a in self._apps:
                cats.update(a.categories)
        return sorted(cats)

    def by_category(self, category: str, limit: int = 50) -> list[AppEntry]:
        """Return apps in a given category."""
        self.refresh()
        cat_lower = category.lower()
        with self._lock:
            return [a for a in self._apps if any(c.lower() == cat_lower for c in a.categories)][:limit]

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._apps)


# Module-level singleton
app_index = AppIndex()
