import os


def env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


class Settings:
    user_agent = os.getenv("EU_USER_AGENT", "EngUniverseBot/0.1")
    redis_url = env("REDIS_URL", "redis://localhost:6379/0")
    crawl_queue_key = os.getenv("CRAWL_QUEUE_KEY", "crawl:queue")
    crawl_delay_key = os.getenv("CRAWL_DELAY_KEY", "crawl:delay")
    raw_queue_key = os.getenv("RAW_QUEUE_KEY", "raw:queue")
    robots_key_prefix = os.getenv("ROBOTS_KEY_PREFIX", "robots:")
    robots_next_allowed_prefix = os.getenv(
        "ROBOTS_NEXT_ALLOWED_PREFIX", "robots:next_allowed:"
    )
    seed_domains = os.getenv(
        "SEED_DOMAINS",
        "engineering.fb.com,builders.ramp.com,www.anthropic.com,developers.openai.com",
    )
    seed_start_urls = os.getenv(
        "SEED_START_URLS",
        "https://engineering.fb.com/,https://builders.ramp.com/,https://www.anthropic.com/engineering,https://developers.openai.com/blog/",
    )
    max_concurrency = int(os.getenv("CRAWLER_CONCURRENCY", "200"))
    request_timeout_s = int(os.getenv("REQUEST_TIMEOUT_S", "20"))
    crawl_delay_default_s = int(os.getenv("CRAWL_DELAY_DEFAULT_S", "5"))
    embeddings_provider = os.getenv("EMBEDDINGS_PROVIDER", "dummy")
    embeddings_dim = int(os.getenv("EMBEDDINGS_DIM", "384"))
    metrics_port = int(os.getenv("METRICS_PORT", "9100"))
    api_port = int(os.getenv("API_PORT", "8080"))
