## Eng Universe

Hybrid search stack for engineering blogs (Meta, Ramp, Anthropic, OpenAI).

### Quickstart

1. Set env vars:
   - `REDIS_URL`
   - `EMBEDDINGS_PROVIDER` (default: `dummy`)
   - `CRAWLER_CONCURRENCY`
2. Initialize search index:
   - `python main.py init-index`
3. Seed and crawl:
   - `python main.py seed`
   - `python main.py crawl`
4. Run indexer:
   - `python main.py index`
5. API:
   - `uvicorn api.search:app --reload`

### Docs

- `docs/spec.md`
- `docs/redis_schema.md`
- `docs/api_ui.md`
- `docs/deploy.md`

### Docker

- Build: `docker compose build`
- Seed: `docker compose --profile seed up`
- Crawler + Redis: `docker compose --profile crawler up`
- Indexer + Redis: `docker compose --profile indexer up`
- API + Redis: `docker compose --profile api up`
- Metrics: `docker compose --profile metrics up`
