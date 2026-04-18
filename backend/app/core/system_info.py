import functools
import logging
import multiprocessing
import os
import platform
import re
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


# Minimum memory budget worker.
MIN_MEMORY_PER_WORKER = 450 * 1024 * 1024

# Environment variable users can set to override the auto-computed worker count.
WORKER_COUNT_ENV_VAR = "ACHEW_WORKER_COUNT"

# Linux cgroup v1 uses this value (or nearby) to indicate "no memory limit".
_CGROUP_V1_NO_LIMIT_THRESHOLD = 1 << 62


def _read_int_file(path: str) -> Optional[int]:
    try:
        with open(path, "r") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def _cgroup_available_memory() -> Optional[int]:
    """
    Return memory available within this process's cgroup, or None if no
    limit is set or the cgroup files are unreadable.

    Covers docker-imposed memory limits.
    """
    # cgroup v2
    v2_max = "/sys/fs/cgroup/memory.max"
    v2_current = "/sys/fs/cgroup/memory.current"
    if os.path.exists(v2_max):
        try:
            with open(v2_max, "r") as f:
                raw = f.read().strip()
            if raw != "max":
                limit = int(raw)
                usage = _read_int_file(v2_current) or 0
                return max(0, limit - usage)
        except (OSError, ValueError):
            pass

    # cgroup v1
    v1_limit = "/sys/fs/cgroup/memory/memory.limit_in_bytes"
    v1_usage = "/sys/fs/cgroup/memory/memory.usage_in_bytes"
    limit = _read_int_file(v1_limit)
    if limit is not None and limit < _CGROUP_V1_NO_LIMIT_THRESHOLD:
        usage = _read_int_file(v1_usage) or 0
        return max(0, limit - usage)

    return None


def _linux_available_memory() -> Optional[int]:
    host_available: Optional[int] = None
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    parts = line.split()
                    host_available = int(parts[1]) * 1024  # kB → bytes
                    break
    except (OSError, ValueError, IndexError):
        host_available = None

    cgroup_available = _cgroup_available_memory()

    if host_available is not None and cgroup_available is not None:
        return min(host_available, cgroup_available)
    return cgroup_available if cgroup_available is not None else host_available


def _macos_available_memory() -> Optional[int]:
    try:
        page_size_out = subprocess.run(
            ["sysctl", "-n", "hw.pagesize"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
        page_size = int(page_size_out)

        vm_out = subprocess.run(
            ["vm_stat"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout

        free_pages = 0
        for key in ("Pages free", "Pages inactive", "Pages speculative"):
            match = re.search(rf"{key}:\s+(\d+)", vm_out)
            if match:
                free_pages += int(match.group(1))
        if free_pages == 0:
            return None
        return free_pages * page_size
    except (subprocess.SubprocessError, ValueError, OSError):
        return None


def _windows_available_memory() -> Optional[int]:
    try:
        import ctypes
        from ctypes import wintypes

        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD),
                ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(MemoryStatusEx)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return int(status.ullAvailPhys)
    except (OSError, AttributeError, ImportError):
        return None


def get_available_memory_bytes() -> Optional[int]:
    """
    Best-effort cross-platform probe for available-memory.
    Returns None when the platform is unsupported or the probe fails.
    """
    system = platform.system()
    if system == "Linux":
        return _linux_available_memory()
    if system == "Darwin":
        return _macos_available_memory()
    if system == "Windows":
        return _windows_available_memory()
    return None


def _read_worker_override() -> Optional[int]:
    raw = os.getenv(WORKER_COUNT_ENV_VAR)
    if not raw:
        return None
    try:
        value = int(raw.strip())
    except ValueError:
        logger.warning(
            f"{WORKER_COUNT_ENV_VAR}={raw!r} is not a valid integer; ignoring override"
        )
        return None
    if value < 1:
        logger.warning(
            f"{WORKER_COUNT_ENV_VAR}={value} must be at least 1; ignoring override"
        )
        return None
    return value


@functools.lru_cache(maxsize=1)
def get_worker_count() -> int:
    """
    Return the worker count to use for parallel audio processing.

    Honors the ACHEW_WORKER_COUNT env var as an override. Otherwise uses
    calculates from num CPU cores and available memory, with a floor of 1.
    """
    cpu_count = multiprocessing.cpu_count()
    cpu_cap = max(1, cpu_count * 2 // 3)

    override = _read_worker_override()
    if override is not None:
        logger.info(
            f"Worker count: {override} (from {WORKER_COUNT_ENV_VAR}; "
            f"CPU cap would have been {cpu_cap})"
        )
        return override

    available = get_available_memory_bytes()
    if available is None:
        logger.info(
            f"Worker count: {cpu_cap} (memory probe unavailable on this platform)"
        )
        return cpu_cap

    memory_cap = max(1, available // MIN_MEMORY_PER_WORKER)
    workers = min(cpu_cap, memory_cap)
    available_mb = available // (1024 * 1024)
    logger.info(
        f"Worker count: {workers} (cpu_cap={cpu_cap} from {cpu_count} cores, "
        f"memory_cap={memory_cap} from {available_mb}MB available)"
    )
    return workers
