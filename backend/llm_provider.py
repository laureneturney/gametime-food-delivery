"""
LLM provider abstraction for the GameTime agent.

Supports three back-ends, selected via the LLM_PROVIDER env var:

    LLM_PROVIDER=mock     # offline deterministic stub (default for demos)
    LLM_PROVIDER=watsonx  # IBM watsonx.ai foundation models
    LLM_PROVIDER=custom   # any OpenAI-compatible /v1/chat/completions endpoint
                          # (vLLM, Ollama with --openai, LM Studio, OpenAI itself, ...)

Every provider exposes the same `.complete(prompt, system=..., **kwargs)` method
that returns a plain string, so the agent code stays provider-agnostic.

The frontend ALWAYS displays the provider name as "IBM WatsonX" regardless of
which backend is actually wired up — see `DISPLAY_PROVIDER_NAME`.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # python-dotenv is optional; environment variables can be set externally too.
    pass


# The UI is required to always show this regardless of backend. Do not change.
DISPLAY_PROVIDER_NAME = "IBM WatsonX"


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class LLMProvider:
    """Tiny common interface so the agent doesn't care which backend is live."""

    name: str = "base"

    def complete(self, prompt: str, system: Optional[str] = None, **kwargs: Any) -> str:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Mock provider
# ---------------------------------------------------------------------------

class MockProvider(LLMProvider):
    """
    Deterministic, offline provider for demos and CI.

    It looks for the structured ANALYSIS JSON the agent embeds in the prompt
    and produces a templated, human-readable recommendation paragraph. This
    keeps the demo working with zero external dependencies.
    """

    name = "mock"

    _INTENSITY_BLURB = {
        "low":       "Lines are short right now — this is one of the best windows of the game to order.",
        "medium":    "Lines are picking up but still manageable.",
        "high":      "We're approaching a peak crowd surge; expect noticeable waits.",
        "very_high": "It's halftime / peak rush — wait times are roughly 4× the calm-period baseline.",
    }

    def complete(self, prompt: str, system: Optional[str] = None, **kwargs: Any) -> str:
        analysis = _extract_analysis_payload(prompt)
        if not analysis:
            return ("Recommendation unavailable: could not parse analysis context. "
                    "Configure WATSONX_APIKEY/WATSONX_PROJECT_ID or set "
                    "LLM_PROVIDER=custom for a live model.")

        intensity = analysis.get("lag_intensity", "low")
        item = analysis.get("recommended_item", {})
        conc = analysis.get("recommended_concession", {})
        timing = analysis.get("timing", {})
        method = analysis.get("delivery_method", "delivery")
        minute = analysis.get("game_time_minute", 0)

        blurb = self._INTENSITY_BLURB.get(intensity, "")
        method_phrase = (
            "delivered straight to your seat — you won't miss a play"
            if method == "delivery"
            else f"ready for pickup at {conc.get('name', 'the nearest stand')} (a quick walk from your seat)"
        )

        lines = [
            f"You're at minute {minute:.0f} of the game with **{intensity.replace('_', ' ')}** lag.",
            blurb,
            "",
            f"**Recommendation:** {item.get('name', 'a quick item')} from "
            f"{conc.get('name', 'the nearest concession')} ({conc.get('floor', '?')} level).",
            f"Estimated total time: ~{timing.get('total_time_minutes', '?')} minutes "
            f"(line {timing.get('current_line_wait', '?')}m + prep {timing.get('estimated_prep_time', '?')}m"
            f" + travel {timing.get('estimated_delivery_overhead', '?')}m).",
            f"Time you'd spend away from the game: ~{timing.get('time_away_from_game_minutes', 0)} minutes.",
            "",
            f"It will be {method_phrase}.",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# OpenAI-compatible provider (custom / open-source)
# ---------------------------------------------------------------------------

class OpenAICompatibleProvider(LLMProvider):
    """
    Talks to any /v1/chat/completions endpoint that follows the OpenAI schema.
    Works with vLLM, Ollama (via `ollama serve --openai`), LM Studio, OpenAI, etc.
    """

    name = "custom"

    def __init__(self,
                 base_url: str,
                 api_key: str,
                 model: str,
                 timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def complete(self, prompt: str, system: Optional[str] = None, **kwargs: Any) -> str:
        import httpx  # local import so mock-only installs don't need httpx-tls

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.4),
            "max_tokens": kwargs.get("max_tokens", 600),
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_key.lower() not in ("", "not-needed", "none"):
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = f"{self.base_url}/chat/completions"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Unexpected response shape from {url}: {data!r}") from exc


# ---------------------------------------------------------------------------
# IBM watsonx.ai provider
# ---------------------------------------------------------------------------

class WatsonxProvider(LLMProvider):
    """
    IBM watsonx.ai text-generation provider.

    Uses the foundation_models.Model interface from the official ibm-watsonx-ai
    SDK. Requires:
        WATSONX_APIKEY
        WATSONX_URL          (default https://us-south.ml.cloud.ibm.com)
        WATSONX_PROJECT_ID
        WATSONX_MODEL_ID     (default ibm/granite-3-8b-instruct)
    """

    name = "watsonx"

    def __init__(self,
                 api_key: str,
                 url: str,
                 project_id: str,
                 model_id: str):
        # Imported lazily so users running mock/custom don't need the SDK installed.
        from ibm_watsonx_ai import Credentials  # type: ignore
        from ibm_watsonx_ai.foundation_models import ModelInference  # type: ignore
        from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as P  # type: ignore

        self._P = P
        self.model_id = model_id
        self.project_id = project_id
        self.credentials = Credentials(url=url, api_key=api_key)
        self.model = ModelInference(
            model_id=model_id,
            credentials=self.credentials,
            project_id=project_id,
        )

    def complete(self, prompt: str, system: Optional[str] = None, **kwargs: Any) -> str:
        full_prompt = f"{system.strip()}\n\n{prompt.strip()}" if system else prompt
        params = {
            self._P.DECODING_METHOD: "greedy",
            self._P.MAX_NEW_TOKENS:  kwargs.get("max_tokens", 600),
            self._P.MIN_NEW_TOKENS:  1,
            self._P.TEMPERATURE:     kwargs.get("temperature", 0.4),
        }
        response = self.model.generate_text(prompt=full_prompt, params=params)
        if isinstance(response, dict):
            # Some SDK versions return the raw dict
            try:
                return response["results"][0]["generated_text"].strip()
            except (KeyError, IndexError):
                return json.dumps(response)
        return str(response).strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ANALYSIS_TAG = "<ANALYSIS_JSON>"
_ANALYSIS_END = "</ANALYSIS_JSON>"


def embed_analysis(payload: Dict[str, Any]) -> str:
    """Wrap a JSON payload in tags the mock provider can parse back out."""
    return f"{_ANALYSIS_TAG}\n{json.dumps(payload, default=str)}\n{_ANALYSIS_END}"


def _extract_analysis_payload(prompt: str) -> Optional[Dict[str, Any]]:
    if _ANALYSIS_TAG not in prompt or _ANALYSIS_END not in prompt:
        return None
    start = prompt.index(_ANALYSIS_TAG) + len(_ANALYSIS_TAG)
    end = prompt.index(_ANALYSIS_END)
    blob = prompt[start:end].strip()
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_provider_singleton: Optional[LLMProvider] = None


def get_llm_provider(force_reload: bool = False) -> LLMProvider:
    """Return the configured LLM provider (singleton)."""
    global _provider_singleton
    if _provider_singleton is not None and not force_reload:
        return _provider_singleton

    choice = os.getenv("LLM_PROVIDER", "mock").strip().lower()

    if choice == "watsonx":
        api_key = os.getenv("WATSONX_APIKEY", "").strip()
        project_id = os.getenv("WATSONX_PROJECT_ID", "").strip()
        url = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com").strip()
        model_id = os.getenv("WATSONX_MODEL_ID", "ibm/granite-3-8b-instruct").strip()
        if not api_key or not project_id:
            print("[llm_provider] WATSONX_APIKEY / WATSONX_PROJECT_ID missing — falling back to mock.")
            _provider_singleton = MockProvider()
        else:
            try:
                _provider_singleton = WatsonxProvider(api_key, url, project_id, model_id)
            except Exception as exc:
                print(f"[llm_provider] watsonx init failed ({exc}); falling back to mock.")
                _provider_singleton = MockProvider()

    elif choice == "custom":
        base_url = os.getenv("CUSTOM_LLM_BASE_URL", "http://localhost:8080/v1").strip()
        api_key = os.getenv("CUSTOM_LLM_API_KEY", "not-needed").strip()
        model = os.getenv("CUSTOM_LLM_MODEL", "llama-3.1-8b-instruct").strip()
        _provider_singleton = OpenAICompatibleProvider(base_url, api_key, model)

    else:
        if choice not in ("mock", ""):
            print(f"[llm_provider] Unknown LLM_PROVIDER={choice!r}; using mock.")
        _provider_singleton = MockProvider()

    return _provider_singleton


def get_provider_name() -> str:
    """The name shown in the UI. Always 'IBM WatsonX' per project requirements."""
    return DISPLAY_PROVIDER_NAME


def get_actual_backend_name() -> str:
    """Real underlying backend (debug only — not shown in the UI)."""
    return get_llm_provider().name


if __name__ == "__main__":
    p = get_llm_provider()
    sample_payload = {
        "game_time_minute": 15,
        "lag_intensity": "low",
        "delivery_method": "delivery",
        "recommended_item": {"name": "Soft Pretzel"},
        "recommended_concession": {"name": "Grand Slam Grill", "floor": "lower"},
        "timing": {
            "current_line_wait": 3,
            "estimated_prep_time": 2,
            "estimated_delivery_overhead": 4,
            "total_time_minutes": 9,
            "time_away_from_game_minutes": 0,
        },
    }
    out = p.complete(
        prompt=embed_analysis(sample_payload) + "\n\nWrite a 4-sentence recommendation.",
        system="You are a concise concierge for a sports stadium food-ordering app.",
    )
    print(f"Backend: {p.name}  (UI label: {get_provider_name()})\n---\n{out}")
