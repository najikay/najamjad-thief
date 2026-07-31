"""Machine specification for the Step-0 computational-fairness declaration.

The lecturer normalises league scores by hardware, rewarding good results on
modest machines; omitting this declaration forfeits that bonus (book rule 24).
Field names follow the reference sample log so the declaration is comparable
across teams.

Every probe degrades to a readable placeholder rather than raising — a missing
GPU driver must never stop a match from starting.
"""

import os
import platform
import shutil
import subprocess
from typing import Any

UNKNOWN = "unknown"
BYTES_PER_GB = 1024**3


def _cpu_name() -> str:
    """Human-readable processor name, best effort across platforms."""
    if platform.system() == "Linux":
        try:
            with open("/proc/cpuinfo", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("model name"):
                        return line.split(":", 1)[1].strip()
        except OSError:
            return platform.processor() or UNKNOWN
    return platform.processor() or platform.machine() or UNKNOWN


def _ram_unix(sysconf: Any = None) -> float | str:
    """Total physical memory via POSIX `sysconf`, or UNKNOWN off POSIX.

    `sysconf` is injectable for the same reason `_ram_windows` takes a
    `kernel32`: otherwise this arithmetic only ever runs on POSIX, and the
    Windows half of the team can never exercise it. The asymmetry was the
    unfixed half of the original defect — the Windows path was made testable
    from Linux, but the POSIX path stayed untestable from Windows, where
    `os.sysconf` does not exist to monkeypatch a success from.
    """
    probe = sysconf or getattr(os, "sysconf", None)
    if probe is None:
        return UNKNOWN
    try:
        pages = probe("SC_PHYS_PAGES")
        page_size = probe("SC_PAGE_SIZE")
    except (ValueError, OSError, AttributeError):
        return UNKNOWN
    return round(pages * page_size / BYTES_PER_GB, 1)


def _ram_windows(kernel32: Any = None) -> float | str:
    """Total physical memory via `GlobalMemoryStatusEx`, or UNKNOWN elsewhere.

    `kernel32` is injectable so the Windows path is testable from any
    platform — otherwise it is code that only ever runs where the suite does
    not, which is how it stayed broken.
    """
    import ctypes

    class _MemoryStatus(ctypes.Structure):
        """The Win32 `MEMORYSTATUSEX` record, field-for-field.

        Input: `dwLength` set to the struct size before the call — Windows
            uses it to version the record and rejects a wrong value.
        Output: `ullTotalPhys`, the only field we read.
        Setup: field order and widths must match the Win32 header exactly;
            a shorter struct silently misreads memory.
        """

        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    try:
        library = kernel32 or ctypes.windll.kernel32  # type: ignore[attr-defined]
        status = _MemoryStatus()
        status.dwLength = ctypes.sizeof(_MemoryStatus)
        if not library.GlobalMemoryStatusEx(ctypes.byref(status)):
            return UNKNOWN
        return round(status.ullTotalPhys / BYTES_PER_GB, 1)
    except Exception:  # noqa: BLE001 - any probe failure degrades to UNKNOWN
        return UNKNOWN


def _ram_gb() -> float | str:
    """Total physical memory in GB, by whichever probe this platform supports.

    `os.sysconf` does not exist on Windows, so this reported UNKNOWN on every
    Windows machine — and `collect_spec` files that straight into the Step-0
    declaration, leaving rule 24's computational-fairness normalisation with a
    blank. CI runs ubuntu, so it was green there and wrong on the machines the
    matches are actually played from. Found by a teammate on Windows.
    """
    memory = _ram_unix()
    return memory if memory != UNKNOWN else _ram_windows()


def _gpu_name() -> str:
    """GPU model via nvidia-smi when present.

    Invoked as an argument list so no shell is ever spawned (no interpolation,
    therefore no command-injection path).
    """
    binary = shutil.which("nvidia-smi")
    if not binary:
        return "none detected"
    try:
        result = subprocess.run(
            [binary, "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN
    first = result.stdout.strip().splitlines()
    return first[0].strip() if first else "none detected"


def collect_spec() -> dict:
    """Collect the hardware declaration in the reference field shape."""
    return {
        "os": f"{platform.system()} {platform.release()}",
        "cpu_type": _cpu_name(),
        "cpu_cores": os.cpu_count() or UNKNOWN,
        "ram_gb": _ram_gb(),
        "gpu_type": _gpu_name(),
        "python": platform.python_version(),
    }


def git_commit(repo_root: str | None = None) -> str:
    """Current HEAD commit — mandatory in Step-0 and the result JSON (rule 53)."""
    binary = shutil.which("git")
    if not binary:
        return UNKNOWN
    try:
        result = subprocess.run(
            [binary, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            cwd=repo_root,
        )
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN
    return result.stdout.strip() or UNKNOWN
