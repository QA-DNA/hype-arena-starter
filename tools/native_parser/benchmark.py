"""Run the release extractor in the actual restricted Docker CPU contract.

Host-side development harness, requiring Python stdlib and Docker only. Native
container runtime has no Python. Reports real process RSS and cgroup peak memory.
"""
import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path


def command(*args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True,
                          encoding="utf-8", **kwargs).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="veridyct-native-extractor:selected-v2")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    input_path = args.input.resolve()
    # The shell stays alive for one measurement after the child exits, making
    # cgroup peak memory and exit status observable without a polling race.
    script = r"""
id -u > /io/uid.txt
if command -v python3 >/dev/null || command -v cargo >/dev/null; then exit 90; fi
if touch /opt/veridyct-extractor/.write-probe 2>/dev/null; then exit 91; fi
/opt/veridyct-extractor/veridyct-extractor --input /input/rows.json --output /io/rows.json --report /io/report.json
status=$?
cat /sys/fs/cgroup/memory.peak > /io/cgroup-memory-peak.txt
cat /sys/fs/cgroup/cpu.max > /io/cpu-max.txt
exit "$status"
"""
    argv = ["docker", "create", "--network", "none", "--read-only", "--cpus", "2",
            "--memory", "6g", "--user", "10001:10001", "--entrypoint", "/bin/sh",
            "--mount", f"type=bind,source={input_path},target=/input/rows.json,readonly",
            "--mount", f"type=bind,source={out},target=/io", args.image, "-c", script]
    container = command(*argv)
    try:
        started = time.perf_counter()
        run = subprocess.run(["docker", "start", "--attach", container], capture_output=True,
                             text=True, encoding="utf-8")
        wall = time.perf_counter() - started
        (out / "stderr.txt").write_text(run.stderr, encoding="utf-8")
        inspect = json.loads(command("docker", "inspect", container))[0]
        if run.returncode or inspect["State"]["ExitCode"]:
            raise RuntimeError(f"Native run failed: {run.returncode}/{inspect['State']['ExitCode']} {run.stderr}")
        image = json.loads(command("docker", "image", "inspect", args.image))[0]
        report = json.loads((out / "report.json").read_text(encoding="utf-8"))
        config = inspect["HostConfig"]
        report.update(image_id=image["Id"], image_bytes=image["Size"], docker_start_wall_seconds=wall,
                      cgroup_peak_bytes=int((out / "cgroup-memory-peak.txt").read_text()),
                      effective_uid=int((out / "uid.txt").read_text()),
                      docker=dict(network=config["NetworkMode"], readonly=config["ReadonlyRootfs"],
                                  nano_cpus=config["NanoCpus"], memory_bytes=config["Memory"],
                                  oom_killed=inspect["State"]["OOMKilled"], exit_code=inspect["State"]["ExitCode"]),
                      cpu_max=(out / "cpu-max.txt").read_text().strip(),
                      hardware=command("docker", "run", "--rm", "--network", "none", "--read-only",
                                       "--entrypoint", "sh", args.image, "-c", "sed -n 's/^model name[[:space:]]*: //p' /proc/cpuinfo | head -n 1"),
                      source_commit=command("git", "rev-parse", "HEAD"),
                      output_sha256=hashlib.sha256((out / "rows.json").read_bytes()).hexdigest())
        assert report["effective_uid"] == 10001
        assert report["image_bytes"] <= 3 * 1024**3
        assert report["cgroup_peak_bytes"] <= 6 * 1024**3
        assert report["docker"]["network"] == "none" and report["docker"]["readonly"]
        assert report["docker"]["nano_cpus"] == 2_000_000_000
        assert report["docker"]["memory_bytes"] == 6 * 1024**3
        (out / "benchmark.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
    finally:
        command("docker", "rm", container)


if __name__ == "__main__":
    main()
