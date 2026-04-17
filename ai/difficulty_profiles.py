"""Difficulty settings for the single-player AI."""

from shared.constants import Difficulty


def get_depth_for_difficulty(difficulty):
    """
    Return the search depth for a requested difficulty.

    The first version keeps this intentionally simple so the difficulty
    behavior is easy to understand and tune later.
    """

    if difficulty == Difficulty.EASY:
        return 1

    if difficulty == Difficulty.MEDIUM:
        return 2

    if difficulty == Difficulty.HARD:
        return 4

    raise ValueError("Unsupported difficulty: " + str(difficulty))
