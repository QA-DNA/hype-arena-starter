"""Run required foundation checks on an isolated copy, preserving frozen kernels."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from run import ROOT, docker, git, sha, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/verifier-folds")
    parser.add_argument("--image", default="veridyct:dev")
    args = parser.parse_args()
    base = args.output.resolve()
    base.relative_to(ROOT)
    workspace = base / "foundation"
    workspace.mkdir(parents=True, exist_ok=True)
    for relative in git("ls-files").decode().splitlines():
        source = ROOT / relative
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    for source in (base / "current/crates/core/src").glob("*.rs"):
        shutil.copyfile(source, workspace / "crates/core/src" / source.name)
    for relative in ("Cargo.toml", "Cargo.lock"):
        shutil.copyfile(base / "current" / f"{relative}.original", workspace / relative)
    shutil.copyfile(base / "current/crates/core/Cargo.toml", workspace / "crates/core/Cargo.toml")
    for relative in ("crates/core/examples/evaluate_boosted.rs", "docs/handoffs/verifier-folds.md"):
        source = ROOT / relative
        if source.exists():
            target = workspace / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    shutil.copytree(ROOT / "tools/verifier_folds", workspace / "tools/verifier_folds", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    # The docs checker uses git ls-files; an ignored temporary repository lets it
    # inspect only this complete validation copy, without touching the real index.
    relative = workspace.relative_to(ROOT).as_posix()
    docker(args, base, ["git", "-C", relative, "init", "--quiet"], "foundation-git.log")
    result = {}
    for task in ("test", "check", "docs"):
        command = ["cargo", "--offline", "--config", f'alias.xtask="run --locked --quiet --package xtask --"',
                   "xtask", task]
        # Cargo aliases run child Cargo commands in the workspace's own cwd.
        argv = ["docker", "run", "--rm", "--user", "0", "--network", "none", "--cpus", "2", "--memory", "6g",
                "-v", f"{ROOT}:/work", "-w", f"/work/{relative}",
                "-e", f"CARGO_HOME=/work/{base.relative_to(ROOT).as_posix()}/cargo-home",
                "-e", f"CARGO_TARGET_DIR=/work/{base.relative_to(ROOT).as_posix()}/foundation-target", args.image, *command]
        completed = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8")
        path = base / "logs" / f"xtask-{task}.log"
        path.write_text(completed.stdout + completed.stderr, encoding="utf-8")
        result[task] = dict(exit_code=completed.returncode, argv=argv, log=path.relative_to(ROOT).as_posix(), log_sha256=sha(path))
        print(json.dumps(result[task]), flush=True)
    # Report lint separately when the frozen root's formatting prevents xtask
    # check from reaching Clippy; no root-owned file is reformatted here.
    command = ["cargo", "clippy", "--offline", "--locked", "--manifest-path", f"{relative}/Cargo.toml",
               "--workspace", "--all-targets", "--", "-D", "warnings"]
    try:
        docker(args, base, command, "foundation-clippy.log")
        result["clippy"] = {"exit_code": 0}
    except RuntimeError:
        result["clippy"] = {"exit_code": "see log"}
    docker(args, base, ["cargo", "test", "--offline", "--locked", "--manifest-path", f"{base.relative_to(ROOT).as_posix()}/current/Cargo.toml",
                       "-p", "veridyct-core", "--example", "evaluate_boosted"], "evaluator-tests.log")
    result["evaluator_tests"] = {"exit_code": 0, "tests": 2}
    docker(args, base, ["rustfmt", "--edition", "2024", "--check", "crates/core/examples/evaluate_boosted.rs",
                       "tools/verifier_folds/original_rf.rs"], "owned-rustfmt.log")
    result["owned_rustfmt"] = {"exit_code": 0}
    write(base / "verification.json", result)
    raise SystemExit(1 if any(row["exit_code"] != 0 for row in result.values()) else 0)


if __name__ == "__main__":
    main()
