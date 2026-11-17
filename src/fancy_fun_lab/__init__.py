"""fancy-fun-lab: a headless gamification engine.

The Python twin of PHP ``particle-academy/laravel-fun-lab`` and Node
``@particle-academy/fancy-fun-lab``, held to both by the shared ``fun-lab/*``
conformance tables.
"""

from __future__ import annotations

from . import resources
from .analytics import AnalyticsBuilder
from .engine import AwardResult, AwardXpBuilder, FunLab, FunLabConfig, GrantBuilder, Subject
from .errors import AwardRejected, FunLabError, PeriodLeaderboardUnavailable
from .events import (
    ACHIEVEMENT_UNLOCKED,
    AWARD_GRANTED,
    CATALOG_MUTATED,
    METRIC_LEVEL_REACHED,
    PRIZE_AWARDED,
    XP_AWARDED,
    AchievementUnlocked,
    AwardGranted,
    CatalogMutated,
    MetricLevelReached,
    PrizeAwarded,
    XpAwarded,
)
from .leaderboard import LeaderboardBuilder, LeaderboardEntry, LeaderboardPage
from .sqlite_store import SqliteStore
from .store import InMemoryStore, Row, Store
from .strings import headline, slug

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # The engine
    "FunLab",
    "FunLabConfig",
    "Subject",
    "AwardXpBuilder",
    "GrantBuilder",
    "AwardResult",
    "LeaderboardBuilder",
    "LeaderboardEntry",
    "LeaderboardPage",
    "AnalyticsBuilder",
    # Persistence
    "Store",
    "Row",
    "InMemoryStore",
    "SqliteStore",
    # Events
    "XP_AWARDED",
    "METRIC_LEVEL_REACHED",
    "ACHIEVEMENT_UNLOCKED",
    "PRIZE_AWARDED",
    "AWARD_GRANTED",
    "CATALOG_MUTATED",
    "XpAwarded",
    "MetricLevelReached",
    "AchievementUnlocked",
    "PrizeAwarded",
    "AwardGranted",
    "CatalogMutated",
    # Errors
    "FunLabError",
    "AwardRejected",
    "PeriodLeaderboardUnavailable",
    # Serializers and strings
    "resources",
    "slug",
    "headline",
]
