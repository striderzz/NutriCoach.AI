"""
LLM provider layer — one place that turns settings into a chat model.

Two tiers per provider: "small" for the narrating agents (BMI, Nutrition,
Meal, Activity) and "large" for the judges (Critics, Coach). Every number in
NutriCoach is computed in code, so even a small local model gives a correct
plan; the model only writes the words.

Provider SDKs are imported lazily so a missing package only breaks that
provider, not the app.
"""
import json
import urllib.request

# Model ids change often: users can also type any custom id in Settings.
PROVIDERS = {
    "openai": {
        "label": "OpenAI", "key": True,
        "small": "gpt-4.1-mini", "large": "gpt-4.1",
        "models": ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini", "gpt-4o", "gpt-5-mini", "gpt-5"],
    },
    "anthropic": {
        "label": "Anthropic (Claude)", "key": True,
        "small": "claude-haiku-5-5", "large": "claude-sonnet-5-5",
        "models": ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"],
    },
    "google": {
        "label": "Google (Gemini)", "key": True,
        "small": "gemini-2.5-flash", "large": "gemini-2.5-pro",
        "models": ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"],
    },
    "deepseek": {
        "label": "DeepSeek", "key": True, "base_url": "https://api.deepseek.com",
        "small": "deepseek-chat", "large": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "ollama": {
        "label": "Local LLM (Ollama, free)", "key": False,
        "small": "llama3.2:3b", "large": "qwen2.5:7b",
        "models": [],                         # filled from the local Ollama install
    },
    "offline": {
        "label": "No AI (rule-based only)", "key": False,
        "small": "", "large": "", "models": [],
    },
}

# Smallest first, so people with little RAM pick from the top.
LOCAL_MODELS = [
    {"name": "qwen2.5:1.5b", "gb": 1.0, "ram_gb": 4,  "note": "Tiny, fast; fine for narrating plans"},
    {"name": "llama3.2:1b",  "gb": 1.3, "ram_gb": 4,  "note": "Tiny Meta model"},
    {"name": "llama3.2:3b",  "gb": 2.0, "ram_gb": 8,  "note": "Recommended small tier, supports tools"},
    {"name": "qwen2.5:3b",   "gb": 1.9, "ram_gb": 8,  "note": "Good tool calling for its size"},
    {"name": "qwen2.5:7b",   "gb": 4.7, "ram_gb": 16, "note": "Recommended large tier"},
    {"name": "llama3.1:8b",  "gb": 4.9, "ram_gb": 16, "note": "Strong general model"},
]
OLLAMA_INSTALL = "https://ollama.com/download"
OLLAMA_URL = "http://localhost:11434"


def installed_ollama_models(base_url: str = OLLAMA_URL) -> list[str] | None:
    """Model names pulled in the local Ollama, or None if Ollama isn't running."""
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=2) as r:
            return [m["name"] for m in json.load(r).get("models", [])]
    except Exception:
        return None


def model_name(cfg: dict, tier: str) -> str:
    p = cfg.get("provider", "openai")
    return (cfg.get(f"model_{tier}") or PROVIDERS[p][tier]).strip()


def make_model(cfg: dict, tier: str = "small"):
    """Chat model for the configured provider and tier, or None for rule-based mode."""
    p = cfg.get("provider", "openai")
    if p == "offline" or p not in PROVIDERS:
        return None
    name = model_name(cfg, tier)
    key = (cfg.get("keys") or {}).get(p, "").strip()
    if PROVIDERS[p]["key"] and not key:
        raise ValueError(f"Add your {PROVIDERS[p]['label']} API key in Settings, "
                         "or pick Local LLM / No AI.")
    # Keys go to each client directly, never os.environ, so they can't leak between runs
    common = {"temperature": 0.3}
    if p in ("openai", "deepseek"):
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=name, api_key=key, base_url=PROVIDERS[p].get("base_url"),
                          max_retries=2, timeout=90, **common)
    if p == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=name, api_key=key, max_tokens=4096,
                             max_retries=2, timeout=90, **common)
    if p == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=name, google_api_key=key, max_retries=2, **common)
    from langchain_ollama import ChatOllama
    return ChatOllama(model=name, base_url=cfg.get("ollama_url") or OLLAMA_URL, **common)
