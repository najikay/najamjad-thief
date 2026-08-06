"""Tests for hardware probing — every probe must degrade, never raise.

A missing driver or an unreadable /proc file must not stop a match from
starting, so each fallback path is exercised explicitly here (they cannot all
run natively on one machine).
"""

import platform
import subprocess
from pathlib import Path

import pytest

from najamjad_agent.shared import sysinfo


def test_collect_spec_has_the_declaration_fields() -> None:
    """All six fields rule 24 asks for, plus what our own artifacts read.

    `cpu_freq_mhz` and `vram_gb` were absent, so `spec_for_declaration`'s
    `spec.get(...)` put `None` into every fairness declaration we ever filed.
    """
    spec = sysinfo.collect_spec()

    assert set(spec) == {
        "os", "cpu_type", "cpu_cores", "cpu_freq_mhz",
        "ram_gb", "gpu_type", "vram_gb", "python",
    }
    assert None not in spec.values()


def test_the_clock_falls_back_to_the_nominal_speed(monkeypatch: pytest.MonkeyPatch) -> None:
    """No `cpuinfo_max_freq` — a container, or not Linux — still yields a number.

    The model string carries the nominal clock, which is what a fairness
    comparison wants anyway.
    """
    monkeypatch.setattr(sysinfo, "CPU_MAX_FREQ", "/nonexistent/cpufreq")
    monkeypatch.setattr(sysinfo, "_cpu_name", lambda: "11th Gen Core i7-1165G7 @ 2.80GHz")

    assert sysinfo._cpu_freq_mhz() == 2800.0


def test_an_undeterminable_clock_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """`unknown` is the established convention here, and beats inventing a 0."""
    monkeypatch.setattr(sysinfo, "CPU_MAX_FREQ", "/nonexistent/cpufreq")
    monkeypatch.setattr(sysinfo, "_cpu_name", lambda: "a CPU with no clock in its name")

    assert sysinfo._cpu_freq_mhz() == sysinfo.UNKNOWN


def test_no_gpu_reports_zero_vram_not_null(monkeypatch: pytest.MonkeyPatch) -> None:
    """`0.0` beside "none detected" is a complete statement; `null` is a hole.

    The GPU is stated rather than detected: this asserted against whatever
    hardware happened to be running it, which is a test that means one thing on
    a laptop and another on a CI runner.
    """
    monkeypatch.setattr(sysinfo, "_gpu_name", lambda: "none detected")

    assert sysinfo._vram_gb() == 0.0


def test_cpu_name_falls_back_when_proc_is_unreadable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sysinfo.platform, "system", lambda: "Linux")
    monkeypatch.setattr(sysinfo, "open", _raising_open, raising=False)
    assert isinstance(sysinfo._cpu_name(), str)


def test_cpu_name_on_non_linux_uses_platform_module(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sysinfo.platform, "system", lambda: "Windows")
    monkeypatch.setattr(sysinfo.platform, "processor", lambda: "Intel(R) Core(TM) i9")
    assert sysinfo._cpu_name() == "Intel(R) Core(TM) i9"


def test_cpu_name_falls_back_to_machine_when_processor_is_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sysinfo.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(sysinfo.platform, "processor", lambda: "")
    monkeypatch.setattr(sysinfo.platform, "machine", lambda: "arm64")
    assert sysinfo._cpu_name() == "arm64"


def test_ram_reports_a_number_or_unknown() -> None:
    value = sysinfo._ram_gb()
    assert value == sysinfo.UNKNOWN or value > 0


def test_the_posix_probe_degrades_when_sysconf_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`raising=False`, and asserted on the POSIX probe rather than `_ram_gb`.

    Two reasons, both found by a teammate running this on Windows:

    `monkeypatch.setattr(os, "sysconf", ...)` cannot replace an attribute that
    does not exist, and `os.sysconf` is POSIX-only — so the test guarding the
    POSIX-only bug was itself POSIX-only, green on ubuntu CI and an error on
    the machines matches are played from. Exactly the shape of the defect it
    exists to catch.

    And it asserted through `_ram_gb`, which now falls back to the Windows
    probe: on Windows that legitimately returns a real number, so the
    assertion was wrong there even once the patch worked.
    """

    def _raise(_name: str) -> int:
        raise ValueError("unsupported")

    monkeypatch.setattr(sysinfo.os, "sysconf", _raise, raising=False)

    assert sysinfo._ram_unix() == sysinfo.UNKNOWN


def test_gpu_reports_none_when_nvidia_smi_is_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sysinfo.shutil, "which", lambda _name: None)
    assert sysinfo._gpu_name() == "none detected"


def test_gpu_reports_the_first_device(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sysinfo.shutil, "which", lambda _name: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(
        sysinfo.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, "NVIDIA GeForce RTX 2060\n", ""),
    )
    assert sysinfo._gpu_name() == "NVIDIA GeForce RTX 2060"


def test_gpu_degrades_when_the_probe_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sysinfo.shutil, "which", lambda _name: "/usr/bin/nvidia-smi")

    def _raise(*_args, **_kwargs):
        raise OSError("driver not loaded")

    monkeypatch.setattr(sysinfo.subprocess, "run", _raise)
    assert sysinfo._gpu_name() == sysinfo.UNKNOWN


def test_gpu_handles_empty_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sysinfo.shutil, "which", lambda _name: "/usr/bin/nvidia-smi")
    monkeypatch.setattr(
        sysinfo.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, "\n", ""),
    )
    assert sysinfo._gpu_name() == "none detected"


def test_git_commit_returns_unknown_without_git(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sysinfo.shutil, "which", lambda _name: None)
    assert sysinfo.git_commit() == sysinfo.UNKNOWN


def test_git_commit_degrades_when_the_call_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sysinfo.shutil, "which", lambda _name: "/usr/bin/git")

    def _raise(*_args, **_kwargs):
        raise subprocess.SubprocessError("boom")

    monkeypatch.setattr(sysinfo.subprocess, "run", _raise)
    assert sysinfo.git_commit() == sysinfo.UNKNOWN


def test_git_commit_reads_head(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sysinfo.shutil, "which", lambda _name: "/usr/bin/git")
    monkeypatch.setattr(
        sysinfo.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, "a" * 40 + "\n", ""),
    )
    assert sysinfo.git_commit() == "a" * 40


def test_git_commit_in_this_repository_is_a_hash_or_unknown() -> None:
    commit = sysinfo.git_commit(str(Path(__file__).resolve().parents[3]))
    assert commit == sysinfo.UNKNOWN or len(commit) == 40


def _raising_open(*_args, **_kwargs):
    raise OSError("permission denied")


# ------------------------------------------------------- the Windows RAM path


class FakeKernel32:
    """Stands in for `ctypes.windll.kernel32.GlobalMemoryStatusEx`.

    Injected so the Windows branch is exercised from Linux. Without this it is
    code that only runs where the suite does not — which is exactly how
    `os.sysconf` (POSIX-only) shipped as the sole probe and left every Windows
    machine reporting `ram_gb: unknown` into the Step-0 declaration.
    """

    def __init__(self, total_bytes: int = 8 * 1024**3, ok: bool = True) -> None:
        self.total_bytes = total_bytes
        self.ok = ok

    def GlobalMemoryStatusEx(self, reference) -> int:  # noqa: N802 - Win32 spelling
        if not self.ok:
            return 0
        reference._obj.ullTotalPhys = self.total_bytes
        return 1


def test_the_windows_probe_reports_physical_memory():
    assert sysinfo._ram_windows(FakeKernel32(total_bytes=8 * 1024**3)) == 8.0


def test_a_failing_windows_call_degrades_rather_than_raising():
    """A blank is bad; a crash while building the declaration is worse."""
    assert sysinfo._ram_windows(FakeKernel32(ok=False)) == sysinfo.UNKNOWN


@pytest.mark.skipif(platform.system() == "Windows", reason="windll exists here")
def test_the_windows_probe_is_absent_off_windows():
    """`ctypes.windll` does not exist off Windows, and that must be a quiet
    UNKNOWN rather than a crash while building the declaration.

    Skipped on Windows, where the probe correctly returns a real number — the
    assertion is about the *absence* path, and asserting it unconditionally
    made the test pass only on the platform that cannot exercise the branch.
    The injected-stub tests above cover the Windows path from either OS.
    """
    assert sysinfo._ram_windows() == sysinfo.UNKNOWN


def test_the_combined_probe_prefers_whichever_platform_answers():
    """One entry point, so `collect_spec` never has to know the platform.

    Asserted without naming a platform: this must hold on ubuntu CI *and* on
    the Windows machines the matches are played from, by whichever probe
    answers there. The old message claimed "this suite runs on POSIX", which
    stopped being true the moment a teammate ran it.
    """
    assert sysinfo._ram_gb() != sysinfo.UNKNOWN, "one probe must answer on any platform we run on"


def test_the_posix_probe_computes_memory_from_pages(monkeypatch: pytest.MonkeyPatch):
    """The POSIX arithmetic, exercised from any OS — including Windows.

    Injected rather than monkeypatched onto `os`, because `os.sysconf` does not
    exist on Windows: there is no attribute to replace with a *success*, so
    this multiplication was unreachable from half the team's machines. The
    mirror of the Windows-path gap `FakeKernel32` already closes.
    """
    monkeypatch.delattr(sysinfo.os, "sysconf", raising=False)

    assert sysinfo._ram_unix(lambda name: {"SC_PHYS_PAGES": 2 * 1024**2, "SC_PAGE_SIZE": 4096}[name]) == 8.0


def test_the_posix_probe_is_absent_off_posix(monkeypatch: pytest.MonkeyPatch):
    """No `os.sysconf` is a quiet UNKNOWN, not an AttributeError mid-declaration."""
    monkeypatch.delattr(sysinfo.os, "sysconf", raising=False)

    assert sysinfo._ram_unix() == sysinfo.UNKNOWN
