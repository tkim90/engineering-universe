FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY eng_universe /app/eng_universe
COPY api /app/api
COPY scripts /app/scripts
COPY main.py /app/main.py

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py", "crawl"]
