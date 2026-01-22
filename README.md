## Eng Universe

Hybrid search stack for engineering blogs (Meta, Ramp, Anthropic, OpenAI).

### Quickstart

1. Set env vars:
   - `REDIS_URL`
   - `EMBEDDINGS_PROVIDER` (default: `dummy`)
   - `PYLATE_MODEL_NAME` (when using `EMBEDDINGS_PROVIDER=pylate`)
   - `PYLATE_INDEX_FOLDER`
   - `PYLATE_INDEX_NAME`
   - `PYLATE_BATCH_SIZE`
   - `PYLATE_DEVICE`
   - `HUGGINGFACE_API_KEY` (when using `EMBEDDINGS_PROVIDER=huggingface`)
   - `HUGGINGFACE_BASE_URL`
   - `HUGGINGFACE_EMBEDDINGS_MODEL` (use a standard embedding model; ColBERT models require `EMBEDDINGS_PROVIDER=pylate`)
   - `CRAWLER_CONCURRENCY`
2. Initialize search index:
   - `python main.py init-index`
   - For `EMBEDDINGS_PROVIDER=pylate`, this creates a local PLAID index on disk.
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
