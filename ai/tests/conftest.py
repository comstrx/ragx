from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, override
import json, threading
import pytest

type Handler = Callable[[str, str, dict[str, Any]], tuple[int, bytes, dict[str, str]]]

@pytest.fixture
def anyio_backend () -> str:

    return "asyncio"

@pytest.fixture
def serve () -> Iterator[Callable[[Handler], str]]:

    servers: list[ThreadingHTTPServer] = []
    threads: list[threading.Thread] = []

    def start ( callback: Handler ) -> str:

        class Request(BaseHTTPRequestHandler):

            @override
            def log_message ( self, format: str, *args: object ) -> None:

                pass

            def handle_request ( self ) -> None:

                size = int(self.headers.get("content-length", "0"))
                body = json.loads(self.rfile.read(size)) if size else {}
                status, data, headers = callback(self.command, self.path, body)
                self.send_response(status)
                for key, value in headers.items(): self.send_header(key, value)
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET ( self ) -> None:

                self.handle_request()

            def do_POST ( self ) -> None:

                self.handle_request()

        server = ThreadingHTTPServer(("127.0.0.1", 0), Request)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        servers.append(server)
        threads.append(worker)
        return f"http://127.0.0.1:{server.server_port}"

    yield start

    for server in servers:
        server.shutdown()
        server.server_close()
    for worker in threads: worker.join()

def pytest_addoption ( parser: pytest.Parser ) -> None:

    parser.addoption("--live", action="store_true", default=False)

def pytest_collection_modifyitems ( config: pytest.Config, items: list[pytest.Item] ) -> None:

    if config.getoption("--live"): return
    for item in items:
        if "live" in item.keywords:
            item.add_marker(pytest.mark.skip(reason="Pass --live to execute pinned native models"))
