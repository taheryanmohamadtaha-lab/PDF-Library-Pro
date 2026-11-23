"""AI providers: Ollama (local) and OpenAI-compatible HTTP APIs. Standard library only."""
import json
import urllib.error
import urllib.request


class AIError(Exception):
    pass


def _post(url: str, payload: dict, headers: dict, timeout: int):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise AIError(f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}")
    except Exception as e:
        raise AIError(str(e))


def _get(url: str, headers: dict, timeout: int = 5):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        raise AIError(str(e))


class OllamaProvider:
    name = "ollama"
    sends_data_online = False

    def __init__(self, base_url="http://localhost:11434", model=""):
        self.base = base_url.rstrip("/")
        self.model = model

    def status(self) -> dict:
        try:
            models = [m["name"] for m in _get(self.base + "/api/tags", {}).get("models", [])]
            return {"ok": True, "models": models}
        except AIError as e:
            return {"ok": False, "error": str(e), "models": []}

    def chat(self, system: str, user: str, timeout=300) -> str:
        if not self.model:
            raise AIError("no model selected")
        data = _post(self.base + "/api/chat", {
            "model": self.model, "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": 0.2}}, {}, timeout)
        return data.get("message", {}).get("content", "").strip()


class OpenAICompatProvider:
    name = "api"
    sends_data_online = True

    def __init__(self, base_url: str, model: str, api_key: str, max_tokens: int = 1200):
        self.base = base_url.rstrip("/")
        self.model = model
        self.key = api_key
        self.max_tokens = max_tokens
        self.used_tokens = 0

    def status(self) -> dict:
        return {"ok": bool(self.key and self.base and self.model), "models": [self.model]}

    def chat(self, system: str, user: str, timeout=120) -> str:
        data = _post(self.base + "/chat/completions", {
            "model": self.model, "temperature": 0.2, "max_tokens": self.max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            {"Authorization": f"Bearer {self.key}"}, timeout)
        self.used_tokens += int(data.get("usage", {}).get("total_tokens", 0))
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError):
            raise AIError("unexpected response")
