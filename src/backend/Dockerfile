FROM python:3.12-slim
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
# COPY forecast /app/forecast
ENV PYTHONPATH=/app/backend
ENV FORECAST_PACKAGE_ROOT=/app
EXPOSE 8000
CMD ["python", "-m", "scripts.start"]
