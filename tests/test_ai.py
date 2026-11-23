import json, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import pytest
from conftest import make_pdf
from app.ai import rag
from app.ai.providers import OllamaProvider, OpenAICompatProvider

SEEN = []


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._send({"models": [{"name": "fake:1b"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append((self.path, self.headers.get("Authorization"), body))
        content = "Answer (p.1)"
        if self.path.endswith("/api/chat"):
            self._send({"message": {"content": content}})
        else:
            self._send({"choices": [{"message": {"content": content}}], "usage": {"total_tokens": 42}})


@pytest.fixture
def server():
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def setup_book(mgr, tmp_path):
    lid = mgr.default_id()
    s = mgr.service(lid)
    _, bid = s.add_pdf(make_pdf(tmp_path / "q.pdf", ("Photosynthesis converts light into energy", "Mitochondria produce ATP")))
    s.index_book(bid)
    return lid, bid, {lid: s}


def test_ollama_and_rag_with_pages(mgr, tmp_path, server):
    lid, bid, svcs = setup_book(mgr, tmp_path)
    p = OllamaProvider(server, "fake:1b")
    assert p.status() == {"ok": True, "models": ["fake:1b"]}
    ans = rag.ask(p, svcs, [(lid, bid)], "What do mitochondria produce?")
    assert ans.found and ans.text and any(pg == 2 for _, pg, _ in ans.sources)
    sent = SEEN[-1][2]["messages"][1]["content"]
    assert "Mitochondria" in sent and "p.2" in sent


def test_not_in_pdf_never_calls_model(mgr, tmp_path, server):
    lid, bid, svcs = setup_book(mgr, tmp_path)
    n = len(SEEN)
    ans = rag.ask(OllamaProvider(server, "m"), svcs, [(lid, bid)], "quantum chromodynamics gluons")
    assert not ans.found and len(SEEN) == n


def test_api_provider_and_tasks(mgr, tmp_path, server):
    lid, bid, svcs = setup_book(mgr, tmp_path)
    p = OpenAICompatProvider(server, "gpt-x", "KEY123")
    a = rag.run_task(p, svcs, [(lid, bid)], "summary")
    assert a.found and p.used_tokens >= 42
    assert SEEN[-1][1] == "Bearer KEY123"
    assert rag.parse_json('xx [{"q":"a"}] yy') == [{"q": "a"}]


def test_secret_roundtrip(home):
    from app.ai.secrets import save_key, load_key
    save_key("sk-test"); assert load_key() == "sk-test"
    save_key(""); assert load_key() == ""
