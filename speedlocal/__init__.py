"""Manifest-driven SpeedLocal analysis engine."""

__all__ = [
    "AnalysisResult",
    "GroupCellResult",
    "GroupResult",
    "run_analysis",
]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from .engine import AnalysisResult, GroupCellResult, GroupResult, run_analysis

    exports = {
        "AnalysisResult": AnalysisResult,
        "GroupCellResult": GroupCellResult,
        "GroupResult": GroupResult,
        "run_analysis": run_analysis,
    }
    return exports[name]
