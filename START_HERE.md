# Start here: team Polygraph's workspace

The challenge is in [README.md](README.md) (the organizers'). This page is ours.

## Who does what

| Who | Branch | Owns | Brief |
| --- | --- | --- | --- |
| Captain + Claude | `engine` | reader, linker, attributor, truth, judge, run, Dockerfile | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Backend teammate | `forge` | forge (the 1,000 claims), validate, server/app.py | [docs/BRIEF_backend.md](docs/BRIEF_backend.md) |
| Frontend teammate | `frontend` | `web/` (the Polygraph console) | [docs/BRIEF_frontend.md](docs/BRIEF_frontend.md) |

Only the captain merges into `main`. Git how-to: [docs/WORKFLOW.md](docs/WORKFLOW.md).

## First time (10 minutes)

You need Python 3.11+ and git.

```powershell
git clone https://github.com/tudsac2308/hype-arena-starter.git
cd hype-arena-starter
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

On Mac/Linux, run `sh scripts/setup.sh` instead. Setup creates `.venv`, installs everything, runs the tests and prints a first evaluation. Then, in every new terminal:

```powershell
.venv\Scripts\Activate.ps1
```

## The four commands you'll use all night

| Command | What it does |
| --- | --- |
| `python scripts/eval.py` | **Main loop.** Hides every 5th practice label, runs the system, and prints label accuracy, the confusion matrix, claim counts and validator problems |
| `python scripts/eval.py --gold-extraction` | The same, but uses the organizers' extracted facts, so it measures the truth engine and forge alone |
| `python -m pytest` | Tests: every example in `contracts/value-forms.md`, the linker, rendering and the end-to-end run |
| `python scripts/run_local.py` | Runs exactly what the judges run (without Docker) and their format checker. Also writes `out/trace.json` for the frontend |

With Docker installed, `sh scripts/check.sh` runs the official check (from Git Bash).

## Rules we must never break

- **The system may not be an LLM at run time.** LLMs can help us write code and build data files.
- **Every claim must be true.** Exactly 1,000 claims, each passing `polygraph/validate.py`.
- **The run is offline:** 2 CPUs, 6 GiB, 30 minutes. `run.py` writes a safe output first, so a crash still hands something in.
- **No push to the PR after 11:00 on 29 Oct.** The final push is by 10:45.
