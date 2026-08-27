FROM python:3.11-slim

WORKDIR /app
COPY requirements-optional.txt /app/requirements-optional.txt
RUN pip install --no-cache-dir -r /app/requirements-optional.txt
COPY multimodal_creative_agent /app/multimodal_creative_agent
ENV PYTHONPATH=/app/multimodal_creative_agent

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
