"""Small, guarded wrapper around Gemini. Never raises, never in the pass/fail logic.

Used only for wording: a plain-English line about a route, or a readable summary of a refresh report. Rules:
* Only aggregate facts go in (a whitelist, below). Never coordinates, addresses or anything about a user:
  on the free tier Google may use and human-review what you send (https://ai.google.dev/gemini-api/terms).
* The reply is checked before use: every number must appear in the facts we sent, written as digits (number
  words like "two" are rejected). If the check fails, or Gemini is off, slow or errors, the caller's own
  fallback text is returned instead, so a route or report never depends on the model.
* Calls are cached in memory and time-limited. Don't call this inside a request that must be fast.

Setup: GEMINI_API_KEY in the gitignored .env, `pip install google-genai`. Model: gemini-3.5-flash-lite
(about 1 s). The default flash model on this key is a slow "thinking" model (about a minute per call), so it
isn't used; override with GEMINI_MODEL. Disable everything with LLM_DISABLED=1 (tests do).
"""
import concurrent.futures
import hashlib
import os
import re
import threading

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
TIMEOUT_S = 15.0
MAX_CACHE = 256
# the only facts allowed to leave the machine
ALLOWED_FACTS = {"minutes_added", "risk_reduction_pct", "hazards_avoided", "closures_avoided", "weather",
                 "avoid_note", "profile", "same_route"}
NUMBER_WORDS = re.compile(r"\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
                          r"fifteen|twenty|thirty|forty|fifty|hundred|half|dozen)\b", re.I)
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")

_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
_lock = threading.Lock()
_cache: dict = {}


def enabled() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY")) and not os.environ.get("LLM_DISABLED")


_client_holder: dict = {}


def _client():
    """One long-lived client. A temporary `genai.Client()` is garbage-collected, which closes its HTTP
    connection before the request is sent ("client has been closed"), so it must be kept referenced."""
    with _lock:
        if "client" not in _client_holder:
            from google import genai  # lazy: the rest of the backend never needs the SDK
            _client_holder["client"] = genai.Client()
        return _client_holder["client"]


def _call(prompt: str) -> str:
    """The one place that talks to Gemini (patched in tests)."""
    out = _client().interactions.create(model=MODEL, input=prompt)
    return out.output_text.strip()


def numbers_in(text: str) -> set[str]:
    return {n.replace(",", "") for n in NUMBER.findall(text)}


def grounded(reply: str, source: str) -> bool:
    """True when every number in `reply` appears in `source` and no number is spelled out as a word."""
    if not reply or NUMBER_WORDS.search(reply):
        return False
    return numbers_in(reply) <= numbers_in(source)


def generate(prompt: str, source: str | None = None) -> str | None:
    """Gemini's reply to `prompt`, or None (disabled, timed out, errored, or failed the number check).

    `source` is the text whose numbers the reply may use; defaults to the prompt itself.
    """
    if not enabled():
        return None
    key = hashlib.sha256(prompt.encode()).hexdigest()
    with _lock:
        if key in _cache:
            return _cache[key]
    try:
        reply = _pool.submit(_call, prompt).result(timeout=TIMEOUT_S)
    except Exception as e:  # timeout, network, quota, bad key, SDK change: just no LLM text
        print(f"llm: Gemini unavailable ({type(e).__name__})")
        return None
    if not grounded(reply, source if source is not None else prompt):
        print("llm: reply rejected (number not in the facts, or a number spelled as a word)")
        reply = None
    with _lock:
        if len(_cache) >= MAX_CACHE:
            _cache.pop(next(iter(_cache)))
        _cache[key] = reply
    return reply


LABELS = {  # explicit labels so the model can't confuse context (weather) with things the route avoids
    "minutes_added": "Extra driving time of the safer route, in minutes",
    "risk_reduction_pct": "Percent less crash risk on the safer route",
    "hazards_avoided": "Hazards the safer route avoids (the fastest route has them)",
    "closures_avoided": "Number of routes skipped because they pass through road closures",
    "weather": "Current weather (background context only; the route does not avoid it)",
    "avoid_note": "Note about the driver's avoid-tolls/highways choice",
    "profile": "Driver profile",
    "same_route": "The fastest route is already the safest",
}


def _facts_text(facts: dict) -> str:
    lines = []
    for k in sorted(facts):
        v = facts[k]
        lines.append(f"- {LABELS.get(k, k)}: {', '.join(map(str, v)) if isinstance(v, (list, tuple)) else v}")
    return "\n".join(lines)


def explain_route(facts: dict, fallback: str) -> str:
    """One plain sentence about the route choice, or `fallback`. Only whitelisted aggregate facts are sent."""
    facts = {k: v for k, v in facts.items() if k in ALLOWED_FACTS and v not in (None, "", [], 0)}
    if not facts or not enabled():
        return fallback
    text = _facts_text(facts)
    prompt = ("Write ONE plain sentence (under 30 words) telling a driver why the app chose this route. "
              "Use only the facts below. Write every number as digits. Do not add any fact, number, road name or advice.\n\n"
              f"Facts:\n{text}")
    return generate(prompt, source=text) or fallback


def summarize_report(markdown: str) -> str | None:
    """A short readable summary of a refresh report (for the pull request), or None."""
    if not enabled():
        return None
    prompt = ("Summarize this data-refresh report for a developer in 3 short bullet points: whether it was accepted, "
              "the main numbers, and anything needing attention. Use only numbers that appear in the report, "
              "written as digits. Do not invent anything.\n\n" + markdown)
    return generate(prompt, source=markdown)
