"""
dual_engine.py — ArabicMind Dual-LLM Engine
=============================================
The core intelligence of ArabicMind:

  Arabic input
      ↓
  [Translation LLM]  — fast, cheap (e.g. claude-haiku, gpt-4o-mini)
      ↓
  English-optimised prompt (with Arabic semantic preservation)
      ↓
  [Reasoning LLM]    — powerful (e.g. claude-opus, gpt-4o, deepseek-r1)
      ↓
  English response + CoT chain
      ↓
  [Translation LLM]  — back to Arabic
      ↓
  Dual-pane output: Arabic answer + English reasoning

Why this works:
  Most LLMs were trained predominantly on English data.
  Complex reasoning (math, code, logic, science) performs 15-40% better
  in English than Arabic for the same underlying model.
  ArabicMind routes reasoning through English while keeping the UI Arabic.

Author: github.com/swordenkisk/arabicmind
"""

import json
import time
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

from ..prompts.system_prompts import SystemPromptRouter
from ..providers.base import BaseLLMProvider, ChatMessage


# ═══════════════════════════════════════════════════════════════
#  DualEngineResult
# ═══════════════════════════════════════════════════════════════

@dataclass
class DualEngineResult:
    """Complete result from the dual-engine pipeline."""
    # User's original Arabic query
    arabic_query        : str = ""

    # English translation of the query (what the reasoning LLM sees)
    english_query       : str = ""

    # English response from the reasoning LLM (raw, unmodified)
    english_response    : str = ""

    # Chain-of-thought steps extracted from the English response
    cot_steps           : list = field(default_factory=list)

    # Final Arabic translation of the response
    arabic_response     : str = ""

    # Detected domain (code, math, science, writing, etc.)
    detected_domain     : str = "general"

    # System prompt used for this request
    system_prompt_used  : str = ""

    # Timing breakdown
    translation_ms      : int = 0
    reasoning_ms        : int = 0
    back_translation_ms : int = 0

    @property
    def total_ms(self) -> int:
        return self.translation_ms + self.reasoning_ms + self.back_translation_ms

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


# ═══════════════════════════════════════════════════════════════
#  DualEngine
# ═══════════════════════════════════════════════════════════════

class DualEngine:
    """
    Dual-LLM orchestration engine.

    Parameters
    ----------
    translation_provider : LLM for Arabic ↔ English translation (fast/cheap)
    reasoning_provider   : LLM for deep reasoning (powerful)
    router               : SystemPromptRouter for domain detection
    preserve_arabic_terms: Keep proper nouns/technical terms in Arabic
    show_cot             : Include chain-of-thought in output
    """

    def __init__(
        self,
        translation_provider: BaseLLMProvider,
        reasoning_provider  : BaseLLMProvider,
        router              : Optional[SystemPromptRouter] = None,
        preserve_arabic_terms: bool = True,
        show_cot            : bool = True,
    ):
        self.translator = translation_provider
        self.reasoner   = reasoning_provider
        self.router     = router or SystemPromptRouter()
        self.preserve   = preserve_arabic_terms
        self.show_cot   = show_cot

    # ── Step 1: Translate Arabic → English ────────────────────

    async def _translate_to_english(self, arabic_text: str) -> str:
        """
        Translate Arabic query to English, preserving:
        - Technical terms (programming, math, science)
        - Proper nouns (names, places)
        - The exact semantic intent of the question
        """
        system = """You are a precise Arabic-to-English translation engine for technical queries.

Rules:
1. Translate the Arabic query to natural, idiomatic English
2. Preserve ALL technical terms exactly (variable names, math symbols, code, proper nouns)
3. Capture the full semantic intent — do not summarize or paraphrase
4. If the query contains code, keep the code unchanged
5. Output ONLY the English translation — no explanations, no preamble

This translation will be sent to a reasoning model. Accuracy of meaning is critical."""

        messages = [ChatMessage(role="user", content=f"Translate to English:\n\n{arabic_text}")]
        response = await self.translator.chat(messages, system_prompt=system, temperature=0.1)
        return response.content.strip()

    # ── Step 2: Route domain + build optimised prompt ─────────

    def _build_reasoning_prompt(
        self,
        english_query: str,
        domain: str,
        system_prompt: str,
    ) -> list:
        """Build the message list for the reasoning LLM."""
        messages = [ChatMessage(role="user", content=english_query)]
        return messages

    # ── Step 3: Translate English response → Arabic ────────────

    async def _translate_to_arabic(
        self,
        english_response: str,
        original_arabic_query: str,
    ) -> str:
        """
        Translate the English reasoning response back to Arabic.
        Preserves code blocks, formulas, and technical terms.
        """
        system = """You are a precise English-to-Arabic translation engine for technical responses.

Rules:
1. Translate the English response to clear, natural Modern Standard Arabic (الفصحى)
2. Keep ALL code blocks, variable names, math formulas, and technical identifiers UNCHANGED
3. Translate explanations and prose to Arabic; never translate code
4. Use proper Arabic technical vocabulary (مصفوفة for array, دالة for function, متغير for variable)
5. Preserve numbered lists, bullet points, and structural formatting
6. Output ONLY the Arabic translation — no English, no preamble

Format code blocks with ```language markers as in the original."""

        prompt = f"""Original Arabic question: {original_arabic_query}

English response to translate:

{english_response}"""

        messages = [ChatMessage(role="user", content=prompt)]
        response = await self.translator.chat(messages, system_prompt=system, temperature=0.1)
        return response.content.strip()

    # ── Step 4: Extract CoT steps ─────────────────────────────

    def _extract_cot(self, english_response: str) -> list:
        """
        Extract chain-of-thought steps from the English response.
        Looks for numbered steps, "First/Then/Finally", <think> tags, etc.
        """
        import re
        steps = []

        # Pattern 1: <think> tags (DeepSeek R1 style)
        think_match = re.search(r'<think>(.*?)</think>', english_response,
                                re.DOTALL | re.IGNORECASE)
        if think_match:
            think_content = think_match.group(1).strip()
            steps = [s.strip() for s in think_content.split('\n') if s.strip()]
            return steps[:20]

        # Pattern 2: Numbered steps "1. ... 2. ..."
        numbered = re.findall(r'^\d+\.\s+(.+)', english_response, re.MULTILINE)
        if len(numbered) >= 2:
            return numbered[:15]

        # Pattern 3: "Step N:" pattern
        step_matches = re.findall(r'[Ss]tep\s+\d+:?\s+(.+)', english_response)
        if step_matches:
            return step_matches[:15]

        # Pattern 4: "First/Second/Then/Finally" reasoning markers
        markers = re.findall(
            r'(?:^|\n)(?:First|Second|Third|Then|Next|Finally|Therefore|Thus|So)[,:]\s+(.+)',
            english_response
        )
        if markers:
            return markers[:10]

        # Fallback: split on double newlines for paragraph-level CoT
        paragraphs = [p.strip() for p in english_response.split('\n\n') if p.strip()]
        return paragraphs[:8] if len(paragraphs) > 1 else []

    # ── Main pipeline ──────────────────────────────────────────

    async def process(
        self,
        arabic_query   : str,
        conversation_history: list = None,
        force_domain   : str = "",
    ) -> DualEngineResult:
        """
        Full dual-engine pipeline: Arabic in → Arabic + English reasoning out.

        Parameters
        ----------
        arabic_query         : User's Arabic question
        conversation_history : Prior messages for context
        force_domain         : Override auto-detected domain
        """
        result = DualEngineResult(arabic_query=arabic_query)

        # ── Phase 1: Arabic → English ───────────────────────
        t0 = time.monotonic()
        result.english_query = await self._translate_to_english(arabic_query)
        result.translation_ms = int((time.monotonic() - t0) * 1000)

        # ── Phase 2: Domain detection + system prompt ────────
        result.detected_domain = force_domain or self.router.detect_domain(
            arabic_query + " " + result.english_query
        )
        system_prompt = self.router.get_system_prompt(result.detected_domain)
        result.system_prompt_used = system_prompt

        # ── Phase 3: Reasoning in English ───────────────────
        t0 = time.monotonic()
        reasoning_messages = []
        if conversation_history:
            reasoning_messages.extend(conversation_history)
        reasoning_messages.append(
            ChatMessage(role="user", content=result.english_query)
        )

        reasoning_response = await self.reasoner.chat(
            reasoning_messages,
            system_prompt=system_prompt,
            temperature=0.6,
        )
        result.english_response = reasoning_response.content
        result.reasoning_ms = int((time.monotonic() - t0) * 1000)

        # ── Phase 4: Extract CoT ────────────────────────────
        if self.show_cot:
            result.cot_steps = self._extract_cot(result.english_response)

        # ── Phase 5: English → Arabic ────────────────────────
        t0 = time.monotonic()
        result.arabic_response = await self._translate_to_arabic(
            result.english_response,
            arabic_query,
        )
        result.back_translation_ms = int((time.monotonic() - t0) * 1000)

        return result

    # ── Streaming variant ─────────────────────────────────────

    async def stream(
        self,
        arabic_query   : str,
        conversation_history: list = None,
        force_domain   : str = "",
    ) -> AsyncIterator[dict]:
        """
        Stream the pipeline result event by event.

        Yields dicts with keys:
          {"event": "translating_query"}
          {"event": "query_translated", "english_query": "..."}
          {"event": "domain_detected", "domain": "...", "prompt": "..."}
          {"event": "reasoning_chunk", "text": "..."}
          {"event": "reasoning_done", "english_response": "..."}
          {"event": "translating_response"}
          {"event": "done", "result": {...}}
        """
        yield {"event": "translating_query"}

        # Phase 1
        english_query = await self._translate_to_english(arabic_query)
        yield {"event": "query_translated", "english_query": english_query}

        # Phase 2
        domain = force_domain or self.router.detect_domain(arabic_query + " " + english_query)
        system_prompt = self.router.get_system_prompt(domain)
        yield {"event": "domain_detected", "domain": domain, "system_prompt": system_prompt}

        # Phase 3 — streaming
        reasoning_messages = list(conversation_history or [])
        reasoning_messages.append(ChatMessage(role="user", content=english_query))

        english_response = ""
        async for chunk in self.reasoner.stream(reasoning_messages, system_prompt=system_prompt):
            english_response += chunk
            yield {"event": "reasoning_chunk", "text": chunk}

        yield {"event": "reasoning_done", "english_response": english_response}

        # Phase 4 CoT
        cot = self._extract_cot(english_response)
        if cot:
            yield {"event": "cot_extracted", "steps": cot}

        # Phase 5 back-translate
        yield {"event": "translating_response"}
        arabic_response = await self._translate_to_arabic(english_response, arabic_query)

        result = DualEngineResult(
            arabic_query=arabic_query,
            english_query=english_query,
            english_response=english_response,
            cot_steps=cot,
            arabic_response=arabic_response,
            detected_domain=domain,
            system_prompt_used=system_prompt,
        )
        yield {"event": "done", "result": result.to_dict()}
