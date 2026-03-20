"""
providers/base.py — LLM Provider Abstraction Layer
===================================================
Unified interface for all supported LLM providers.
Supports: Anthropic Claude, OpenAI GPT, DeepSeek, Gemini, Ollama (local)
"""

import json
import ssl
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from asyncio import get_event_loop
from dataclasses import dataclass
from functools import partial
from typing import AsyncIterator, List, Optional


@dataclass
class ChatMessage:
    role   : str    # "user" | "assistant" | "system"
    content: str

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class LLMResponse:
    content      : str
    model        : str   = ""
    input_tokens : int   = 0
    output_tokens: int   = 0
    provider     : str   = ""


class BaseLLMProvider(ABC):
    """Abstract base for all LLM providers."""

    @abstractmethod
    async def chat(
        self,
        messages     : List[ChatMessage],
        system_prompt: str = "",
        temperature  : float = 0.7,
        max_tokens   : int = 4096,
    ) -> LLMResponse:
        ...

    @abstractmethod
    async def stream(
        self,
        messages     : List[ChatMessage],
        system_prompt: str = "",
        temperature  : float = 0.7,
        max_tokens   : int = 4096,
    ) -> AsyncIterator[str]:
        ...

    def _run_sync(self, func, *args, **kwargs):
        loop = get_event_loop()
        return loop.run_in_executor(None, partial(func, *args, **kwargs))

    @staticmethod
    def _ssl():
        ctx = ssl.create_default_context()
        return ctx

    @staticmethod
    def _post(url: str, headers: dict, body: dict, timeout=120) -> dict:
        data = json.dumps(body).encode()
        req  = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout,
                                    context=BaseLLMProvider._ssl()) as r:
            return json.loads(r.read().decode())


# ═══════════════════════════════════════════════════════════════
#  Anthropic Claude Provider
# ═══════════════════════════════════════════════════════════════

class AnthropicProvider(BaseLLMProvider):
    """
    Anthropic Claude API provider.
    Models: claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5-20251001
    """

    API_URL     = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        self.api_key = api_key
        self.model   = model

    def _headers(self) -> dict:
        return {
            "x-api-key"        : self.api_key,
            "anthropic-version": self.API_VERSION,
            "content-type"     : "application/json",
        }

    def _build_body(self, messages, system_prompt, temperature, max_tokens, stream=False):
        body = {
            "model"      : self.model,
            "max_tokens" : max_tokens,
            "messages"   : [m.to_dict() for m in messages],
            "temperature": temperature,
            "stream"     : stream,
        }
        if system_prompt:
            body["system"] = system_prompt
        return body

    def _sync_chat(self, messages, system_prompt, temperature, max_tokens) -> LLMResponse:
        body = self._build_body(messages, system_prompt, temperature, max_tokens)
        data = self._post(self.API_URL, self._headers(), body)
        text = "".join(b.get("text","") for b in data.get("content",[])
                       if b.get("type") == "text")
        usage = data.get("usage", {})
        return LLMResponse(
            content=text, model=self.model, provider="anthropic",
            input_tokens=usage.get("input_tokens",0),
            output_tokens=usage.get("output_tokens",0),
        )

    async def chat(self, messages, system_prompt="", temperature=0.7, max_tokens=4096):
        return await self._run_sync(self._sync_chat, messages, system_prompt, temperature, max_tokens)

    def _sync_stream(self, messages, system_prompt, temperature, max_tokens):
        """Returns list of text chunks (sync streaming via chunked HTTP read)."""
        body = self._build_body(messages, system_prompt, temperature, max_tokens, stream=True)
        data = json.dumps(body).encode()
        req  = urllib.request.Request(self.API_URL, data=data,
                                      headers=self._headers(), method="POST")
        chunks = []
        resp = urllib.request.urlopen(req, timeout=180, context=self._ssl())
        buf  = b""
        while True:
            part = resp.read(512)
            if not part:
                break
            buf += part
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if not payload or payload == "[DONE]":
                    continue
                try:
                    ev = json.loads(payload)
                    if ev.get("type") == "content_block_delta":
                        d = ev.get("delta", {})
                        if d.get("type") == "text_delta":
                            chunks.append(d.get("text", ""))
                except Exception:
                    pass
        resp.close()
        return chunks

    async def stream(self, messages, system_prompt="", temperature=0.7, max_tokens=4096):
        chunks = await self._run_sync(self._sync_stream, messages, system_prompt, temperature, max_tokens)
        for chunk in chunks:
            yield chunk


# ═══════════════════════════════════════════════════════════════
#  OpenAI Provider (also works for DeepSeek, Qwen with base_url)
# ═══════════════════════════════════════════════════════════════

class OpenAIProvider(BaseLLMProvider):
    """
    OpenAI-compatible provider.
    Works with: OpenAI, DeepSeek, Qwen, any OpenAI-compatible API.
    """

    def __init__(self, api_key: str, model: str = "gpt-4o",
                 base_url: str = "https://api.openai.com"):
        self.api_key  = api_key
        self.model    = model
        self.base_url = base_url.rstrip("/")

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type" : "application/json",
        }

    def _build_messages(self, messages, system_prompt):
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.extend(m.to_dict() for m in messages)
        return msgs

    def _sync_chat(self, messages, system_prompt, temperature, max_tokens):
        body = {
            "model"      : self.model,
            "messages"   : self._build_messages(messages, system_prompt),
            "temperature": temperature,
            "max_tokens" : max_tokens,
        }
        data  = self._post(f"{self.base_url}/v1/chat/completions",
                           self._headers(), body)
        text  = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return LLMResponse(
            content=text, model=self.model, provider="openai",
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )

    async def chat(self, messages, system_prompt="", temperature=0.7, max_tokens=4096):
        return await self._run_sync(self._sync_chat, messages, system_prompt, temperature, max_tokens)

    def _sync_stream(self, messages, system_prompt, temperature, max_tokens):
        body = {
            "model": self.model,
            "messages": self._build_messages(messages, system_prompt),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        data = json.dumps(body).encode()
        req  = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=data, headers=self._headers(), method="POST"
        )
        chunks = []
        resp   = urllib.request.urlopen(req, timeout=180, context=self._ssl())
        buf    = b""
        while True:
            part = resp.read(512)
            if not part:
                break
            buf += part
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if not payload or payload == "[DONE]":
                    continue
                try:
                    ev = json.loads(payload)
                    delta = ev["choices"][0].get("delta", {})
                    if "content" in delta and delta["content"]:
                        chunks.append(delta["content"])
                except Exception:
                    pass
        resp.close()
        return chunks

    async def stream(self, messages, system_prompt="", temperature=0.7, max_tokens=4096):
        chunks = await self._run_sync(self._sync_stream, messages, system_prompt, temperature, max_tokens)
        for chunk in chunks:
            yield chunk


# ═══════════════════════════════════════════════════════════════
#  Mock Provider (for testing without API keys)
# ═══════════════════════════════════════════════════════════════

class MockProvider(BaseLLMProvider):
    """Mock provider for testing. Returns predictable responses."""

    def __init__(self, response_template: str = ""):
        self.template = response_template or "This is a mock response for testing ArabicMind."

    async def chat(self, messages, system_prompt="", temperature=0.7, max_tokens=4096):
        query = messages[-1].content if messages else ""
        return LLMResponse(
            content=f"{self.template}\n\nQuery processed: {query[:50]}...",
            model="mock", provider="mock",
            input_tokens=len(query)//4,
            output_tokens=50,
        )

    async def stream(self, messages, system_prompt="", temperature=0.7, max_tokens=4096):
        resp = await self.chat(messages, system_prompt)
        words = resp.content.split()
        for word in words:
            yield word + " "


# ═══════════════════════════════════════════════════════════════
#  Provider Factory
# ═══════════════════════════════════════════════════════════════

def create_provider(provider_type: str, api_key: str = "",
                    model: str = "", base_url: str = "") -> BaseLLMProvider:
    """Factory function to create a provider by name."""
    pt = provider_type.lower()

    if pt in ("anthropic", "claude"):
        m = model or "claude-sonnet-4-6"
        return AnthropicProvider(api_key=api_key, model=m)

    if pt in ("openai", "gpt"):
        m = model or "gpt-4o"
        return OpenAIProvider(api_key=api_key, model=m)

    if pt == "deepseek":
        m = model or "deepseek-reasoner"
        return OpenAIProvider(api_key=api_key, model=m,
                              base_url=base_url or "https://api.deepseek.com")

    if pt in ("qwen", "tongyi"):
        m = model or "qwen-max"
        return OpenAIProvider(api_key=api_key, model=m,
                              base_url=base_url or "https://dashscope.aliyuncs.com/compatible-mode")

    if pt == "gemini":
        m = model or "gemini-1.5-pro"
        return OpenAIProvider(api_key=api_key, model=m,
                              base_url=base_url or "https://generativelanguage.googleapis.com/v1beta/openai")

    if pt in ("mock", "test"):
        return MockProvider()

    raise ValueError(f"Unknown provider: {provider_type}. "
                     f"Supported: anthropic, openai, deepseek, qwen, gemini, mock")


SUPPORTED_PROVIDERS = {
    "anthropic": {
        "name"   : "Anthropic Claude",
        "models" : ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
        "default": "claude-sonnet-4-6",
        "url"    : "https://console.anthropic.com",
    },
    "openai": {
        "name"   : "OpenAI",
        "models" : ["gpt-4o", "gpt-4o-mini", "o1", "o3-mini"],
        "default": "gpt-4o",
        "url"    : "https://platform.openai.com",
    },
    "deepseek": {
        "name"   : "DeepSeek",
        "models" : ["deepseek-reasoner", "deepseek-chat"],
        "default": "deepseek-reasoner",
        "url"    : "https://platform.deepseek.com",
    },
    "qwen": {
        "name"   : "Qwen / Tongyi",
        "models" : ["qwen-max", "qwen-turbo", "qwen-plus"],
        "default": "qwen-max",
        "url"    : "https://dashscope.aliyuncs.com",
    },
    "gemini": {
        "name"   : "Google Gemini",
        "models" : ["gemini-1.5-pro", "gemini-2.0-flash"],
        "default": "gemini-1.5-pro",
        "url"    : "https://aistudio.google.com",
    },
}
