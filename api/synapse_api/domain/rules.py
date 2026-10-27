"""Règles chiffrées (CLAUDE.md, section Règles chiffrées)."""

from datetime import timedelta

MAX_QA_ROUND_TRIPS = 3
MAX_TASK_EXECUTION = timedelta(hours=2)
PROD_ROLLBACK_WINDOW = timedelta(minutes=30)
