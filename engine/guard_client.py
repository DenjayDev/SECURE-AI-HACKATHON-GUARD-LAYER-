import os, time, requests
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _config():
    url = os.environ.get("GUARD_URL", "").rstrip("/")
    token = os.environ.get("GUARD_TOKEN", "")
    if not url or not token:
        raise RuntimeError("Set GUARD_URL and GUARD_TOKEN (see .env.example)")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    return url, headers


def check(kind, text, retries=2):
    """Ask the Guard about one message.

    kind: "prompt" (user text, before the LLM) or "response" (LLM text, before the user).
    Always returns a dict with "ok" = True if the call worked. If "ok" is False,
    there is an "error" string, and the caller must decide what to do (we will fail closed).
    """
    url, headers = _config()
    for attempt in range(retries + 1):
        try:
            r = requests.post(f"{url}/v1/check/{kind}", headers=headers,
                              json={"text": text}, timeout=30)
        except requests.RequestException as e:
            return {"ok": False, "error": f"network error: {e}"}
        if r.status_code == 200:
            data = r.json()
            data["ok"] = True
            return data
        if r.status_code == 429 and attempt < retries:
            try:
                wait = int(float(r.headers.get("Retry-After", 5)))
            except ValueError:
                wait = 5
            time.sleep(wait + 1)
            continue
        return {"ok": False, "error": f"HTTP {r.status_code}: {r.text[:120]}"}
    return {"ok": False, "error": "gave up after retries"}
