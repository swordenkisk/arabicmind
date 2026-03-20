"""
test_arabicmind.py — ArabicMind Test Suite (20 tests)
Run: python tests/test_arabicmind.py
"""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.prompts.system_prompts import SystemPromptRouter, DOMAINS
from src.providers.base import (
    MockProvider, ChatMessage, create_provider, SUPPORTED_PROVIDERS
)
from src.engine.dual_engine import DualEngine, DualEngineResult

W = 64
passed = failed = 0
results = []
loop = asyncio.new_event_loop()

def run(coro): return loop.run_until_complete(coro)
def check(name, cond, detail=""):
    global passed, failed
    msg = f"  [{'PASS' if cond else 'FAIL'}] {name}"
    if detail: msg += f"  --  {detail}"
    print(msg)
    results.append((name, cond))
    if cond: passed += 1
    else:    failed += 1

print("=" * W)
print("  ArabicMind — Test Suite (20 tests)")
print("=" * W)

# ── Block A: Domain Router ─────────────────────────────────
print("\n[ Block A: SystemPromptRouter (5 tests) ]\n")

router = SystemPromptRouter()

check("A1: DOMAINS dict has ≥ 10 entries",
      len(DOMAINS) >= 10, f"count={len(DOMAINS)}")

d1 = router.detect_domain("اشرح خوارزمية QuickSort وكيف تعمل")
check("A2: detects code domain for QuickSort",
      d1 in ("code_write", "code_debug", "data_science"),
      f"domain={d1}")

d2 = router.detect_domain("احسب تكامل sin(x) من صفر إلى pi")
check("A3: detects math domain for integral",
      d2 in ("math_solve", "math_proof"),
      f"domain={d2}")

d3 = router.detect_domain("أثبت مبرهنة فيثاغورس")
check("A4: detects math_proof for proof request",
      d3 in ("math_proof", "math_solve"),
      f"domain={d3}")

prompt = router.get_system_prompt("code_debug")
check("A5: code_debug prompt is non-empty and detailed",
      len(prompt) > 100 and "debug" in prompt.lower(),
      f"len={len(prompt)}")

# ── Block B: Providers ─────────────────────────────────────
print("\n[ Block B: Providers (4 tests) ]\n")

mock = MockProvider("Test response OK")
resp = run(mock.chat([ChatMessage(role="user", content="Hello")]))
check("B1: MockProvider.chat returns LLMResponse",
      resp.content and len(resp.content) > 0,
      f"content='{resp.content[:30]}'")

chunks = []
async def collect():
    async for c in mock.stream([ChatMessage(role="user", content="Stream test")]):
        chunks.append(c)

run(collect())
check("B2: MockProvider.stream yields chunks",
      len(chunks) > 0, f"chunks={len(chunks)}")

p = create_provider("mock")
check("B3: create_provider('mock') returns MockProvider",
      isinstance(p, MockProvider))

check("B4: SUPPORTED_PROVIDERS has 5 entries",
      len(SUPPORTED_PROVIDERS) >= 5,
      f"count={len(SUPPORTED_PROVIDERS)}")

# ── Block C: Dual Engine ────────────────────────────────────
print("\n[ Block C: DualEngine (6 tests) ]\n")

translator = MockProvider("This is the English translation of the Arabic query.")
reasoner   = MockProvider(
    "Step 1: Understand the problem. Step 2: Apply the algorithm. "
    "Step 3: The answer is 42. Therefore: the solution is complete."
)
engine = DualEngine(translator, reasoner, router, show_cot=True)

result = run(engine.process("اشرح لي كيف تعمل خوارزمية الفرز السريع"))
check("C1: process() returns DualEngineResult",
      isinstance(result, DualEngineResult))

check("C2: arabic_query preserved",
      "خوارزمية" in result.arabic_query,
      f"query='{result.arabic_query[:40]}'")

check("C3: english_query generated",
      len(result.english_query) > 5,
      f"en='{result.english_query[:40]}'")

check("C4: english_response non-empty",
      len(result.english_response) > 10,
      f"len={len(result.english_response)}")

check("C5: arabic_response non-empty (back-translated)",
      len(result.arabic_response) > 5,
      f"len={len(result.arabic_response)}")

check("C6: domain detected",
      result.detected_domain in DOMAINS,
      f"domain={result.detected_domain}")

# ── Block D: CoT Extraction ─────────────────────────────────
print("\n[ Block D: CoT Extraction (3 tests) ]\n")

text1 = "First: we identify the pivot.\nSecond: we partition the array.\nFinally: we recurse on both halves."
cot1  = engine._extract_cot(text1)
check("D1: extracts First/Second/Finally steps",
      len(cot1) >= 2, f"steps={cot1}")

text2 = "1. Parse the input\n2. Validate types\n3. Apply algorithm\n4. Return result"
cot2  = engine._extract_cot(text2)
check("D2: extracts numbered steps",
      len(cot2) >= 3, f"steps={cot2}")

text3 = "<think>I need to solve this step by step.\nFirst consider the base case.\nThen the recursive step.</think>\nThe answer is X."
cot3  = engine._extract_cot(text3)
check("D3: extracts <think> tag content (DeepSeek style)",
      len(cot3) >= 1, f"steps={cot3[:2]}")

# ── Block E: Streaming ──────────────────────────────────────
print("\n[ Block E: Streaming (2 tests) ]\n")

events = []
async def collect_stream():
    async for ev in engine.stream("ما هو مفهوم التكامل؟"):
        events.append(ev)

run(collect_stream())
event_types = [e["event"] for e in events]
check("E1: stream yields multiple events",
      len(events) >= 4, f"events={event_types}")

check("E2: stream ends with 'done' event",
      "done" in event_types,
      f"last={event_types[-1] if event_types else 'none'}")

# ── Summary ─────────────────────────────────────────────────
total = passed + failed
print()
print("=" * W)
status = "ALL PASS ✅" if failed == 0 else f"{failed} FAILED ❌"
print(f"  Results  :  {passed}/{total} tests passed  ({status})")
if failed > 0:
    print("  Failures :  " + ", ".join(n for n, ok in results if not ok))
print("=" * W)

import sys as _sys; _sys.exit(0 if failed == 0 else 1)
