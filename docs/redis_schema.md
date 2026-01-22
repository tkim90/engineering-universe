# Redis Schema and Queries

## Keys

- `crawl:queue` list of URL events (`url\\tsource\\tdepth`).
- `crawl:delay` sorted set for delayed URLs (score = next_allowed_ts).
- `crawl:seen` set of normalized URLs that were enqueued.
- `crawl:doc_seq` integer sequence for crawl doc IDs.
- `crawl:doc:{doc_id}` hash of crawl metadata (url, domain, paths, depth, status).
- `raw:queue` list of crawl document IDs ready for indexing.
- `doc:{doc_id}` hash of indexed document fields.
- `robots:{domain}` hash of robots rules.
- `robots:next_allowed:{domain}` string unix timestamp.

## Disk Storage

- Raw and cleaned HTML are stored under `CRAWL_STORAGE_DIR` using:
  - `{doc_id}/raw_{url_hash}.html`
  - `{doc_id}/clean_{url_hash}.html`

## RediSearch Index

```
FT.CREATE idx:blogs ON HASH PREFIX 1 doc: SCHEMA \
  title TEXT content TEXT \
  topics TAG SEPARATOR , \
  source TAG SEPARATOR , \
  company TAG SEPARATOR , \
  authors TAG SEPARATOR , \
  published_at TEXT \
  url TEXT \
  lang TAG SEPARATOR , \
  embedding VECTOR HNSW 6 TYPE FLOAT32 DIM 384 DISTANCE_METRIC COSINE
```

## Query Templates

### Keyword (BM25)

```
FT.SEARCH idx:blogs "@title|content:redis" LIMIT 0 10
```

### Vector + Keyword (Hybrid)

```
FT.SEARCH idx:blogs "(@title|content:redis)=>[KNN 10 @embedding $vec AS vector_score]" \
  PARAMS 2 vec $vector_bytes \
  SORTBY vector_score \
  RETURN 3 title url vector_score \
  DIALECT 2
```

### Filters

```
@company:{Meta} @topics:{Kafka} @lang:{en_US}
```
