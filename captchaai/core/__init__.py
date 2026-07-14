# ── What this package IS ──────────────────────────────────────────────────────
# The core layer: the engine and the data shapes it works with.
# Exposes Config and SolveResult now; the registry and orchestrator are added in
# a later phase.

from .config import Config
from .result import SolveResult

__all__ = ["Config", "SolveResult"]
