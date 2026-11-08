"""Read-only Linux telemetry, kept independent of the AI and installer engine."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import time


@dataclass(frozen=True)
class Snapshot:
    timestamp: float
    load_1m: float | None
    memory_total_kib: int | None
    memory_available_kib: int | None
    uptime_seconds: float | None
    cpu_temp_c: float | None

    @property
    def memory_used_percent(self) -> float | None:
        if not self.memory_total_kib or self.memory_available_kib is None:
            return None
        return round(100 * (1 - self.memory_available_kib / self.memory_total_kib), 1)


def _meminfo(path: Path) -> tuple[int | None, int | None]:
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError):
        return None, None
    values = {}
    for line in lines:
        key, sep, value = line.partition(":")
        if not sep or key not in ("MemTotal", "MemAvailable"):
            continue
        parts = value.strip().split()
        if len(parts) == 2 and parts[1] == "kB":
            try:
                values[key] = int(parts[0])
            except ValueError:
                pass
    return values.get("MemTotal"), values.get("MemAvailable")


def _temperature(root: Path, hwmon: Path | None = None) -> float | None:
    # Only identified CPU zones qualify; motherboard/GPU zones are not CPU telemetry.
    for path in sorted(root.glob("thermal_zone*/temp")):
        try:
            kind = (path.parent / "type").read_text(encoding="ascii").strip().lower()
            if kind not in ("x86_pkg_temp", "cpu-thermal", "k10temp", "zenpower"):
                continue
            value = int(path.read_text(encoding="ascii").strip()) / 1000
            if -20 <= value <= 125:
                return round(value, 1)
        except (OSError, UnicodeError, ValueError):
            continue
    # Ryzen generally exposes k10temp through hwmon rather than thermal zones.
    if hwmon is not None:
        for sensor in sorted(hwmon.glob('hwmon*/name')):
            try:
                if sensor.read_text(encoding='ascii').strip() not in ('k10temp', 'zenpower', 'coretemp'):
                    continue
                for label in sorted(sensor.parent.glob('temp*_label')):
                    if label.read_text(encoding='ascii').strip() not in ('Tdie', 'Tctl', 'Package id 0'):
                        continue
                    value = int(label.with_name(label.name.replace('_label', '_input')).read_text()) / 1000
                    if -20 <= value <= 125:
                        return round(value, 1)
            except (OSError, UnicodeError, ValueError):
                continue
    return None


def snapshot(proc: Path = Path("/proc"), thermal: Path = Path("/sys/class/thermal"),
             hwmon: Path | None = None) -> Snapshot:
    total, available = _meminfo(proc / "meminfo")
    try:
        load = float((proc / "loadavg").read_text(encoding="ascii").split()[0])
    except (OSError, UnicodeError, ValueError, IndexError):
        load = None
    try:
        uptime = float((proc / "uptime").read_text(encoding="ascii").split()[0])
    except (OSError, UnicodeError, ValueError, IndexError):
        uptime = None
    return Snapshot(
        timestamp=time.time(),
        load_1m=load,
        memory_total_kib=total,
        memory_available_kib=available,
        uptime_seconds=uptime,
        cpu_temp_c=_temperature(thermal, hwmon),
    )


def format_snapshot(data: Snapshot) -> str:
    load = f"{data.load_1m:.2f}" if data.load_1m is not None else "unknown"
    mem = f"{data.memory_used_percent:.1f}%" if data.memory_used_percent is not None else "unknown"
    temp = f"{data.cpu_temp_c:.1f}°C (identified CPU zone)" if data.cpu_temp_c is not None else "unknown"
    return f"Load 1m: {load} | RAM used: {mem} | Temp: {temp}"


async def async_snapshot() -> Snapshot:
    """Isolate potentially slow proc/sysfs reads without blocking the UI loop."""
    import json
    import sys
    from .process import run
    code, output = await run([sys.executable, '-m', 'tui.telemetry'],
                             cwd=Path(__file__).resolve().parent.parent, timeout=3)
    if code:
        raise OSError('Telemetry collector failed')
    return Snapshot(**json.loads(output))


if __name__ == '__main__':
    import json
    from dataclasses import asdict
    print(json.dumps(asdict(snapshot(hwmon=Path('/sys/class/hwmon')))))

