"""The engine's refusals, mirroring the PHP exception classes.

Messages are part of the contract: the ``fun-lab/*`` tables compare them
verbatim with the PHP and Node engines, including their inconsistencies (an
award refused for opt-out ends with a full stop; a grant refused for the same
reason does not, because a grant refusal is a result rather than an error).
"""

from __future__ import annotations


class FunLabError(ValueError):
    """PHP's ``InvalidArgumentException``: bad input to the engine."""


class AwardRejected(FunLabError):
    """PHP's ``AwardRejectedException``.

    ``kind`` is ``cap_exceeded``, ``pipeline_rejected`` or ``opted_out``.
    """

    def __init__(self, message: str, kind: str = "rejected") -> None:
        super().__init__(message)
        self.kind = kind


class PeriodLeaderboardUnavailable(FunLabError):
    """A daily, weekly or monthly board was asked for while the event log is off.

    The log is the only record of WHEN XP was earned, and an empty board would
    read exactly like a quiet week, so the request is refused.
    """
