import random
from typing import Dict

ROUND_DURATION_SECONDS = 100
TIMER_TICK_SECONDS = 1


def generate_secret(unique_digits: bool = True) -> str:
    """
    Generate a 4-digit secret number. When unique_digits=True, all digits differ.
    """
    digits = list("0123456789")
    if unique_digits:
        return "".join(random.sample(digits, 4))
    return "".join(random.choice(digits) for _ in range(4))


def evaluate_guess(secret: str, guess: str) -> Dict[str, int | bool]:
    """
    Compare secret and guess.

    Returns:
        {
            "plus": digits correct and in the right position,
            "minus": digits correct but in the wrong position,
            "is_clean_miss": True when no digit overlaps (bonus trigger)
        }
    """
    if len(secret) != 4 or len(guess) != 4:
        raise ValueError("Secret and guess must both be 4 characters long.")

    plus = sum(1 for s, g in zip(secret, guess) if s == g)
    shared = sum(min(secret.count(d), guess.count(d)) for d in set(guess))
    minus = shared - plus
    is_clean_miss = shared == 0
    return {"plus": plus, "minus": minus, "is_clean_miss": is_clean_miss}


def base_points_for_position(position: int) -> int:
    """
    Earlier winners get higher base points. Simple linear decay capped at 30 pts.
    """
    return max(30, 120 - (position - 1) * 20)


def calculate_guess_score(
    position: int | None,
    plus: int,
    minus: int,
    is_clean_miss: bool,
) -> int:
    """
    Compute score impact for a guess.

    Scoring breakdown:
        * Base points only apply when the guess is fully correct (position != None).
        * Each `+` gives +2 points even if guess is wrong.
        * Each `-` gives +1 point.
        * Clean misses reward +5 bonus points to encourage risk.
    """
    score = plus * 2 + minus
    if is_clean_miss:
        score += 5
    if position is not None:
        score += base_points_for_position(position)
    return score

