import re


DEFAULT_TOPICS = [
    "Kafka",
    "Flink",
    "Spark",
    "Redis",
    "Kubernetes",
    "Ray",
    "TensorFlow",
    "PyTorch",
    "GraphQL",
    "React",
    "Rust",
]


def extract_topics(text: str, topics: list[str] | None = None) -> list[str]:
    if topics is None:
        topics = DEFAULT_TOPICS
    found = []
    for topic in topics:
        if re.search(rf"\\b{re.escape(topic)}\\b", text, re.IGNORECASE):
            found.append(topic)
    return found
