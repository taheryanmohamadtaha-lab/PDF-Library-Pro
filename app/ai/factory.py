from ..database.central import CentralDB
from .providers import OllamaProvider, OpenAICompatProvider
from .secrets import load_key


def make_provider(central: CentralDB):
    mode = central.get("ai_mode", "none")
    if mode == "local":
        return OllamaProvider(central.get("ollama_url", "http://localhost:11434"), central.get("ollama_model", ""))
    if mode == "api":
        return OpenAICompatProvider(central.get("api_url", "https://api.openai.com/v1"),
                                    central.get("api_model", ""), load_key(),
                                    int(central.get("api_max_tokens", "1200")))
    return None
