import json, os, re, time
import httpx

class LLMUnavailable(Exception):
    """Raised with a human-readable reason (HTTP status + provider message) so it shows up in the audit log."""

def provider():
    p = os.getenv("LLM_PROVIDER", "auto").lower()
    if p == "auto":
        if os.getenv("ANTHROPIC_API_KEY"): return "anthropic"
        if os.getenv("OPENAI_API_KEY"): return "openai"
        return "mock"
    return p

def model_name():
    p = provider()
    if p == "anthropic": return os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    if p == "openai": return os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    return "none"

def _redact(text):
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        v = os.getenv(k)
        if v: text = text.replace(v, "***")
    return text

def _post(url, headers, body):
    try:
        return httpx.post(url, headers=headers, json=body, timeout=45)
    except httpx.HTTPError as e:
        raise LLMUnavailable(_redact(f"network error calling {url}: {type(e).__name__}: {e}"))

def _check(r):
    if r.status_code >= 400:
        raise LLMUnavailable(_redact(f"HTTP {r.status_code} from provider: {r.text[:250]}"))

def complete_json(system, user, max_tokens=2000):
    """max_tokens is generous because 'reasoning' models spend part of it thinking before answering."""
    p = provider()
    if p == "anthropic":
        if not os.getenv("ANTHROPIC_API_KEY"): raise LLMUnavailable("ANTHROPIC_API_KEY is empty")
        r = _post("https://api.anthropic.com/v1/messages",
            {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
            {"model": model_name(), "max_tokens": max_tokens, "temperature": 0, "system": system,
             "messages": [{"role": "user", "content": user}]})
        _check(r)
        text = r.json()["content"][0]["text"]
    elif p == "openai":
        if not os.getenv("OPENAI_API_KEY"): raise LLMUnavailable("OPENAI_API_KEY is empty")
        url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
        headers = {"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]}
        body = {"model": model_name(), "temperature": 0, "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        r = _post(url, headers, body)
        if r.status_code == 400 and "response_format" in r.text.lower():   # provider without JSON mode
            body.pop("response_format")
            r = _post(url, headers, body)
        _check(r)
        text = r.json()["choices"][0]["message"].get("content") or ""
    else:
        raise LLMUnavailable("no provider configured (mock mode)")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise LLMUnavailable("model returned no JSON (try a larger model or raise max_tokens): " + text[:120])
    try:
        out = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise LLMUnavailable(f"model returned invalid JSON: {e}")
    if not isinstance(out, dict):
        raise LLMUnavailable("model JSON was not an object")
    return out

_cache = {"t": 0, "v": None}

def check(force=False):
    """Tiny live probe used by /api/llm-check and the UI header. Cached for 30s."""
    if not force and _cache["v"] and time.time() - _cache["t"] < 30:
        return _cache["v"]
    info = {"provider": provider(), "model": model_name(), "ok": False, "error": None}
    if info["provider"] == "mock":
        info["error"] = "No API key configured; running in mock mode"
    else:
        try:
            complete_json('Reply with only this JSON: {"ok": true}', "ping", max_tokens=200)
            info["ok"] = True
        except Exception as e:
            info["error"] = str(e)[:300]
    _cache.update(t=time.time(), v=info)
    return info
