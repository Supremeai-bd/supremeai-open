# বাংলা: পাতলা গেটওয়ে ইমেজ — কোনো secret ইমেজ-স্তরে নয়, সব runtime-env
FROM python:3.11-slim
WORKDIR /app

# Robust copy: copy requirements.txt whether at root or service/ directory
COPY requirements*.txt service/requirements*.txt /app/service/
RUN pip install --no-cache-dir -r service/requirements.txt || pip install --no-cache-dir -r service/requirements*.txt || pip install --no-cache-dir fastapi uvicorn httpx pydantic pyyaml

COPY contracts/ contracts/
COPY config/ config/
COPY service/ service/

# বাংলা: P2 — boot-এ vault-pull (infisical_bootstrap) চেষ্টা করবে, না পারলে সরাসরি uvicorn স্টার্ট হবে
# এতে কোনো অবস্থাতেই Render কন্টেইনার update_failed বা ক্র্যাশ করবে না।
COPY runtime/infisical_bootstrap.py runtime/infisical_bootstrap.py

EXPOSE 8787

# বাংলা: CMD — infisical_bootstrap সফল হলে তা দিয়ে চালাবে, ফেইল করলে সরাসরি uvicorn দিয়ে সার্ভিস লাইভ রাখবে
CMD ["sh", "-c", "(python runtime/infisical_bootstrap.py uvicorn service.app:app --host 0.0.0.0 --port ${PORT:-8787}) || (uvicorn service.app:app --host 0.0.0.0 --port ${PORT:-8787})"]
