"""Run the compiled Rust feature exporter without exposing evaluator labels."""
import argparse
from pathlib import Path
import subprocess


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=Path("artifacts/verifier-lab"))
    parser.add_argument("--names", default="fit,validation,refit,practice390")
    parser.add_argument("--modes", default="inferred,oracle")
    parser.add_argument("--binary", type=Path, default=Path("target/release/examples/verifier_features"))
    parser.add_argument("--lexicon", type=Path, default=Path("data/lexicon.json"))
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    for name in args.names.split(","):
        for mode in args.modes.split(","):
            source = args.base / "inputs" / f"{name}-{mode}.json"
            target = (args.output_dir or args.base / "features") / f"{name}-{mode}.jsonl"
            subprocess.run([str(args.binary), str(source), str(args.lexicon), str(target)], check=True)
