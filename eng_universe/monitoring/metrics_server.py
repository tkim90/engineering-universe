import time

from prometheus_client import start_http_server

from eng_universe.config import Settings


def run_metrics_server() -> None:
    start_http_server(Settings.metrics_port)
    while True:
        time.sleep(1)
