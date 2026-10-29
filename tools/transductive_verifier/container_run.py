"""Run a research command and record real Linux child RSS/cgroup peak metadata."""
import argparse
import json
from pathlib import Path
import platform
import resource
import subprocess
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--metadata", type=Path, required=True)
parser.add_argument("command", nargs=argparse.REMAINDER)
args = parser.parse_args()
if not args.command:
    parser.error("command required")
start = time.monotonic()
result = subprocess.run(args.command, check=False)
cpu = next((line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines() if line.startswith("model name")), "unknown")
peak = Path("/sys/fs/cgroup/memory.peak")
metadata = {"command": args.command, "exit_code": result.returncode, "seconds": time.monotonic() - start,
            "hardware": cpu, "architecture": platform.machine(), "cpu_limit": 2, "memory_limit_bytes": 6 * 1024**3,
            "peak_child_rss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
            "cgroup_peak_bytes": int(peak.read_text()) if peak.exists() else None,
            "threads": "Rust extraction and feature evaluation single compute thread; GBT host libraries capped at two"}
args.metadata.parent.mkdir(parents=True, exist_ok=True)
args.metadata.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
print(json.dumps(metadata), flush=True)
raise SystemExit(result.returncode)
