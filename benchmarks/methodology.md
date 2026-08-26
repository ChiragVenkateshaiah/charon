# Benchmark Methodology

**Status: stub.** This file is a placeholder for the methodology that gets fixed in
Week 2 of Phase 1 (see `docs/phase-1-plan.md`). The rules below are carried over from
that plan so they exist in one canonical place before any run happens. Once Week 2
finalizes the load generator and fills in the specifics (exact tool, prompt set, hardware
profile), this file becomes the real methodology doc and stops changing.

Per [ADR-0001](../adr/0001-measurement-discipline.md): a number only counts if it was
produced on real hardware by a reproducible run whose raw output is committed to the
repo. These rules exist so the numbers mean something.

## The seven rules

1. **Fixed input and output token counts.** Variable-length outputs make runs
   incomparable. Use a fixed prompt set and `min_tokens = max_tokens` so every request
   generates exactly N tokens.
2. **Discard warmup.** First requests include compilation, cache allocation, and CUDA
   context setup. Drop the first 30 seconds or first 20 requests.
3. **Report percentiles, never averages alone.** p50, p95, p99. Averages hide the
   behaviour that matters.
4. **Three runs minimum**, report median and spread. If spread exceeds ~10%, something
   is uncontrolled — find it before continuing.
5. **Record the environment every time:** GPU model, driver, CUDA version, framework
   versions, model revision hash, exact server flags.
6. **Change one variable per experiment.** Tempting to bundle; don't.
7. **Commit raw output**, not just the summary table.

## Not yet decided

The following get filled in during Week 2, once chosen deliberately rather than
inherited:

- Load generator (adopted tool vs. hand-rolled)
- Canonical prompt set and fixed token counts
- Hardware profile block (GPU model, driver, CUDA, framework versions — recorded once,
  referenced thereafter)
- Concurrency sweep levels used as the standard sweep

Until this section is filled in, no benchmark run should be treated as methodology-final.
