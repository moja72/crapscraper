from app.comparison.service import ComparisonService
from app.comparison.candidate_performance import install_candidate_performance
from app.comparison.performance_runtime import install_comparison_performance_runtime

install_candidate_performance()
install_comparison_performance_runtime()

__all__ = ["ComparisonService"]
