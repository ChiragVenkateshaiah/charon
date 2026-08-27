# Incident 000: Twenty Minutes for One Slack Reply

**Status:** Closed as motivating observation. Not a controlled benchmark, not row zero
of any table. The gap it leaves open is more valuable than the numbers it does have.

---

## Summary

While building a headless Slack bot for an in-house data governance platform, in
production, frontier model APIs weren't available for this use case, so a local Ollama
model stood in to test the bot's GenAI capability end-to-end. Replies took roughly
20–30 minutes each — a figure recalled after the fact, not read off a timing log. This
document is the writeup of *why*, as best as it can be reconstructed after the fact —
and an honest account of where the reconstruction runs out.

Sitting through replies that slow, on a machine with no dedicated GPU, is what turned
into an interest in how inference actually runs on GPU and TPU hardware — batching, the
KV cache, quantization, and what it takes to serve larger models with numbers to tune
them by. That interest is the project.

This is the observation that motivated Charon. It is not a baseline. The comparison to
later L4 numbers will not be controlled: different runtime, different quantization,
different hardware, different everything. A real, controlled CPU baseline gets measured
on the GCP instance's own CPU in Week 1 of Phase 1. This document exists to preserve the
observation and to model, in public, the difference between a war story and a
measurement — which is exactly the distinction Phase 1 is training.

---

## Measured / Estimated / Unknown

| Input | Value | Status |
|---|---|---|
| Response time | ~20–30 minutes per message | **Recalled** — observed repeatedly in production use, but no timing log was kept; the figure is from memory |
| CPU | Intel Core i5 | **Measured** |
| RAM capacity | 16 GB | **Measured** |
| Storage | 256 GB SSD | **Measured** |
| Graphics | Intel Iris integrated, no dedicated GPU | **Measured** |
| OS | Windows 11 | **Measured** |
| Runtime | Ollama | **Measured** |
| Memory configuration (channels, speed) | Assumed DDR4-3200 dual channel (~51 GB/s peak) | **Estimated** — not captured at the time |
| Model | Assumed 7–8B parameter instruct model | **Estimated** — not recorded |
| Quantization | Assumed Ollama default, 4-bit | **Estimated** — not recorded |
| Model weight size | Assumed ~4.5–5 GB | **Estimated**, derived from the two rows above |
| Whether iGPU was used at all | Assumed no — CPU only | **Estimated**, based on how Ollama's default backend behaved at the time |
| Output token count for the observed replies | Not recorded | **Unknown** |
| Prompt / system prompt length | Not recorded | **Unknown** |
| Sustained thermal behaviour during the run | Not recorded | **Unknown** |
| Single- vs dual-channel memory (actual) | Not recorded | **Unknown** — unrecoverable; office laptop, no longer accessible |
| Exact model name/tag | Not recorded | **Unknown** — unrecoverable; office laptop, no longer accessible |

Everything below the "Measured" rows is scaffolding to produce a plausible ceiling, not
a reconstruction of what actually happened. Treat every number that follows as an
assumption wearing the clothes of an estimate.

---

## What almost certainly happened

Ollama on this machine almost certainly ran entirely on CPU. There was no dedicated GPU,
and Intel Iris integrated graphics was not a supported or meaningfully used backend for
Ollama's default configuration at the time. So the mental model is: decode running on
general-purpose CPU cores, reading model weights out of system RAM.

Decode — generating each output token one at a time, autoregressively — is
**memory-bandwidth-bound**. For a dense (non-MoE) transformer with no batching (batch
size 1, which a single Slack reply is), producing one token requires reading
essentially the entire weight set out of memory. The arithmetic that follows is standard
for this class of estimate, not specific to this incident.

### The ceiling, worked out

Assuming DDR4-3200 in dual channel:

```
3200 MT/s × 8 bytes/transfer × 2 channels ≈ 51 GB/s theoretical peak bandwidth
```

Assuming a 7–8B parameter model at Ollama's default 4-bit quantization, weights are
roughly 4.5–5 GB. Take ~4.7 GB as the midpoint.

```
51 GB/s ÷ 4.7 GB ≈ 10.9 → ~11 tokens/sec theoretical ceiling
```

That's a ceiling, not an expectation. Real-world CPU inference typically achieves
40–60% of theoretical peak bandwidth, because of imperfect memory access patterns,
non-weight traffic (KV cache, activations), and the CPU doing dequantization work
alongside the memory reads:

```
11 tokens/sec × 0.4–0.6 ≈ 4–7 tokens/sec expected
```

### Sensitivity note — the single-channel case

Memory configuration was never captured, and dual-channel is the assumption doing the
most work in the estimate above. If the machine was actually running single-channel
memory — plausible and common on consumer laptops, especially if it shipped with one
stick or a mismatched pair — effective bandwidth roughly halves to **~25 GB/s**, which
roughly halves the ceiling and the expected range with it. If that's the true
configuration, CPU-boundedness explains the slowness even more strongly than the
estimate above already suggests. Integrated graphics sharing the same memory bus, for
whatever background contention Windows and the desktop environment introduce, pushes
the effective figure down further in either case.

---

## The gap this doesn't explain

At an expected 4–7 tokens/sec — call it 5 as a round number — 20–30 minutes of wall
time implies:

```
5 tokens/sec × 1,200–1,800 seconds = ~6,000–9,000 output tokens
```

That is off by more than an order of magnitude from what a Slack bot reply would
plausibly generate. Something in the wall-time figure is not explained by decode
bandwidth alone — and the larger the recalled figure, the wider that gap gets. This is
the actual finding of this incident writeup: **the bandwidth story is necessary but not
sufficient.**

Rather than force a conclusion the data can't support, here are the candidate
explanations, unranked, as open questions:

- **Single-channel memory.** If true, halves effective bandwidth (see above) but still
  doesn't close a gap this size on its own.
- **Prefill cost on a long system prompt.** Prefill is compute-bound and scales with
  input length, not output length. A bot framework with a large system prompt, tool
  descriptions, or conversation history could spend a large, unmeasured chunk of that
  wall time in prefill before the first output token even appears — none of the
  arithmetic above accounts for TTFT at all.
- **Thermal throttling.** Sustained CPU load on a laptop chassis, especially one not
  designed for it, can throttle clock speed significantly partway through a long
  generation, meaning the effective rate late in the response could be well below the
  steady-state estimate.
- **Memory pressure and swapping.** 16 GB total RAM, shared between Windows, the
  governance platform's own services, the Slack bot process, and a multi-GB model
  resident in memory, is tight. If anything swapped to disk during inference, latency
  could degrade by an order of magnitude or more, independent of raw compute.
- **iGPU contention for the memory bus.** Even if Iris wasn't doing inference work, if
  it was doing anything else (display compositing, other GPU-accelerated apps), it was
  drawing from the same shared memory bandwidth budget as CPU inference.

No single one of these is confirmed. Several were probably compounding. That is an
honest place to leave it.

---

## Why this is the right place to leave it

This gap — a plausible mechanism (bandwidth) that explains only a fraction of the
observation, and a list of unconfirmed suspects for the rest — is the first real open
question of this project. It is also a fair description of the skill Phase 1 exists to
build: not reading about memory-bandwidth-bound decode, but being able to measure
carefully enough to close a gap like this one instead of gesturing at it.

The next CPU number in this repo will be a controlled one: fixed hardware (the GCP
instance's own CPU), fixed model, fixed quantization, fixed prompt and output length,
recorded environment, multiple runs. It will land in `benchmarks/results/`, not in this
document, and it will be directly comparable to nothing that came before it — including
this incident.

---

## TODOs — closed as unrecoverable

The machine was an office laptop and is no longer accessible. Neither of these can be
recovered, and the writeup stands without them. What actually closes the gap is a
controlled CPU baseline on the GCP instance's own CPU in Week 1 — different machine,
but a measured one.

- [x] ~~Confirm exact model name/tag used at the time~~ — unrecoverable, no access to
      the machine
- [x] ~~Confirm actual memory configuration (single vs. dual channel, actual speed)~~ —
      unrecoverable, no access to the machine
