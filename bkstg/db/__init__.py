"""DuckDB data layer for catalog analysis."""

from .graph_analysis import DependencyAnalyzer
from .history_queries import HistoryQueries
from .loader import CatalogLoader
from .queries import CatalogQueries
from .schema import create_schema, get_connection
from .score_queries import ScoreQueries

__all__ = [
    "create_schema",
    "get_connection",
    "CatalogLoader",
    "CatalogQueries",
    "DependencyAnalyzer",
    "HistoryQueries",
    "ScoreQueries",
]
