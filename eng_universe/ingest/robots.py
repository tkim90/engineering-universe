import time
from dataclasses import dataclass
import math
import re
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import aiohttp
import redis.asyncio as redis

from eng_universe.config import Settings


@dataclass
class RobotsRules:
    domain: str
    crawl_delay_s: int
    request_rate_s: int
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


def _parse_request_rate_value(value: str) -> int:
    match = re.match(r"^\s*(\d+)\s*/\s*([\d.]+)\s*([smhd])?\s*$", value)
    if not match:
        return 0
    requests = int(match.group(1))
    if requests <= 0:
        return 0
    window = float(match.group(2))
    unit = match.group(3) or "s"
    multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400}.get(unit, 1)
    window_s = window * multiplier
    if window_s <= 0:
        return 0
    return int(math.ceil(window_s / requests))


def _extract_request_rate(robots_txt: str, user_agent: str) -> int:
    user_agent = user_agent.lower()
    groups: list[tuple[list[str], list[str]]] = []
    agents: list[str] = []
    directives: list[str] = []
    seen_directive = False
    for raw_line in robots_txt.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.lower().startswith("user-agent:"):
            agent = line.split(":", 1)[1].strip().lower()
            if agents and seen_directive:
                groups.append((agents, directives))
                agents = []
                directives = []
                seen_directive = False
            agents.append(agent)
            continue
        if not agents:
            continue
        directives.append(line)
        seen_directive = True
    if agents:
        groups.append((agents, directives))

    exact_rate = 0
    wildcard_rate = 0
    for agents, directives in groups:
        applies_exact = user_agent in agents
        applies_wildcard = "*" in agents
        if not applies_exact and not applies_wildcard:
            continue
        for directive in directives:
            if not directive.lower().startswith("request-rate:"):
                continue
            value = directive.split(":", 1)[1].strip()
            rate_s = _parse_request_rate_value(value)
            if applies_exact and rate_s:
                exact_rate = rate_s
            elif applies_wildcard and rate_s and wildcard_rate == 0:
                wildcard_rate = rate_s
    return exact_rate or wildcard_rate


def parse_robots(robots_txt: str, domain: str, user_agent: str) -> RobotsRules:
    parser = RobotFileParser()
    parser.parse(robots_txt.splitlines())
    delay = parser.crawl_delay(user_agent) or Settings.crawl_delay_default_s
    allowed = parser.can_fetch(user_agent, f"https://{domain}/")
    request_rate_s = _extract_request_rate(robots_txt, user_agent)
    return RobotsRules(
        domain=domain,
        crawl_delay_s=int(delay),
        request_rate_s=int(request_rate_s),
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
            request_rate_s=int(cached.get(b"request_rate_s", b"0")),
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
            "request_rate_s": rules.request_rate_s,
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


async def reserve_next_allowed(
    redis_client: redis.Redis, domain: str, delay_s: int
) -> tuple[bool, int]:
    now = int(time.time())
    key = robots_next_allowed_key(domain)
    script = """
    local now = tonumber(ARGV[1])
    local delay = tonumber(ARGV[2])
    local current = tonumber(redis.call("GET", KEYS[1]) or "0")
    if current <= now then
        local next_allowed = now + delay
        redis.call("SET", KEYS[1], next_allowed)
        return {1, next_allowed}
    end
    return {0, current}
    """
    allowed, next_allowed = await redis_client.eval(script, 1, key, now, delay_s)
    return bool(int(allowed)), int(next_allowed)
