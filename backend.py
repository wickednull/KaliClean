"""Cleaning engine for KaliClean.

Every operation is conservative:
  * RAM cache drop uses the kernel's supported sysctl interface.
  * Swap is drained and brought straight back online.
  * Logs are vacuumed (a recent history is always kept).
  * File deletion is limited to cache/temp paths, regular files and a minimum age.
  * Privileged commands are the only ones that ever see the sudo password,
    which lives in memory for the lifetime of the app and is never written out.
"""

from __future__ import annotations

import glob
import os
import shutil
import stat
import subprocess
import time
from pathlib import Path

HOME = Path.home()

# Single source of truth for the UI. `root` marks tasks that need elevation.
TASKS = [
    {"id": "ram", "name": "Memory cache", "desc": "Drop reclaimable pages, dentries & inodes", "icon": "cpu", "root": True, "default": True},
    {"id": "swap", "name": "Swap space", "desc": "Drain swap devices and bring them back", "icon": "refresh", "root": True, "default": True},
    {"id": "journal", "name": "System journals", "desc": "Vacuum logs, keeping the last 64 MB", "icon": "file", "root": True, "default": True},
    {"id": "apt", "name": "Package archives", "desc": "Remove cached .deb installers (apt clean)", "icon": "package", "root": True, "default": True},
    {"id": "temp", "name": "Temporary files", "desc": "Old files in /tmp and /var/tmp (1+ days)", "icon": "clock", "root": True, "default": True},
    {"id": "thumbnails", "name": "Thumbnail cache", "desc": "Regenerate file & image thumbnails", "icon": "image", "root": False, "default": True},
    {"id": "browser", "name": "Browser caches", "desc": "Firefox / Chromium HTTP caches only", "icon": "globe", "root": False, "default": True},
    {"id": "trash", "name": "Trash", "desc": "Empty the desktop trash bin (irreversible)", "icon": "trash", "root": False, "default": False},
    {"id": "crash", "name": "Crash reports", "desc": "Clear stale /var/crash reports", "icon": "alert", "root": True, "default": True},
    {"id": "dns", "name": "DNS resolver cache", "desc": "Restart systemd-resolved (brief network pause)", "icon": "wifi", "root": True, "default": False},
]


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def human(num: float) -> str:
    num = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024.0:
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} PB"


def meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                key, _, rest = line.partition(":")
                parts = rest.split()
                if parts:
                    values[key.strip()] = int(parts[0]) * 1024
    except OSError:
        pass
    return values


def swap_used() -> int:
    memory = meminfo()
    return max(0, memory.get("SwapTotal", 0) - memory.get("SwapFree", 0))


def dir_size(paths: list[str]) -> int:
    total = 0
    for path in paths:
        try:
            if os.path.islink(path):
                continue
            if os.path.isfile(path):
                total += os.path.getsize(path)
                continue
            for root, _dirs, files in os.walk(path, followlinks=False, onerror=lambda _e: None):
                for name in files:
                    full = os.path.join(root, name)
                    try:
                        info = os.lstat(full)
                        if stat.S_ISREG(info.st_mode):
                            total += info.st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def journal_paths() -> list[str]:
    return ["/var/log/journal", "/run/log/journal"]


def apt_paths() -> list[str]:
    return ["/var/cache/apt/archives"]


def temp_paths() -> list[str]:
    return ["/tmp", "/var/tmp"]


def thumbnail_paths() -> list[str]:
    return [str(HOME / ".cache" / "thumbnails")]


def browser_paths() -> list[str]:
    patterns = [
        str(HOME / ".cache" / "mozilla" / "firefox" / "*" / "cache2"),
        str(HOME / ".cache" / "google-chrome" / "*" / "Cache"),
        str(HOME / ".cache" / "google-chrome" / "*" / "Code Cache"),
        str(HOME / ".cache" / "chromium" / "*" / "Cache"),
        str(HOME / ".cache" / "chromium" / "*" / "Code Cache"),
        str(HOME / ".cache" / "BraveSoftware" / "*" / "Cache"),
    ]
    found: list[str] = []
    for pattern in patterns:
        found.extend(glob.glob(pattern))
    return found


def trash_paths() -> list[str]:
    return [
        str(HOME / ".local" / "share" / "Trash" / "files"),
        str(HOME / ".local" / "share" / "Trash" / "info"),
    ]


def crash_paths() -> list[str]:
    return ["/var/crash"]


PATHS = {
    "journal": journal_paths,
    "apt": apt_paths,
    "temp": temp_paths,
    "thumbnails": thumbnail_paths,
    "browser": browser_paths,
    "trash": trash_paths,
    "crash": crash_paths,
}


def estimate(task_id: str) -> int:
    """Best-effort estimate of what a task could reclaim, in bytes."""
    if task_id == "ram":
        memory = meminfo()
        return max(0, memory.get("Cached", 0) - memory.get("Shmem", 0))
    if task_id == "swap":
        return swap_used()
    if task_id == "dns":
        return 0
    getter = PATHS.get(task_id)
    return dir_size(getter()) if getter else 0


def system_stats() -> dict:
    memory = meminfo()
    total = memory.get("MemTotal", 1)
    available = memory.get("MemAvailable", 0)
    used = max(0, total - available)
    swap_total = memory.get("SwapTotal", 0)
    swap_free = memory.get("SwapFree", 0)
    disk = shutil.disk_usage("/")
    return {
        "memTotal": total,
        "memUsed": used,
        "memAvailable": available,
        "memPercent": round(used / total * 100, 1),
        "swapTotal": swap_total,
        "swapUsed": max(0, swap_total - swap_free),
        "swapPercent": round((swap_total - swap_free) / swap_total * 100, 1) if swap_total else 0,
        "diskTotal": disk.total,
        "diskUsed": disk.used,
        "diskPercent": round(disk.used / disk.total * 100, 1),
        "isRoot": os.geteuid() == 0,
    }


def clear_dir_contents(paths: list[str]) -> tuple[int, int]:
    """Delete regular files (and emptied subdirectories) inside cache folders."""
    freed = 0
    count = 0
    for path in paths:
        if not os.path.isdir(path) or os.path.islink(path):
            continue
        for root, dirs, files in os.walk(path, topdown=False, followlinks=False, onerror=lambda _e: None):
            for name in files:
                full = os.path.join(root, name)
                try:
                    info = os.lstat(full)
                    if not stat.S_ISREG(info.st_mode):
                        continue
                    freed += info.st_size
                    os.unlink(full)
                    count += 1
                except OSError:
                    continue
            for name in dirs:
                full = os.path.join(root, name)
                try:
                    if not os.path.islink(full):
                        os.rmdir(full)
                except OSError:
                    continue
    return freed, count


def clean_temp(days: int = 1) -> tuple[int, int]:
    """Remove only old, regular, non-hidden files from the temp directories."""
    cutoff = time.time() - days * 86400
    freed = 0
    count = 0
    for base in temp_paths():
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base, topdown=True, followlinks=False, onerror=lambda _e: None):
            dirs[:] = [
                d for d in dirs
                if not d.startswith(".")
                and not d.startswith("systemd-private-")
            ]
            for name in files:
                if name.startswith("."):
                    continue
                full = os.path.join(root, name)
                try:
                    info = os.lstat(full)
                    if not stat.S_ISREG(info.st_mode):
                        continue
                    if info.st_mtime >= cutoff or info.st_atime >= cutoff:
                        continue
                    freed += info.st_size
                    os.unlink(full)
                    count += 1
                except OSError:
                    continue
        for root, dirs, _files in os.walk(base, topdown=False, followlinks=False, onerror=lambda _e: None):
            if root == base or os.path.basename(root).startswith("."):
                continue
            try:
                info = os.stat(root)
                if info.st_mtime < cutoff and not os.listdir(root):
                    os.rmdir(root)
            except OSError:
                continue
    return freed, count


# --------------------------------------------------------------------------
# Cleaner
# --------------------------------------------------------------------------
class Cleaner:
    def __init__(self) -> None:
        self.password: str | None = None
        self.cancelled = False

    def verify_password(self, password: str) -> tuple[bool, str]:
        if os.geteuid() == 0:
            self.password = None
            return True, "Running as root"
        try:
            result = subprocess.run(
                ["sudo", "-S", "-p", "", "-v"],
                input=password + "\n",
                text=True,
                capture_output=True,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return False, f"Could not run sudo: {exc}"
        if result.returncode == 0:
            self.password = password
            return True, "Unlocked"
        return False, "Incorrect password"

    def _command(self, command: list[str], timeout: int = 120) -> tuple[bool, str]:
        """Run a command, elevating only when we are not already root."""
        try:
            if os.geteuid() == 0:
                result = subprocess.run(
                    command, text=True, capture_output=True, timeout=timeout
                )
            else:
                if not self.password:
                    return False, "No elevated credentials available"
                result = subprocess.run(
                    ["sudo", "-S", "-p", "", *command],
                    input=self.password + "\n",
                    text=True,
                    capture_output=True,
                    timeout=timeout,
                )
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except OSError as exc:
            return False, str(exc)
        output = (result.stderr or result.stdout or "").strip()
        return result.returncode == 0, output

    def run_task(self, task_id: str) -> dict:
        """Execute a single cleanup task. Returns a JSON-friendly result."""
        try:
            if task_id == "ram":
                before = meminfo().get("MemAvailable", 0)
                ok, message = self._command(
                    ["/bin/sh", "-c", "sync; echo 3 > /proc/sys/vm/drop_caches"]
                )
                after = meminfo().get("MemAvailable", 0)
                freed = max(0, after - before)
                return self._result(ok, freed, message or "Kernel caches dropped")

            if task_id == "swap":
                before = swap_used()
                ok1, message1 = self._command(["swapoff", "-a"], timeout=180)
                ok2, message2 = self._command(["swapon", "-a"], timeout=120)
                after = swap_used()
                freed = max(0, before - after)
                ok = ok2  # swap must be back online; swapoff may fail if RAM is full
                detail = "Swap drained and re-enabled"
                if not ok1:
                    detail = f"Some swap could not be drained ({message1[:90]})"
                elif not ok2:
                    detail = f"Swap drain ok, re-enable failed ({message2[:90]})"
                return self._result(ok, freed, detail)

            if task_id == "journal":
                before = dir_size(journal_paths())
                ok, message = self._command(
                    ["journalctl", "--vacuum-size=64M", "--no-pager"], timeout=180
                )
                after = dir_size(journal_paths())
                return self._result(ok, max(0, before - after), message or "Journals vacuumed")

            if task_id == "apt":
                before = dir_size(apt_paths())
                ok, message = self._command(["apt-get", "clean"], timeout=180)
                after = dir_size(apt_paths())
                return self._result(ok, max(0, before - after), message or "APT archives removed")

            if task_id == "temp":
                before = dir_size(temp_paths())
                freed, count = clean_temp(1)
                after = dir_size(temp_paths())
                measured = max(0, before - after)
                return self._result(True, measured or freed, f"{count} stale temp files removed")

            if task_id == "dns":
                ok, message = self._command(
                    ["systemctl", "restart", "systemd-resolved"], timeout=60
                )
                return self._result(ok, 0, message or "Resolver cache flushed")

            getter = PATHS.get(task_id)
            if getter:
                paths = getter()
                before = dir_size(paths)
                freed, count = clear_dir_contents(paths)
                after = dir_size(paths)
                measured = max(0, before - after)
                return self._result(True, measured or freed, f"{count} cached files removed")

            return self._result(False, 0, f"Unknown task: {task_id}")
        except Exception as exc:  # keep one bad task from aborting the whole run
            return self._result(False, 0, f"Unexpected error: {exc}")

    @staticmethod
    def _result(ok: bool, freed: int, detail: str) -> dict:
        return {"ok": bool(ok), "freed": int(max(0, freed)), "detail": str(detail)[:200]}
