# Redis Schema and Queries

## Keys

- `crawl:queue` list of URL events (`url\\tsource`).
- `crawl:delay` sorted set for delayed URLs (score = next_allowed_ts).
- `raw:queue` list of raw document IDs.
- `raw:{doc_id}` hash of raw HTML.
- `doc:{doc_id}` hash of indexed document fields.
- `robots:{domain}` hash of robots rules.
- `robots:next_allowed:{domain}` string unix timestamp.

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
  embedding VECTOR HNSW 12 TYPE FLOAT32 DIM 384 DISTANCE_METRIC COSINE
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
  RETURN 3 title url vector_score
```

### Filters

```
@company:{Meta} @topics:{Kafka} @lang:{en_US}
```
