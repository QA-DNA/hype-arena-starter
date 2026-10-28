# The image the judges run: docker build --platform linux/amd64 .
# Runs offline as user 10001 on a read-only root; only /tmp and /output are writable.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache \
    MPLCONFIGDIR=/tmp \
    OMP_NUM_THREADS=2 \
    OPENBLAS_NUM_THREADS=2

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY polygraph/ polygraph/
COPY data/ data/

USER 10001
ENTRYPOINT ["python", "-m", "polygraph.run", "--universe", "/universe", "--output", "/output"]
