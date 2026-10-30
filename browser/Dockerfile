# SupremeAI Browser - lightweight Gemini cookie relay (no browser, ~30MB RAM)
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py main.py ./

RUN useradd -m -u 1000 app && chown -R app:app /app

ENV PYTHONUNBUFFERED=1
ENV PORT=8080

EXPOSE 8080

USER app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
