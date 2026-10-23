from engine.database import database
from .health import DEGRADED, DOWN, OK, Check, Health, Heartbeat, Probe, Result

health    = Health()
heartbeat = Heartbeat(health, database)

__all__ = ["DEGRADED", "DOWN", "OK", "Check", "Health", "Heartbeat", "Probe", "Result", "health", "heartbeat"]
