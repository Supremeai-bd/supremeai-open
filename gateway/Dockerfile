# বাংলা: পাতলা গেটওয়ে ইমেজ — কোনো secret ইমেজ-স্তরে নয়, সব runtime-env
FROM python:3.11-slim
WORKDIR /app

# Requirements live at the satellite root (federation_satellite_sync.py maps
# gateway/requirements.txt -> requirements.txt); single source, no flat copy.
COPY requirements*.txt /app/
RUN pip install --no-cache-dir -r requirements.txt || pip install --no-cache-dir fastapi uvicorn httpx pydantic pyyaml

COPY contracts/ contracts/
COPY config/ config/

# বাংলা: #1772 মূল-কারণ সংশোধন — অ্যাপ নিজের কোডকে `gateway.*` নেমস্পেস হিসেবে
# ইমপোর্ট করে (app.py সহ ১৬+ ইমপোর্ট-সাইট; correlation_id/security_headers সহ)।
# পুরনো flat `service/` লেআউটে `uvicorn service.app:app` বুটেই ImportError করত —
# এখন থেকে প্যাকেজ-সত্য লেআউট: gateway/ প্যাকেজ হিসেবেই শিপ হবে, রানও সেভাবেই।
COPY gateway/ gateway/

# বাংলা: P2 — boot-এ vault-pull (infisical_bootstrap) চেষ্টা করবে, না পারলে সরাসরি uvicorn স্টার্ট হবে
# এতে কোনো অবস্থাতেই Render কন্টেইনার update_failed বা ক্র্যাশ করবে না।
COPY runtime/infisical_bootstrap.py runtime/infisical_bootstrap.py

EXPOSE 8787

RUN useradd -m -u 1000 app && chown -R app:app /app

USER app

# বাংলা: CMD — infisical_bootstrap সফল হলে তা দিয়ে চালাবে, ফেইল করলে সরাসরি uvicorn দিয়ে সার্ভিস লাইভ রাখবে
CMD ["sh", "-c", "(python runtime/infisical_bootstrap.py uvicorn gateway.service.app:app --host 0.0.0.0 --port ${PORT:-8787}) || (uvicorn gateway.service.app:app --host 0.0.0.0 --port ${PORT:-8787})"]
