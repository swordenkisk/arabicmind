"""
app.py — ArabicMind Flask Application
=====================================
Dual-LLM engine web interface for Arabic users.

Routes:
  GET  /                → Main dual-pane chat UI
  POST /api/chat        → Full pipeline (non-streaming)
  GET  /api/stream      → SSE streaming pipeline
  GET  /api/domains     → List available domains
  GET  /api/providers   → List supported LLM providers
  POST /api/validate_key → Validate an API key
  GET  /health          → Health check

Author: github.com/swordenkisk/arabicmind
"""

import asyncio
import json
import os
import time
from flask import Flask, Response, jsonify, render_template, request, stream_with_context

from src.engine.dual_engine import DualEngine
from src.providers.base import create_provider, MockProvider, SUPPORTED_PROVIDERS
from src.prompts.system_prompts import SystemPromptRouter

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "arabicmind-dev-2026")

router = SystemPromptRouter()


def _get_event_loop():
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


def _build_engine(req_data: dict) -> DualEngine:
    """Build a DualEngine from request configuration."""
    # Translation provider
    tr_type  = req_data.get("translation_provider", "mock")
    tr_key   = req_data.get("translation_api_key", "")
    tr_model = req_data.get("translation_model", "")
    tr_url   = req_data.get("translation_base_url", "")
    translator = create_provider(tr_type, api_key=tr_key, model=tr_model, base_url=tr_url)

    # Reasoning provider
    rs_type  = req_data.get("reasoning_provider", "mock")
    rs_key   = req_data.get("reasoning_api_key", "")
    rs_model = req_data.get("reasoning_model", "")
    rs_url   = req_data.get("reasoning_base_url", "")
    reasoner = create_provider(rs_type, api_key=rs_key, model=rs_model, base_url=rs_url)

    return DualEngine(
        translation_provider=translator,
        reasoning_provider=reasoner,
        router=router,
        show_cot=req_data.get("show_cot", True),
    )


@app.route("/")
def index():
    domains   = router.list_domains()
    providers = SUPPORTED_PROVIDERS
    return render_template("index.html", domains=domains, providers=providers)


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True) or {}
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "يرجى إدخال سؤال | Please provide a query"}), 400

    engine = _build_engine(data)
    loop   = _get_event_loop()

    try:
        result = loop.run_until_complete(engine.process(
            arabic_query=query,
            force_domain=data.get("domain", ""),
        ))
        return jsonify(result.to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/stream")
def api_stream():
    query = request.args.get("query", "").strip()
    if not query:
        def err():
            yield f"data: {json.dumps({'event':'error','message':'لا يوجد سؤال'})}\n\n"
        return Response(stream_with_context(err()), mimetype="text/event-stream")

    # Parse config from query params
    config = {
        "translation_provider": request.args.get("tr_provider", "mock"),
        "translation_api_key" : request.args.get("tr_key", ""),
        "translation_model"   : request.args.get("tr_model", ""),
        "reasoning_provider"  : request.args.get("rs_provider", "mock"),
        "reasoning_api_key"   : request.args.get("rs_key", ""),
        "reasoning_model"     : request.args.get("rs_model", ""),
        "show_cot"            : request.args.get("show_cot", "true") == "true",
        "domain"              : request.args.get("domain", ""),
    }

    engine = _build_engine(config)
    loop   = _get_event_loop()

    def generate():
        async def run():
            async for event in engine.stream(query, force_domain=config["domain"]):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        gen = run()
        while True:
            try:
                chunk = loop.run_until_complete(gen.__anext__())
                yield chunk
            except StopAsyncIteration:
                break
            except Exception as e:
                yield f"data: {json.dumps({'event':'error','message':str(e)})}\n\n"
                break

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/domains")
def api_domains():
    return jsonify(router.list_domains())


@app.route("/api/providers")
def api_providers():
    return jsonify(SUPPORTED_PROVIDERS)


@app.route("/api/validate_key", methods=["POST"])
def api_validate_key():
    data     = request.get_json(silent=True) or {}
    ptype    = data.get("provider", "")
    api_key  = data.get("api_key", "")
    model    = data.get("model", "")
    base_url = data.get("base_url", "")

    if not api_key:
        return jsonify({"valid": False, "error": "No API key provided"})

    try:
        provider = create_provider(ptype, api_key=api_key, model=model, base_url=base_url)
        from src.providers.base import ChatMessage
        loop = _get_event_loop()
        resp = loop.run_until_complete(
            provider.chat([ChatMessage(role="user", content="Reply with: OK")],
                          max_tokens=10, temperature=0)
        )
        return jsonify({"valid": True, "model": resp.model,
                        "response_preview": resp.content[:30]})
    except Exception as e:
        return jsonify({"valid": False, "error": str(e)})


@app.route("/health")
def health():
    return jsonify({"status": "ok", "app": "ArabicMind", "version": "1.0.0"})


if __name__ == "__main__":
    host  = os.environ.get("HOST", "127.0.0.1")
    port  = int(os.environ.get("PORT", 7071))
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    print(f"\n{'='*55}")
    print("  ArabicMind — عقل عربي | Dual-LLM Engine")
    print(f"  http://{host}:{port}")
    print(f"{'='*55}\n")
    app.run(host=host, port=port, debug=debug, threaded=True)
