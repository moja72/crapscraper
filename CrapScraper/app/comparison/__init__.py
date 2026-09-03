from app.comparison.service import ComparisonService
from app.comparison.performance_runtime import install_comparison_performance_runtime

install_comparison_performance_runtime()

__all__ = ["ComparisonService"]
