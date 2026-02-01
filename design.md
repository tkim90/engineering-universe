1. Seed and start

- python main.py seed → seed_queue() enqueues CrawlItem(url, depth=0) in crawl:queue.
- python main.py crawl → run_crawlers() starts MAX_WORKERS workers and a shared aiohttp session.

2. Worker loop (per item)

- promote_due() moves any delayed items whose time has arrived from crawl:delay → crawl:queue.
- dequeue() pops one CrawlItem(url, source, depth).

3. Robots compliance

- get_or_fetch_robots() loads robots.txt from cache or fetches it and stores in Redis.
- RobotFileParser.can_fetch() checks the URL; if disallowed → drop URL.
- reserve_next_allowed() atomically enforces crawl-delay + request-rate.
    - If not allowed yet, delay() requeues to crawl:delay with the next allowed timestamp.

4. Fetch

- fetch_html() downloads HTML (timeout guarded).
- Non‑200 or fetch failure → drop URL.

5. Link discovery (bounded)

- BeautifulSoup parses HTML.
- extract_links() collects anchor URLs, normalizes, filters out mailto/tel/js.
- If CRAWL_ALLOW_EXTERNAL=false, keeps only same domain.
- If depth < CRAWL_DEPTH_LIMIT, enqueue links with depth + 1.

6. Clean & store

- _clean_container() keeps article → main → body (removes nav/footer/aside/script/style/noscript).
- doc_id = INCR crawl:doc_seq.
- Write raw HTML to disk:
  CRAWL_STORAGE_DIR/{domain}/urls/{doc_id}/raw/{url_hash}.html
- Write cleaned HTML to disk:
  CRAWL_STORAGE_DIR/{domain}/urls/{doc_id}/cleaned/{url_hash}.html

7. Metadata record

- Redis crawl:doc:{doc_id} stores: url, domain, source, depth, paths, url_hash, fetched_at, status.
