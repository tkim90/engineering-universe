# API and UI Spec

## API (Vercel)

### `GET /api/search`

Query params:

- `q` (string, required): user query.
- `mode` (keyword|hybrid|semantic): search mode.
- `limit` (1-50): result count.

Response:

```
{
  "query": "redis",
  "mode": "hybrid",
  "count": 10,
  "results": [
    { "doc_id": "...", "title": "...", "url": "...", "score": 0.12 }
  ]
}
```

### `GET /api/health`

```
{ "status": "ok" }
```

## UI

- Single HTML page with search input + mode selector.
- Minimal list of results, each linking to canonical URL.
- No framework dependencies.
