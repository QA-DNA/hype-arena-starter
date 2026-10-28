FROM --platform=linux/amd64 python:3.12-slim
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir sentence-transformers model2vec scikit-learn
COPY fetch_models.py /tmp/fetch_models.py
RUN python /tmp/fetch_models.py && rm -f /tmp/fetch_models.py && chmod -R a+rX /app/models
ENV HOME=/tmp HF_HOME=/tmp/hf HF_HUB_OFFLINE=1 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 RAYON_NUM_THREADS=2 TOKENIZERS_PARALLELISM=false
WORKDIR /app
COPY bench.py practice.csv /app/
USER 10001
CMD ["python", "/app/bench.py"]
