# Deployment Notes

## Vercel

- Deploy `api/search.py` as serverless function.
- Host `web/` as static assets.
- Env vars: `REDIS_URL`, `EMBEDDINGS_PROVIDER`, `EMBEDDINGS_DIM`.

## Workers

- Run crawler and indexer as containerized workers.
- Scale crawler concurrency via `MAX_WORKERS`.
- Use a process manager (systemd, supervisor, or Kubernetes).

## Redis

- Use Redis Stack with RediSearch enabled.
- Enable RDB snapshots and upload to object storage.
- Snapshot schedule: hourly + daily retention.

## robots.txt Policy

- Store `robots:{domain}` hash (crawl_delay_s, allowed, fetched_at).
- Store `robots:next_allowed:{domain}` timestamp for per-domain throttling.
- Worker flow: dequeue URL → check robots cache → obey crawl-delay.

## Metrics

- Expose Prometheus metrics on `METRICS_PORT`.
- Dashboards: crawler RPS, indexer docs/sec, search latency.
