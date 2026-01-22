import os

from dotenv import load_dotenv


load_dotenv("secrets.env", override=False)


def env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def env_bool(name: str, default: str = "false") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


class Settings:
    user_agent = os.getenv("EU_USER_AGENT", "EngUniverseBot/0.1")
    redis_url = env("REDIS_URL", "redis://default:devpass@localhost:6379/0")
    crawl_queue_key = os.getenv("CRAWL_QUEUE_KEY", "crawl:queue")
    crawl_delay_key = os.getenv("CRAWL_DELAY_KEY", "crawl:delay")
    raw_queue_key = os.getenv("RAW_QUEUE_KEY", "raw:queue")
    robots_key_prefix = os.getenv("ROBOTS_KEY_PREFIX", "robots:")
    robots_next_allowed_prefix = os.getenv(
        "ROBOTS_NEXT_ALLOWED_PREFIX", "robots:next_allowed:"
    )
    crawl_seen_key = os.getenv("CRAWL_SEEN_KEY", "crawl:seen")
    crawl_doc_seq_key = os.getenv("CRAWL_DOC_SEQ_KEY", "crawl:doc_seq")
    crawl_doc_key_prefix = os.getenv("CRAWL_DOC_KEY_PREFIX", "crawl:doc:")
    crawl_storage_dir = os.getenv("CRAWL_STORAGE_DIR", "data/crawl")
    crawl_depth_limit = int(os.getenv("CRAWL_DEPTH_LIMIT", 3))
    crawl_allow_external = env_bool("CRAWL_ALLOW_EXTERNAL", "false")
    crawl_log = env_bool("CRAWL_LOG", "true")
    seed_domains = os.getenv(
        "SEED_DOMAINS",
        "engineering.fb.com,builders.ramp.com,www.anthropic.com,developers.openai.com",
    )
    seed_start_urls = os.getenv(
        "SEED_START_URLS",
        "https://engineering.fb.com/,https://builders.ramp.com/,https://www.anthropic.com/engineering,https://developers.openai.com/blog/",
    )
    max_concurrency = int(os.getenv("CRAWLER_CONCURRENCY", 200))
    request_timeout_s = int(os.getenv("REQUEST_TIMEOUT_S", 20))
    crawl_delay_default_s = int(os.getenv("CRAWL_DELAY_DEFAULT_S", 5))
    embeddings_provider = os.getenv("EMBEDDINGS_PROVIDER", "dummy")
    embeddings_dim = int(os.getenv("EMBEDDINGS_DIM", 384))
    indexer_exit_on_idle = env_bool("INDEXER_EXIT_ON_IDLE", "true")
    indexer_idle_grace_s = float(os.getenv("INDEXER_IDLE_GRACE_S", "2"))
    metrics_port = int(os.getenv("METRICS_PORT", 9100))
    api_port = int(os.getenv("API_PORT", 8080))
