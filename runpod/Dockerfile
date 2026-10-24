FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/src \
    MODEL_PATH=/app/src/forecast/artifacts/model.pt \
    DEVICE=auto

WORKDIR /app

COPY runpod/requirements.txt /app/runpod/requirements.txt

# CPU is enough for this small quantile MLP. For a CUDA build, pass:
#   --build-arg TORCH_INDEX_URL=https://download.pytorch.org/whl/cu124
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir --index-url "${TORCH_INDEX_URL}" "torch>=2.2,<3" \
    && pip install --no-cache-dir -r /app/runpod/requirements.txt

COPY src/forecast /app/src/forecast
COPY runpod /app/runpod

CMD ["python", "-u", "/app/runpod/handler.py"]
