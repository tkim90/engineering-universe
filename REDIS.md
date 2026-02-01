  Key Pattern: crawl:queue
  Type: List
  Description: FIFO queue of URLs pending crawl
  ────────────────────────────────────────
  Key Pattern: crawl:delay
  Type: Sorted Set
  Description: URLs delayed due to rate limiting, scored by next-allowed timestamp
  ────────────────────────────────────────
  Key Pattern: crawl:seen
  Type: Set
  Description: Dedupe set of all URLs ever enqueued
  ────────────────────────────────────────
  Key Pattern: crawl:doc_seq
  Type: String (int)
  Description: Auto-incrementing counter for doc IDs
  ────────────────────────────────────────
  Key Pattern: crawl:doc:{docId}
  Type: Hash
  Description: Metadata for a crawled page (url, domain, paths, status, etc.)
  ────────────────────────────────────────
  Key Pattern: raw:queue
  Type: List
  Description: Queue of doc IDs waiting to be indexed
  ────────────────────────────────────────
  Key Pattern: robots:{domain}
  Type: Hash
  Description: Cached robots.txt rules (crawl_delay, request_rate, allowed, text)
  ────────────────────────────────────────
  Key Pattern: robots:next_allowed:{domain}
  Type: String (int)
  Description: Timestamp when next request to domain is allowed
  ────────────────────────────────────────
  Key Pattern: doc:{docId}
  Type: Hash
  Description: Indexed document data for search (title, content, embeddings, etc.)
  ────────────────────────────────────────
  Key Pattern: idx:blogs
  Type: RediSearch Index
  Description: Full-text search index over doc:* hashes
