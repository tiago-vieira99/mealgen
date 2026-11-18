"""Random meal plan generation.

Constraint semantics: ``type_days[t] = n`` means *exactly* n of the selected days contain at
least one meal of type t (0 excludes the type). Types left as ``None`` are unconstrained and
used freely to fill the remaining slots.
"""

import random
from dataclasses import dataclass
from datetime import date

from app.models import MEAL_TYPE_LABELS

MEAL_TYPES = list(MEAL_TYPE_LABELS)
MAX_MEALS_PER_DAY = 4


@dataclass(frozen=True)
class MealOption:
    id: int
    meal_type: str


class GenerationError(ValueError):
    pass


class _MealPicker:
    """Draws meals of a type without repeating until every meal of that type was used."""

    def __init__(self, by_type: dict[str, list[MealOption]], rng: random.Random) -> None:
        self._by_type = by_type
        self._queues: dict[str, list[MealOption]] = {t: [] for t in by_type}
        self._rng = rng

    def pick(self, meal_type: str) -> MealOption:
        queue = self._queues[meal_type]
        if not queue:
            queue.extend(self._by_type[meal_type])
            self._rng.shuffle(queue)
        return queue.pop()


def _assign_types(
    days: list[date],
    meals_per_day: int,
    constraints: dict[str, int],
    fillers: list[str],
    filler_weights: list[int],
    rng: random.Random,
) -> dict[date, list[str]] | None:
    required: dict[date, set[str]] = {d: set() for d in days}
    # Place the most demanding types first, each on the least loaded days (ties broken randomly).
    order = list(constraints.items())
    rng.shuffle(order)
    order.sort(key=lambda item: -item[1])
    for meal_type, n in order:
        candidates = [d for d in days if len(required[d]) < meals_per_day]
        if len(candidates) < n:
            return None
        rng.shuffle(candidates)
        candidates.sort(key=lambda d: len(required[d]))
        for d in candidates[:n]:
            required[d].add(meal_type)

    layout: dict[date, list[str]] = {}
    for d in days:
        types = list(required[d])
        missing = meals_per_day - len(types)
        if missing:
            # Repeating a constrained type on a day that already has it keeps its day count exact.
            allowed = fillers + types
            if not allowed:
                return None
            weights = filler_weights + [1] * len(types)
            types += rng.choices(allowed, weights=weights, k=missing)
        rng.shuffle(types)
        layout[d] = types
    return layout


def generate_plan(
    meals: list[MealOption],
    days: list[date],
    meals_per_day: int = 1,
    type_days: dict[str, int | None] | None = None,
    rng: random.Random | None = None,
    attempts: int = 50,
) -> dict[date, list[MealOption]]:
    rng = rng or random.Random()
    days = sorted(set(days))
    type_days = type_days or {}

    if not days:
        raise GenerationError("Pick at least one day.")
    if not 1 <= meals_per_day <= MAX_MEALS_PER_DAY:
        raise GenerationError(f"Meals per day must be between 1 and {MAX_MEALS_PER_DAY}.")
    if not meals:
        raise GenerationError("You have no saved meals yet. Add a few before generating a plan.")

    by_type = {t: [m for m in meals if m.meal_type == t] for t in MEAL_TYPES}
    constraints = {t: n for t, n in type_days.items() if t in by_type and n is not None}

    for meal_type, n in constraints.items():
        label = MEAL_TYPE_LABELS[meal_type].lower()
        if not 0 <= n <= len(days):
            raise GenerationError(f"Days with {label} must be between 0 and {len(days)}.")
        if n > 0 and not by_type[meal_type]:
            raise GenerationError(f"You asked for {n} day(s) with {label}, but you have no {label} meals saved.")

    fillers = [t for t in MEAL_TYPES if t not in constraints and by_type[t]]
    filler_weights = [len(by_type[t]) for t in fillers]
    if not fillers and not any(constraints.values()):
        raise GenerationError("These rules leave no meal type available to choose from.")
    if sum(constraints.values()) > len(days) * meals_per_day:
        raise GenerationError("The rules ask for more meals than the selected days and meals per day allow.")

    for _ in range(attempts):
        layout = _assign_types(days, meals_per_day, constraints, fillers, filler_weights, rng)
        if layout is not None:
            break
    else:
        raise GenerationError(
            "These rules can't be met: some days would be left without an allowed meal type. "
            "Set a type to \"Any\" or adjust the numbers."
        )

    picker = _MealPicker(by_type, rng)
    return {d: [picker.pick(t) for t in layout[d]] for d in days}
