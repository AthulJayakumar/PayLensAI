"""Deterministic, modular PayLens insight detection."""

from app.insights.engine import InsightEngine
from app.insights.models import Insight, InsightType, Severity

__all__ = ["Insight", "InsightEngine", "InsightType", "Severity"]

