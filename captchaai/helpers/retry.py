# ── What this file IS ─────────────────────────────────────────────────────────
# The retry/backoff schedules: generators that yield how long to sleep between
# attempts, plus a jitter helper. They exist so the orchestrator never hardcodes
# sleep maths, and so every wait gets randomness added — preventing many clients
# from retrying in lockstep and hammering the server at the same instant.

from __future__ import annotations

import random
from typing import Iterator


def add_jitter(seconds: float, jitter_max: float) -> float:
    """Return `seconds` plus a small random extra delay.

    Jitter spreads concurrent clients' retries apart so they don't all fire at the
    same moment (thundering herd). Used for fixed waits like initial wait and polls.

    Parameters:
        seconds: the base wait.
        jitter_max: upper bound of the random extra (0..jitter_max) added on top.
    """
    return seconds + random.uniform(0, jitter_max)


def exponential(base: float, jitter_max: float, factor: float = 2.0) -> Iterator[float]:
    """Yield an ever-growing backoff: base, base*factor, base*factor^2, ... + jitter.

    Used for submit failures (transient server errors), where backing off harder
    each time gives a struggling server room to recover.

    Parameters:
        base: first delay in seconds.
        jitter_max: max random extra added to every yielded delay.
        factor: growth multiplier per step (default doubles each time).
    """
    step = 0
    while True:
        # Grow the base by factor^step, then add jitter so retries don't align.
        yield base * (factor ** step) + random.uniform(0, jitter_max)
        step += 1


def linear(step_seconds: float, jitter_max: float) -> Iterator[float]:
    """Yield a constant delay each time: step_seconds + jitter, forever.

    Used for poll failures, where a steady retry cadence is appropriate (we are
    just waiting for the same answer, not for a server to recover).

    Parameters:
        step_seconds: the fixed base delay between attempts.
        jitter_max: max random extra added to every yielded delay.
    """
    while True:
        yield step_seconds + random.uniform(0, jitter_max)


def thread_busy_backoff(interval: float = 8.0, jitter_max: float = 3.0) -> Iterator[float]:
    """Yield short jittered sleep durations for thread-busy retries.

    Checks every ~8s whether a solve slot has freed up. Does not count
    attempts — the caller controls the deadline via thread_busy_timeout.
    Jitter spreads concurrent clients' retries so they don't all hammer
    threadsinfo at the same instant after sleeping.

    Parameters:
        interval: base seconds between thread-busy retry attempts.
        jitter_max: max random extra added on top of interval.
    """
    while True:
        # Sleep ~8s then let the caller retry. Jitter prevents thundering herd.
        yield interval + random.uniform(0, jitter_max)
