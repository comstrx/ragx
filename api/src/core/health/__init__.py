from .check import DEGRADED, DOWN, OK, Check, Probe, Result
from .health import Health

health = Health()

__all__ = ["DEGRADED", "DOWN", "OK", "Check", "Health", "Probe", "Result", "health"]
