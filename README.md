# Eng Universe

Search engine for engineering blogs from Meta, Ramp, Anthropic, and OpenAI.
Combines keyword (BM25) and semantic search for hybrid results.

## Features

- Crawls engineering blogs with robots.txt compliance
- Hybrid search (keyword + semantic) via Redis
- FastAPI endpoint with configurable search modes
- Prometheus metrics

## Quickstart

1. Set `REDIS_URL` and optional embedding provider env vars
2. `python main.py seed && python main.py crawl` (optional: `--max-docs N --concurrency K`)
3. `python main.py index`
4. `uvicorn api.search:app --reload`

## Docker

- `docker compose --profile api up` - API + Redis
- `docker compose --profile crawler up` - Crawler
- `docker compose --profile indexer up` - Indexer

## Docs

See `docs/` for detailed specs.
