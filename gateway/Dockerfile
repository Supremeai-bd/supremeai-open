# বাংলা: পাতলা গেটওয়ে ইমেজ — কোনো secret ইমেজ-স্তরে নয়, সব runtime-env
FROM python:3.11-slim
WORKDIR /app

# Robust copy: copy requirements.txt whether at root or service/ directory
COPY requirements*.txt service/requirements*.txt /app/service/
RUN pip install --no-cache-dir -r service/requirements.txt || pip install --no-cache-dir -r service/requirements*.txt || pip install --no-cache-dir fastapi uvicorn httpx pydantic pyyaml

COPY contracts/ contracts/
COPY config/ config/
COPY service/ service/

# বাংলা: P2 — boot-এ vault-pull (infisical_bootstrap) তারপর exec; identity = Render env-এ
COPY runtime/infisical_bootstrap.py runtime/infisical_bootstrap.py

EXPOSE 8787

# বাংলা: ENTRYPOINT=bootstrap, CMD=service — Render-এর PORT মানানসই (fallback 8787)
ENTRYPOINT ["python", "runtime/infisical_bootstrap.py"]
CMD ["sh", "-c", "uvicorn service.app:app --host 0.0.0.0 --port ${PORT:-8787}"]
