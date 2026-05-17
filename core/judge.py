"""LLM-as-Judge — provider-agnostic evaluation engine.

Supported providers:
  - Anthropic  (direct API key)
  - OpenAI     (direct API key)
  - Amazon Bedrock (AWS credentials, uses Converse API)
  - Azure OpenAI   (endpoint + key + deployment)
"""
from __future__ import annotations
from typing import Optional
import json
import re


# ── Prompt ────────────────────────────────────────────────────────────────────

JUDGE_SYSTEM = """You are a rigorous evaluation judge for AI agent outputs.
You will be given:
  - A user query the agent received
  - The agent's response
  - A single evaluation criterion with a scoring rubric

Your task:
1. Reason step-by-step about how the response meets or fails the criterion.
2. Assign a score from the rubric.
3. Return ONLY valid JSON in the exact format below — no markdown, no extra text.

{"score": <integer>, "explanation": "<one concise sentence>"}"""


def build_prompt(query: str, response: str, criterion: dict) -> str:
    scale_text = "\n".join(
        f"  {k}: {v}"
        for k, v in sorted(criterion["scale"].items(), key=lambda x: int(x[0]))
    )
    return (
        f"## Criterion: {criterion['name']}\n"
        f"{criterion['definition']}\n\n"
        f"## Scoring rubric\n{scale_text}\n\n"
        f"## Observable signal\n{criterion.get('signal', 'N/A')}\n\n"
        f"## Agent query\n{query}\n\n"
        f"## Agent response\n{response}\n\n"
        "Return JSON only."
    )


def _parse(raw: str) -> dict:
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if not m:
        raise ValueError(f"No JSON found in model output: {raw[:200]}")
    parsed = json.loads(m.group())
    return {"score": int(parsed["score"]), "explanation": parsed.get("explanation", "")}


# ── Provider base ─────────────────────────────────────────────────────────────

class LLMProvider:
    """Abstract provider — subclasses implement complete()."""
    label: str = "unknown"

    def complete(self, system: str, user: str) -> str:
        raise NotImplementedError

    def score_trace(self, query: str, response: str, criterion: dict) -> dict:
        raw = self.complete(JUDGE_SYSTEM, build_prompt(query, response, criterion))
        return _parse(raw)


# ── Anthropic ─────────────────────────────────────────────────────────────────

class AnthropicProvider(LLMProvider):
    label = "Anthropic"

    MODELS = [
        "claude-sonnet-4-6",
        "claude-opus-4-7",
        "claude-haiku-4-5-20251001",
    ]

    def __init__(self, api_key: str, model: str):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model  = model

    def complete(self, system: str, user: str) -> str:
        msg = self.client.messages.create(
            model=self.model, max_tokens=256,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text.strip()


# ── OpenAI ────────────────────────────────────────────────────────────────────

class OpenAIProvider(LLMProvider):
    label = "OpenAI"

    MODELS = [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-3.5-turbo",
    ]

    def __init__(self, api_key: str, model: str):
        import openai
        self.client = openai.OpenAI(api_key=api_key)
        self.model  = model

    def complete(self, system: str, user: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.model, max_tokens=256,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        )
        return resp.choices[0].message.content.strip()


# ── Amazon Bedrock ────────────────────────────────────────────────────────────

class BedrockProvider(LLMProvider):
    label = "Amazon Bedrock"

    MODELS = [
        "anthropic.claude-sonnet-4-5",
        "anthropic.claude-3-5-haiku-20241022-v1:0",
        "anthropic.claude-3-opus-20240229-v1:0",
        "amazon.nova-pro-v1:0",
        "amazon.nova-lite-v1:0",
        "meta.llama3-70b-instruct-v1:0",
        "mistral.mistral-large-2402-v1:0",
    ]

    def __init__(self, aws_access_key: str, aws_secret_key: str,
                 aws_region: str, model: str, aws_session_token: str = ""):
        import boto3
        kwargs = dict(
            service_name="bedrock-runtime",
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=aws_region,
        )
        if aws_session_token:
            kwargs["aws_session_token"] = aws_session_token
        self.client = boto3.client(**kwargs)
        self.model  = model

    def complete(self, system: str, user: str) -> str:
        # Bedrock Converse API — works for all supported models
        resp = self.client.converse(
            modelId=self.model,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={"maxTokens": 256},
        )
        return resp["output"]["message"]["content"][0]["text"].strip()


# ── Azure OpenAI ──────────────────────────────────────────────────────────────

class AzureOpenAIProvider(LLMProvider):
    label = "Azure OpenAI"

    def __init__(self, api_key: str, endpoint: str,
                 deployment: str, api_version: str = "2024-02-01"):
        import openai
        self.client     = openai.AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )
        self.deployment = deployment

    def complete(self, system: str, user: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.deployment, max_tokens=256,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        )
        return resp.choices[0].message.content.strip()


# ── Factory ───────────────────────────────────────────────────────────────────

PROVIDERS = ["Anthropic", "OpenAI", "Amazon Bedrock", "Azure OpenAI"]


def make_provider(name: str, cfg: dict) -> LLMProvider:
    """Build a provider from a config dict. Raises on missing keys."""
    if name == "Anthropic":
        return AnthropicProvider(cfg["api_key"], cfg["model"])
    if name == "OpenAI":
        return OpenAIProvider(cfg["api_key"], cfg["model"])
    if name == "Amazon Bedrock":
        return BedrockProvider(
            cfg["aws_access_key"], cfg["aws_secret_key"],
            cfg["aws_region"], cfg["model"],
            cfg.get("aws_session_token", ""),
        )
    if name == "Azure OpenAI":
        return AzureOpenAIProvider(
            cfg["api_key"], cfg["endpoint"],
            cfg["deployment"], cfg.get("api_version", "2024-02-01"),
        )
    raise ValueError(f"Unknown provider: {name}")


def provider_model_id(provider_name: str, model: str) -> str:
    """Stable string stored in judge_scores.model column."""
    return f"{provider_name}/{model}"


# ── Calibration ───────────────────────────────────────────────────────────────

def calibration_kappa(human_scores: list, judge_scores: list) -> Optional[float]:
    from sklearn.metrics import cohen_kappa_score
    if len(human_scores) < 2:
        return None
    try:
        return float(cohen_kappa_score(human_scores, judge_scores))
    except Exception:
        return None
