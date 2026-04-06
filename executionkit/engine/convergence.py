"""Convergence detection for iterative refinement loops."""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class ConvergenceDetector:
    """Tracks score history and detects convergence via delta + patience.

    Convergence is declared when either:
    - ``score_threshold`` is set and the current score meets or exceeds it, or
    - The score delta has been below ``delta_threshold`` for ``patience``
      consecutive iterations.

    Attributes:
        delta_threshold: Minimum meaningful score improvement.
        patience: How many consecutive stale iterations before stopping.
        score_threshold: Optional absolute score target for early exit.
    """

    delta_threshold: float = 0.01
    patience: int = 3
    score_threshold: float | None = None

    _scores: list[float] = field(default_factory=list, init=False, repr=False)
    _stale_count: int = field(default=0, init=False, repr=False)

    def should_stop(self, score: float) -> bool:
        """Record a score and return whether convergence is reached.

        Args:
            score: Evaluator score, must be in [0.0, 1.0] and not NaN.

        Returns:
            True if the loop should stop (converged or threshold met).

        Raises:
            ValueError: If score is NaN or outside [0.0, 1.0].
        """
        if math.isnan(score) or not (0.0 <= score <= 1.0):
            raise ValueError(f"Invalid score: {score}")

        self._scores.append(score)

        # Absolute threshold check
        if self.score_threshold is not None and score >= self.score_threshold:
            return True

        # Delta-based convergence check (need at least 2 scores)
        if len(self._scores) >= 2:
            delta = abs(self._scores[-1] - self._scores[-2])
            if delta < self.delta_threshold:
                self._stale_count += 1
            else:
                self._stale_count = 0

            if self._stale_count >= self.patience:
                return True

        return False

    def reset(self) -> None:
        """Clear all tracked state."""
        self._scores.clear()
        self._stale_count = 0
