"""Manifest-driven SpeedLocal analysis engine."""

from .engine import AnalysisResult, GroupCellResult, GroupResult, run_analysis

__all__ = [
    "AnalysisResult",
    "GroupCellResult",
    "GroupResult",
    "run_analysis",
]
