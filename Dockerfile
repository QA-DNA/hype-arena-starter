# syntax=docker/dockerfile:1
FROM --platform=linux/amd64 python:3.11-slim

# Set environment variables for read-only root and no-home user
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp \
    TMPDIR=/tmp \
    LOKY_MAX_CPU_COUNT=2 \
    ARENA_UNIVERSE=/universe \
    ARENA_OUTPUT=/output

# Create app directory and required mountpoints
WORKDIR /app
RUN mkdir -p /universe /output /tmp && \
    chmod 1777 /tmp && \
    chmod 777 /output

# Install ML dependencies required by label_rows
RUN pip install --no-cache-dir numpy pandas scipy scikit-learn

# Copy standard library source code, ML labeler, and data dependencies
COPY src/ /app/src/
COPY data/practice.csv /app/data/practice.csv
COPY data/lexicon.json /app/data/lexicon.json
COPY generate_claims.py /app/generate_claims.py
COPY label_rows.py /app/label_rows.py
COPY entrypoint.py /app/entrypoint.py

# Ensure all files are readable by non-root user 10001
RUN chmod -R 755 /app

# Non-root user 10001 as required by contest rules
USER 10001

# Run the inference and claim packaging engine
ENTRYPOINT ["python", "/app/entrypoint.py"]
