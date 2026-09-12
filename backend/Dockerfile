FROM python:3.11-slim

# gcc for a couple of wheels; redis-server so a single container can also
# host the job queue (see start.sh). Railway uses its own Redis plugin and
# simply never starts this one.
RUN apt-get update && apt-get install -y --no-install-recommends gcc redis-server \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY start.sh .
RUN chmod +x start.sh

# Hugging Face Spaces run the container as UID 1000; give it a home so
# anything that wants to write (caches, temp files) has somewhere to go.
RUN useradd -m -u 1000 app && chown -R app:app /app
USER app
ENV HOME=/home/app

# 7860 is what Hugging Face Spaces expects; Railway passes $PORT instead.
EXPOSE 7860
ENV PORT=7860

CMD ["./start.sh"]
