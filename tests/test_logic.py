import re

from app.game.logic import calculate_guess_score, evaluate_guess, generate_secret


def test_generate_secret_unique_digits():
    secret = generate_secret(unique_digits=True)
    assert re.fullmatch(r"\d{4}", secret)
    assert len(set(secret)) == 4


def test_evaluate_guess_counts_plus_minus():
    secret = "1234"
    guess = "1243"
    result = evaluate_guess(secret, guess)
    assert result["plus"] == 2  # positions 1 and 2
    assert result["minus"] == 2  # digits 3 and 4 swapped
    assert not result["is_clean_miss"]


def test_evaluate_guess_clean_miss():
    secret = "9876"
    guess = "1234"
    result = evaluate_guess(secret, guess)
    assert result["plus"] == 0
    assert result["minus"] == 0
    assert result["is_clean_miss"]


def test_calculate_score_with_position_and_bonus():
    score = calculate_guess_score(position=1, plus=4, minus=0, is_clean_miss=False)
    assert score > 120  # base + plus bonus


def test_calculate_score_clean_miss_bonus():
    score = calculate_guess_score(position=None, plus=0, minus=0, is_clean_miss=True)
    assert score == 5

