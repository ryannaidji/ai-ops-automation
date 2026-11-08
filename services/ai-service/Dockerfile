FROM python:3.11-slim
WORKDIR /app/services/ai-service
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
ENV DOCS_DIR=/app/docs DB_PATH=/app/data/tickets.db
EXPOSE 8000
CMD ["uvicorn", "app.main:get_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
