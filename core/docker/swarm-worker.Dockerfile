FROM python:3.11-slim

WORKDIR /app

# Upgrade pip and install minimal edge worker dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir nats-py pydantic litellm langchain

# We assume the user maps or copies the core messaging and worker scripts here
COPY core/nats_messaging.py ./core/
COPY engine/worker_node.py ./engine/

# Set Python path so imports work correctly
ENV PYTHONPATH="/app"

# NATS_TOKEN এবং NATS_URL রানটাইমে environment variable হিসেবে পাস করতে হবে।
# বাংলা মন্তব্য: Hardcoded secrets Dockerfile-এ রাখা নিরাপদ নয়।
# ব্যবহার: docker run -e NATS_TOKEN=$NATS_TOKEN -e NATS_URL=nats://... image
# NATS_URL default for container-to-host connectivity:
ENV NATS_URL="nats://host.docker.internal:4222"

# Create and switch to non-root user for security compliance (Trap #97)
RUN addgroup --system supremeai && adduser --system supremeai --ingroup supremeai && \
    chown -R supremeai:supremeai /app
USER supremeai

CMD ["python", "engine/worker_node.py"]
