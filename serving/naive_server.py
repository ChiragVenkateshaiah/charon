"""
Naive single-stream inference server — Charon Phase 1, Week 1.

Deliberately the worst reasonable implementation: plain transformers
``model.generate``, one request at a time behind a global lock, no batching, no
optimization, no compilation. Its only jobs are to be correct and to be honest
about its own timings, so the Week 1 baseline row of the benchmark table can be
trusted.

What it exists to show: at concurrency 1 a server like this leaves most of a GPU
idle, because decode is memory-bandwidth-bound and a batch of one wastes nearly
all available compute.

Write and smoke-test this locally on CPU — one request, confirm it works. Every
*measurement* run happens on the GCP g2-standard-4 spot instance (see CLAUDE.md
and docs/phase-1-plan.md). The code is device-agnostic; nothing here changes
between the CPU smoke test and the GPU run.
"""

from __future__ import annotations

import os
import threading
import time
from contextlib import asynccontextmanager

import torch
import transformers
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from transformers import AutoModelForCausalLM, AutoTokenizer, LogitsProcessor

# Week 1 model decision — see docs/worklog.md. Env-overridable so the Week 6
# scale-up can point at Qwen2.5-7B-Instruct without touching this file.
MODEL_ID = os.environ.get("CHARON_MODEL_ID", "Qwen/Qwen2.5-1.5B-Instruct")
MODEL_REVISION = os.environ.get(
    "CHARON_MODEL_REVISION", "989aa7980e4cf806f80c7fef2b1adb7bc71aa306"
)

# One request at a time. This lock *is* the naive part. Later weeks (batching,
# continuous batching) get their own files; they do not edit this one.
_GEN_LOCK = threading.Lock()

_STATE: dict = {}


class _StepTimer(LogitsProcessor):
    """Timestamps each decode step; leaves the logits untouched.

    ``generate()`` runs logits processing once per forward pass. The first call
    lands right after prefill, when the first token's logits are ready — that is
    the TTFT boundary. ``len(self.times)`` equals the number of decode steps,
    which for a forced output length (``min_new_tokens == max_new_tokens``) is
    the exact output token count.
    """

    def __init__(self) -> None:
        self.times: list[float] = []

    def __call__(self, input_ids, scores):  # noqa: ANN001, ARG002
        self.times.append(time.perf_counter())
        return scores


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
    # transformers 5 renamed `torch_dtype=` to `dtype=`. Try the current name,
    # fall back to the old one so this runs on 4.x too (CLAUDE.md version drift).
    common = {"revision": MODEL_REVISION, "device_map": "auto"}
    try:
        model = AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype="auto", **common)
    except (TypeError, ValueError):
        model = AutoModelForCausalLM.from_pretrained(MODEL_ID, torch_dtype="auto", **common)
    model.eval()
    _STATE.update(
        tokenizer=tokenizer,
        model=model,
        device=str(next(model.parameters()).device),
        dtype=str(next(model.parameters()).dtype),
    )
    if torch.cuda.is_available():
        _STATE["weights_vram_bytes"] = int(torch.cuda.memory_allocated())
    try:
        yield
    finally:
        _STATE.clear()


app = FastAPI(title="charon-naive-server", lifespan=lifespan)


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    max_tokens: int = Field(gt=0, le=8192)
    # Default min == max: methodology rule 1 — every request emits exactly N
    # tokens, so runs are comparable.
    min_tokens: int | None = Field(default=None, gt=0, le=8192)


class GenerateResponse(BaseModel):
    text: str
    prompt_tokens: int
    output_tokens: int
    ttft_s: float
    tpot_s: float
    e2e_s: float
    decode_tokens_per_s: float
    itl_s: list[float]
    peak_vram_bytes: int | None


def _require_model():
    if "model" not in _STATE:
        raise HTTPException(status_code=503, detail="model not loaded")
    return _STATE["tokenizer"], _STATE["model"]


@app.get("/healthz")
def healthz() -> dict:
    _require_model()  # 503 until the model finishes loading
    return {
        "status": "ok",
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "device": _STATE["device"],
        "dtype": _STATE["dtype"],
        "weights_vram_bytes": _STATE.get("weights_vram_bytes"),
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "cuda_available": torch.cuda.is_available(),
        "cuda_build": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    }


@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest) -> GenerateResponse:
    tokenizer, model = _require_model()

    min_tokens = req.min_tokens or req.max_tokens
    if min_tokens > req.max_tokens:
        raise HTTPException(status_code=422, detail="min_tokens must not exceed max_tokens")

    prompt_text = tokenizer.apply_chat_template(
        [{"role": "user", "content": req.prompt}],
        add_generation_prompt=True,
        tokenize=False,
    )
    enc = tokenizer(prompt_text, return_tensors="pt", add_special_tokens=False)
    enc = {k: v.to(_STATE["device"]) for k, v in enc.items()}
    prompt_len = int(enc["input_ids"].shape[1])

    pad_token_id = tokenizer.pad_token_id
    if pad_token_id is None:
        pad_token_id = tokenizer.eos_token_id

    # Serialize: the whole point of the baseline is concurrency 1.
    with _GEN_LOCK:
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
        timer = _StepTimer()
        t0 = time.perf_counter()
        with torch.inference_mode():
            out = model.generate(
                **enc,
                min_new_tokens=min_tokens,
                max_new_tokens=req.max_tokens,
                do_sample=False,
                num_beams=1,
                pad_token_id=pad_token_id,
                logits_processor=[timer],
            )
        t_end = time.perf_counter()
        peak_vram_bytes = (
            int(torch.cuda.max_memory_allocated()) if torch.cuda.is_available() else None
        )

    if not timer.times:
        raise HTTPException(status_code=500, detail="no tokens generated")

    output_ids = out[0, prompt_len:]
    text = tokenizer.decode(output_ids, skip_special_tokens=True)
    output_tokens = int(output_ids.shape[0])

    ttft_s = timer.times[0] - t0
    e2e_s = t_end - t0
    itl_s = [timer.times[i] - timer.times[i - 1] for i in range(1, len(timer.times))]
    tpot_s = sum(itl_s) / len(itl_s) if itl_s else 0.0
    decode_window = e2e_s - ttft_s
    decode_tokens_per_s = (output_tokens - 1) / decode_window if decode_window > 0 else 0.0

    return GenerateResponse(
        text=text,
        prompt_tokens=prompt_len,
        output_tokens=output_tokens,
        ttft_s=ttft_s,
        tpot_s=tpot_s,
        e2e_s=e2e_s,
        decode_tokens_per_s=decode_tokens_per_s,
        itl_s=itl_s,
        peak_vram_bytes=peak_vram_bytes,
    )
