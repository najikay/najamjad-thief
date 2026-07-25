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


def _ram_gb() -> float | str:
    """Total physical memory in GB."""
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError, AttributeError):
        return UNKNOWN
    return round(pages * page_size / BYTES_PER_GB, 1)


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
