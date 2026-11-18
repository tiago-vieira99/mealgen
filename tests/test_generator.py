import random
from datetime import date, timedelta

import pytest

from app.generator import GenerationError, MealOption, generate_plan

WEEK = [date(2026, 11, 16) + timedelta(days=i) for i in range(7)]


def library(meat=5, fish=5, vegetarian=5):
    meals, next_id = [], 1
    for meal_type, n in (("meat", meat), ("fish", fish), ("vegetarian", vegetarian)):
        for _ in range(n):
            meals.append(MealOption(next_id, meal_type))
            next_id += 1
    return meals


def days_with(plan, meal_type):
    return sum(1 for meals in plan.values() if any(m.meal_type == meal_type for m in meals))


@pytest.mark.parametrize("seed", range(30))
def test_exact_type_day_counts(seed):
    plan = generate_plan(library(), WEEK, 1, {"meat": 3, "fish": 2}, rng=random.Random(seed))
    assert days_with(plan, "meat") == 3
    assert days_with(plan, "fish") == 2
    assert days_with(plan, "vegetarian") == 2
    assert all(len(m) == 1 for m in plan.values())


@pytest.mark.parametrize("seed", range(30))
def test_multiple_meals_per_day_keeps_exact_counts(seed):
    plan = generate_plan(library(), WEEK[:5], 2, {"meat": 2, "fish": 0}, rng=random.Random(seed))
    assert days_with(plan, "meat") == 2
    assert days_with(plan, "fish") == 0
    assert all(len(m) == 2 for m in plan.values())


def test_no_repeats_until_library_is_exhausted():
    meals = library(meat=7, fish=0, vegetarian=0)
    plan = generate_plan(meals, WEEK, 1, rng=random.Random(1))
    ids = [m.id for day in plan.values() for m in day]
    assert len(set(ids)) == 7


def test_repeats_when_library_is_small():
    plan = generate_plan(library(meat=2, fish=0, vegetarian=0), WEEK, 1)
    assert len(plan) == 7


def test_only_selected_days():
    plan = generate_plan(library(), [WEEK[0], WEEK[4]], 1)
    assert sorted(plan) == [WEEK[0], WEEK[4]]


def test_all_types_constrained_must_cover_every_day():
    plan = generate_plan(library(), WEEK, 1, {"meat": 3, "fish": 2, "vegetarian": 2})
    assert [days_with(plan, t) for t in ("meat", "fish", "vegetarian")] == [3, 2, 2]
    with pytest.raises(GenerationError):
        generate_plan(library(), WEEK, 1, {"meat": 3, "fish": 2, "vegetarian": 1})


@pytest.mark.parametrize(
    "kwargs",
    [
        {"meals": [], "days": WEEK},
        {"meals": library(), "days": []},
        {"meals": library(), "days": WEEK, "meals_per_day": 0},
        {"meals": library(), "days": WEEK, "type_days": {"meat": 8}},
        {"meals": library(meat=0), "days": WEEK, "type_days": {"meat": 1}},
        {"meals": library(), "days": WEEK, "type_days": {"meat": 5, "fish": 5}},
        {"meals": library(vegetarian=0), "days": WEEK, "type_days": {"meat": 0, "fish": 0}},
    ],
)
def test_invalid_requests_raise(kwargs):
    with pytest.raises(GenerationError):
        generate_plan(**kwargs)
