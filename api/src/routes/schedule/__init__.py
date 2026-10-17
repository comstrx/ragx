from core.schedule import schedule
from app.jobs import PurgeTokens

tasks = (
    schedule.job(PurgeTokens, "tokens.purge").daily_at("03:00").without_overlapping(),
)

__all__ = ["tasks"]
