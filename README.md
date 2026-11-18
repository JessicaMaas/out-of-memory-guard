# out-of-memory-guard

A small standard-library-only guard that watches available memory and temporarily disables non-essential handlers before allocation failures crash the process.

## Usage

```python
from out_of_memory_guard import MemoryGuard

# In a real app this would read cgroup or /proc/self/status.
def available_bytes() -> int:
    return 512 * 1024 * 1024

guard = MemoryGuard(available_bytes, threshold_bytes=64 * 1024 * 1024, resume_bytes=128 * 1024 * 1024)
guard.register("metrics_flush", lambda: None)
guard.register("cache_warm", lambda: None)

# Call check() from a periodic task or before large allocations.
if guard.check():
    # Non-essential work is now skipped.
    pass

# Essential work bypasses the guard entirely.
guard.run_essential(lambda: None)
```

## Why this exists

When a process approaches memory exhaustion, the failure mode is usually an
`MemoryError` or an OOM kill, not a graceful degradation. Non-essential
handlers — metrics flushes, cache warmers, background prefetches — can be the
allocations that push the process over the edge. This library gives callers a
single place to say "these handlers are optional" and a single place to check
whether to run them.

The trade-off is explicit hysteresis. A single threshold flaps when memory
hovers around it: handlers get disabled, freed memory lets them run, they
allocate, and memory drops again. The guard therefore takes two thresholds.
Handlers are disabled at or below `threshold_bytes` and re-enabled only at or
above `resume_bytes`. Between the two, the previous state is kept. This means
memory can sit between the thresholds with handlers still disabled, which is
the intended conservative behaviour.

## The awkward edge

The guard does not know how much memory your handlers allocate. If a handler
is marked non-essential but allocates a large buffer the moment it runs, the
guard cannot prevent that allocation. The guard only decides *whether* to run
a handler, not *how* it runs. Treat the handler registration as a promise that
the handler is safe to skip, and keep the handlers themselves small.

## API

- `MemoryGuard(memory_reader, threshold_bytes, resume_bytes)`
  - `memory_reader` is a zero-argument callable returning available memory in bytes.
  - `threshold_bytes` is the available-memory level at or below which handlers are disabled.
  - `resume_bytes` is the available-memory level at or above which handlers are re-enabled.
  - Raises `ValueError` if `resume_bytes < threshold_bytes`.
- `guard.register(name, handler)` — register a non-essential zero-argument callable.
- `guard.unregister(name)` — remove a handler; no-op if unknown.
- `guard.is_disabled(name)` — True if the named handler is currently disabled.
- `guard.check()` — evaluate memory and toggle handlers; returns True if any are disabled.
- `guard.run_essential(func)` — run `func` regardless of guard state.
- `guard.run_handlers()` — run enabled handlers in registration order and return their names.
- `guard.state` — the live `GuardState` (`disabled`, `threshold_bytes`, `resume_bytes`).

## Performance

The window keeps a bounded buffer, so `push` is constant time and memory does not
grow with the length of the stream. `peak` and `trough` are linear in the window
size, which is the trade that keeps `push` cheap.

