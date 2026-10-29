"""One interface over the language models UniTask can use.

LLM_PROVIDER=gemini   Google Gemini (AI Studio endpoint), key in GEMINI_API_KEY
LLM_PROVIDER=bedrock  Amazon Bedrock Converse API, model in BEDROCK_MODEL_ID
LLM_PROVIDER=none     no model: callers fall back to deterministic behaviour

The model never decides facts the app can compute (deadlines, feasibility, scores). It explains,
structures text and tutors. Every call is bounded: timeouts, at most two attempts, then LLMError.
"""

import base64
import json
import logging
import os
import re
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class LLMError(RuntimeError):
    pass


@dataclass
class Turn:
    role: str  # "user" | "model"
    text: str


def provider() -> str:
    configured = os.getenv("LLM_PROVIDER", "").strip().lower()
    if configured:
        return configured
    return "gemini" if os.getenv("GEMINI_API_KEY") else "none"


def _configured(name: str) -> bool:
    if name == "gemini":
        return bool(os.getenv("GEMINI_API_KEY"))
    if name == "bedrock":
        return bool(os.getenv("BEDROCK_MODEL_ID"))
    return False


def chain() -> list[str]:
    """The primary provider, then LLM_FALLBACK (e.g. bedrock first, gemini if Bedrock is unavailable)."""
    names = [provider(), os.getenv("LLM_FALLBACK", "").strip().lower()]
    return [n for i, n in enumerate(names) if n and n not in names[:i] and _configured(n)]


def available() -> bool:
    return bool(chain())


def _model(name: str, fast: bool = False) -> str:
    if name == "bedrock":
        return (os.getenv("BEDROCK_FAST_MODEL_ID") if fast else None) or os.getenv("BEDROCK_MODEL_ID", "")
    return os.getenv("LLM_FAST_MODEL" if fast else "LLM_MODEL", "gemini-flash-lite-latest" if fast else "gemini-3.5-flash")


def describe() -> dict:
    names = chain()
    if not names:
        return {"provider": "none", "model": None, "fast_model": None, "fallback": None}
    return {
        "provider": names[0],
        "model": _model(names[0]),
        "fast_model": _model(names[0], fast=True),
        "fallback": names[1] if len(names) > 1 else None,
        "last_used": _last_used.get("provider"),
    }


_last_used: dict[str, str] = {}


def _parse_json(text: str):
    text = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", text, re.S)
        if match:
            return json.loads(match.group(1))
        raise


def _gemini(system: str, turns: list[Turn], *, json_mode: bool, fast: bool, image: tuple[bytes, str] | None) -> str:
    key = os.getenv("GEMINI_API_KEY", "")
    primary = os.getenv("LLM_FAST_MODEL" if fast else "LLM_MODEL", "gemini-flash-lite-latest" if fast else "gemini-3.5-flash")
    fallback = os.getenv("LLM_FAST_MODEL", "gemini-flash-lite-latest")
    contents = []
    for index, turn in enumerate(turns):
        parts: list[dict] = [{"text": turn.text}]
        if image and index == len(turns) - 1:
            parts.append({"inline_data": {"mime_type": image[1], "data": base64.b64encode(image[0]).decode()}})
        contents.append({"role": "model" if turn.role == "model" else "user", "parts": parts})
    body: dict = {"contents": contents, "systemInstruction": {"parts": [{"text": system}]}}
    config: dict = {"temperature": 0.4}
    if json_mode:
        config["responseMimeType"] = "application/json"
    body["generationConfig"] = config

    last_error = "no attempt made"
    for attempt, model in enumerate([primary, fallback if fallback != primary else primary]):
        try:
            response = httpx.post(
                GEMINI_URL.format(model=model),
                headers={"x-goog-api-key": key},
                json=body,
                timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "45")),
            )
        except httpx.HTTPError as exc:
            last_error = f"{model}: {type(exc).__name__}"
            continue
        if response.status_code == 429 or response.status_code >= 500:
            last_error = f"{model}: HTTP {response.status_code}"
            time.sleep(1.5 * (attempt + 1))
            continue
        if response.status_code != 200:
            raise LLMError(f"Gemini rejected the request ({response.status_code}).")
        data = response.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(part.get("text", "") for part in parts if not part.get("thought"))
        except (KeyError, IndexError):
            last_error = f"{model}: empty response ({data.get('promptFeedback', {}).get('blockReason', 'no candidates')})"
    raise LLMError(f"The AI model did not respond ({last_error}).")


_bedrock_client = None


def _bedrock(system: str, turns: list[Turn], *, json_mode: bool, fast: bool, image: tuple[bytes, str] | None) -> str:
    import boto3
    from botocore.config import Config
    from botocore.exceptions import BotoCoreError, ClientError

    global _bedrock_client
    if _bedrock_client is None:
        region = os.getenv("BEDROCK_REGION") or os.getenv("AWS_REGION", "ap-south-1")
        profile = os.getenv("AWS_PROFILE") or None
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        _bedrock_client = session.client(
            "bedrock-runtime", region_name=region, config=Config(retries={"max_attempts": 2}, read_timeout=90, connect_timeout=10)
        )
    messages = []
    for index, turn in enumerate(turns):
        content: list[dict] = [{"text": turn.text}]
        if image and index == len(turns) - 1:
            fmt = image[1].split("/")[-1].replace("jpg", "jpeg")
            content.append({"image": {"format": fmt, "source": {"bytes": image[0]}}})
        messages.append({"role": "assistant" if turn.role == "model" else "user", "content": content})
    instruction = system + ("\nRespond with a single JSON object only, no prose and no code fences." if json_mode else "")
    try:
        response = _bedrock_client.converse(
            modelId=_model("bedrock", fast),
            system=[{"text": instruction}],
            messages=messages,
            inferenceConfig={"temperature": 0.4, "maxTokens": 4000},
        )
    except (BotoCoreError, ClientError) as exc:
        logger.warning("Bedrock call failed: %s", exc)
        raise LLMError("Amazon Bedrock did not respond.") from exc
    return "".join(block.get("text", "") for block in response["output"]["message"]["content"])


def _normalise(turns: list[Turn]) -> list[Turn]:
    """Start with the student and alternate roles, merging consecutive turns from the same side."""
    out: list[Turn] = []
    for turn in turns:
        role = "model" if turn.role == "model" else "user"
        if not out and role == "model":
            continue
        if out and out[-1].role == role:
            out[-1] = Turn(role, out[-1].text + "\n\n" + turn.text)
        else:
            out.append(Turn(role, turn.text))
    return out


def generate(
    system: str,
    turns: list[Turn] | str,
    *,
    json_mode: bool = False,
    fast: bool = False,
    image: tuple[bytes, str] | None = None,
):
    """Return text, or parsed JSON when json_mode=True. Tries LLM_PROVIDER, then LLM_FALLBACK.

    Raises LLMError when no configured model can answer.
    """
    if isinstance(turns, str):
        turns = [Turn("user", turns)]
    turns = _normalise(turns)
    names = chain()
    if not names:
        raise LLMError("No AI model is configured on this server.")
    errors = []
    for name in names:
        started = time.monotonic()
        try:
            if name == "gemini":
                text = _gemini(system, turns, json_mode=json_mode, fast=fast, image=image)
            elif name == "bedrock":
                text = _bedrock(system, turns, json_mode=json_mode, fast=fast, image=image)
            else:
                raise LLMError(f"Unknown LLM provider '{name}'.")
            if json_mode:
                try:
                    result = _parse_json(text)
                except (json.JSONDecodeError, ValueError) as exc:
                    raise LLMError("The AI model returned malformed structured output.") from exc
            else:
                result = text.strip()
        except LLMError as exc:
            logger.warning("llm provider=%s failed after %.1fs: %s", name, time.monotonic() - started, exc)
            errors.append(f"{name}: {exc}")
            continue
        _last_used["provider"] = name
        logger.info("llm call provider=%s fast=%s json=%s took=%.1fs", name, fast, json_mode, time.monotonic() - started)
        return result
    raise LLMError("; ".join(errors))
