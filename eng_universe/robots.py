import time
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import aiohttp
import redis.asyncio as redis

from eng_universe.config import Settings


@dataclass
class RobotsRules:
    domain: str
    crawl_delay_s: int
    allowed: bool
    fetched_at: int
    text: str


def robots_cache_key(domain: str) -> str:
    return f"{Settings.robots_key_prefix}{domain}"


def robots_next_allowed_key(domain: str) -> str:
    return f"{Settings.robots_next_allowed_prefix}{domain}"


def parse_domain(url: str) -> str:
    return urlparse(url).netloc


async def fetch_robots_txt(session: aiohttp.ClientSession, domain: str) -> str:
    robots_url = f"https://{domain}/robots.txt"
    async with session.get(robots_url, timeout=Settings.request_timeout_s) as response:
        if response.status >= 400:
            return ""
        return await response.text()


def parse_robots(robots_txt: str, domain: str, user_agent: str) -> RobotsRules:
    parser = RobotFileParser()
    parser.parse(robots_txt.splitlines())
    delay = parser.crawl_delay(user_agent) or Settings.crawl_delay_default_s
    allowed = parser.can_fetch(user_agent, f"https://{domain}/")
    return RobotsRules(
        domain=domain,
        crawl_delay_s=int(delay),
        allowed=allowed,
        fetched_at=int(time.time()),
        text=robots_txt,
    )


async def get_or_fetch_robots(
    redis_client: redis.Redis, session: aiohttp.ClientSession, domain: str
) -> RobotsRules:
    cached = await redis_client.hgetall(robots_cache_key(domain))
    if cached:
        return RobotsRules(
            domain=domain,
            crawl_delay_s=int(cached.get(b"crawl_delay_s", b"0")),
            allowed=cached.get(b"allowed", b"1") == b"1",
            fetched_at=int(cached.get(b"fetched_at", b"0")),
            text=cached.get(b"text", b"").decode(),
        )
    robots_txt = await fetch_robots_txt(session, domain)
    rules = parse_robots(robots_txt, domain, Settings.user_agent)
    await redis_client.hset(
        robots_cache_key(domain),
        mapping={
            "crawl_delay_s": rules.crawl_delay_s,
            "allowed": 1 if rules.allowed else 0,
            "fetched_at": rules.fetched_at,
            "text": rules.text,
        },
    )
    return rules


async def get_next_allowed(redis_client: redis.Redis, domain: str) -> int:
    value = await redis_client.get(robots_next_allowed_key(domain))
    if value is None:
        return 0
    return int(value)


async def update_next_allowed(
    redis_client: redis.Redis, domain: str, delay_s: int
) -> None:
    next_allowed = int(time.time()) + delay_s
    await redis_client.set(robots_next_allowed_key(domain), next_allowed)
