FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "streamlit>=1.66,<2" "requests>=2.31,<3"
COPY .streamlit /app/.streamlit
COPY dashboard /app/dashboard
ENV API_BASE_URL=http://api:8000/api/v1
EXPOSE 8501
CMD ["sh", "-c", "streamlit run dashboard/app.py --server.address=0.0.0.0 --server.port=${PORT:-8501} --server.headless=true"]
