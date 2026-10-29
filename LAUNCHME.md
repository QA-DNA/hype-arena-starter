# Hooly Hype Arena - Quick Launch Guide (100% Offline)

This guide explains how to start the **Frontend** and run the **Docker Container** completely offline.

---

## 1. How to Start the Frontend (100% Offline)

The frontend shows the system's architecture diagram and runs the live pipeline (`src/label_rows.py` + `generate_claims.py`) on the 20-row jury sample (`datasets/sample.csv`) or custom inputs.

### Quick Start:
```bash
# 1. Ensure core ML dependencies are available (no extra web framework needed):
pip install numpy pandas scipy scikit-learn

# 2. Launch the standard library Python server:
python frontend/server.py
```

### In Browser:
1. Open [http://localhost:8000](http://localhost:8000).
2. Click **"Load sample"** to load the 20 unlabelled rows from `datasets/sample.csv`.
3. Click **"Run system"**:
   - The interactive SVG architecture diagram lights up sequentially as each layer processes.
   - Predictions are displayed with color-coded labels (`true`, `false`, `unsure` with empty confidence).
   - Exactly 1,000 new verified claims are generated across the 5 contract types (`fact`, `compare`, `change`, `at_event`, `relation`).
4. Click **"Download output.csv"** to save the verified submission table.

### Smoke Test:
```bash
python frontend/test_server.py
```

---

## 2. How to Run the System in Docker (100% Offline)

The Docker container runs under the exact official hackathon constraints:
- Non-root user `USER 10001`
- Read-only root filesystem
- Zero network access (`--network none`)
- 2 CPUs, 6 GiB RAM, 256 process limit

### Build the Image:
```bash
docker build --platform linux/amd64 -t hype-arena .
```

### Run with the Official Referee Test Harness:
- **On Linux / macOS:**
  ```bash
  scripts/check.sh hype-arena
  ```
- **On Windows (PowerShell):**
  ```powershell
  powershell scripts/check.ps1
  ```

### Run Manually with Docker:
```bash
docker run --rm --platform linux/amd64 \
  --network none --read-only --user 10001:10001 \
  --cpus 2 --memory 6g --pids-limit 256 \
  --tmpfs /tmp:rw,size=128m,mode=1777 \
  -v "$(pwd)/datasets:/universe:ro" \
  -v "$(pwd)/output:/output" \
  hype-arena
```

### Verify Output against Official Referee:
```bash
python scripts/check_output.py output data/practice.csv datasets/sample.csv
```
Expected output:
```text
labels: 20 of the 20 hidden rows labelled; 0 right, 0 wrong, 7 unsure, against the practice labels
claims: 1000 new claims
the format checks pass
```
