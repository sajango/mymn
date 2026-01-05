"""Stats API endpoints."""

from fastapi import APIRouter

from services.analytics import (
    get_confidence_analysis,
    get_overall_stats,
    get_time_analysis,
)

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
def stats():
    """Get overall trading statistics."""
    return get_overall_stats()


@router.get("/confidence-analysis")
def confidence_analysis():
    """Get confidence vs outcome analysis."""
    return get_confidence_analysis()


@router.get("/time-analysis")
def time_analysis():
    """Get performance by hour and day of week."""
    return get_time_analysis()
