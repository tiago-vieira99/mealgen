import random
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import dates
from app.db import get_db
from app.generator import MAX_MEALS_PER_DAY, GenerationError, MealOption, generate_plan
from app.models import MEAL_TYPE_LABELS, Meal, MealPlan, PlanEntry, User
from app.security import csrf_protect, flash
from app.web import absolute_url, current_user, form_data, redirect, render

router = APIRouter(dependencies=[Depends(csrf_protect)])


def get_owned_plan(db: Session, user: User, plan_id: int) -> MealPlan:
    plan = db.get(MealPlan, plan_id)
    if plan is None or plan.user_id != user.id:
        raise HTTPException(404, "Plan not found.")
    return plan


def _user_meals(db: Session, user: User) -> list[Meal]:
    return list(db.scalars(select(Meal).where(Meal.user_id == user.id).order_by(func.lower(Meal.name))))


def _type_counts(meals: list[Meal]) -> dict[str, int]:
    return {t: sum(1 for m in meals if m.meal_type.value == t) for t in MEAL_TYPE_LABELS}


def _latest_plan(db: Session, user: User, week_start: date) -> MealPlan | None:
    return db.scalar(
        select(MealPlan)
        .where(MealPlan.user_id == user.id, MealPlan.week_start == week_start)
        .order_by(MealPlan.created_at.desc())
        .limit(1)
    )


def _default_form(week: str) -> dict:
    first_day = dates.today().weekday() if week == "current" else 0
    return {
        "week": week,
        "days": list(range(first_day, 7)),
        "meals_per_day": 1,
        "type_days": {t: None for t in MEAL_TYPE_LABELS},
        "name": "",
    }


def _parse_int(value: str) -> int | None:
    value = (value or "").strip()
    return int(value) if value.lstrip("-").isdigit() else None


def _fill_entries(
    plan: MealPlan,
    days: list[date],
    meals_per_day: int,
    layout: dict[date, list[MealOption]] | None,
    meals_by_id: dict[int, Meal],
) -> None:
    for day in days:
        for slot in range(meals_per_day):
            entry = PlanEntry(day=day, slot=slot)
            if layout:
                entry.set_meal(meals_by_id[layout[day][slot].id])
            plan.entries.append(entry)


def _generate(meals: list[Meal], days: list[date], meals_per_day: int, type_days: dict) -> dict:
    options = [MealOption(m.id, m.meal_type.value) for m in meals]
    return generate_plan(options, days, meals_per_day, type_days)


@router.get("/")
def dashboard(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    current, upcoming = dates.current_week_start(), dates.next_week_start()
    meal_count = db.scalar(select(func.count()).select_from(Meal).where(Meal.user_id == user.id))
    return render(
        request,
        "dashboard.html",
        weeks=[
            ("current", current, _latest_plan(db, user, current)),
            ("next", upcoming, _latest_plan(db, user, upcoming)),
        ],
        meal_count=meal_count,
        today=dates.today(),
        greeting=dates.greeting(),
    )


@router.get("/plans")
def list_plans(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    plans = db.scalars(
        select(MealPlan)
        .where(MealPlan.user_id == user.id)
        .order_by(MealPlan.week_start.desc(), MealPlan.created_at.desc())
    ).all()
    return render(request, "plans/list.html", plans=plans)


@router.get("/plans/new")
def new_plan(request: Request, week: str = "current", user: User = Depends(current_user), db: Session = Depends(get_db)):
    week = week if week in ("current", "next") else "current"
    meals = _user_meals(db, user)
    return render(request, "plans/new.html", form=_default_form(week), **_new_plan_context(meals))


def _new_plan_context(meals: list[Meal]) -> dict:
    return {
        "counts": _type_counts(meals),
        "meal_total": len(meals),
        "max_meals_per_day": MAX_MEALS_PER_DAY,
        "today_index": dates.today().weekday(),
        "week_labels": {"current": "This week", "next": "Next week"},
        "week_starts": {"current": dates.current_week_start(), "next": dates.next_week_start()},
    }


@router.post("/plans")
def create_plan(
    request: Request,
    form=Depends(form_data),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    meals = _user_meals(db, user)
    week = form.get("week") if form.get("week") in ("current", "next") else "current"
    mode = "manual" if form.get("mode") == "manual" else "random"
    day_indexes = sorted({i for i in (_parse_int(v) for v in form.getlist("days")) if i is not None and 0 <= i <= 6})
    meals_per_day = _parse_int(form.get("meals_per_day")) or 1
    type_days = {t: _parse_int(form.get(f"type_{t}")) for t in MEAL_TYPE_LABELS}
    name = (form.get("name") or "").strip()[:120]
    values = {"week": week, "days": day_indexes, "meals_per_day": meals_per_day, "type_days": type_days, "name": name}

    def fail(message: str):
        return render(request, "plans/new.html", status_code=400, form=values, error=message, **_new_plan_context(meals))

    if not day_indexes:
        return fail("Pick at least one day.")
    if not 1 <= meals_per_day <= MAX_MEALS_PER_DAY:
        return fail(f"Meals per day must be between 1 and {MAX_MEALS_PER_DAY}.")

    week_start = dates.current_week_start() if week == "current" else dates.next_week_start()
    plan_days = [week_start + timedelta(days=i) for i in day_indexes]
    layout = None
    if mode == "random":
        try:
            layout = _generate(meals, plan_days, meals_per_day, type_days)
        except GenerationError as exc:
            return fail(str(exc))

    plan = MealPlan(
        user_id=user.id,
        name=name or f"Dinners, {dates.fmt_week(week_start)}",
        week_start=week_start,
        options={"mode": mode, "days": day_indexes, "meals_per_day": meals_per_day, "type_days": type_days},
    )
    _fill_entries(plan, plan_days, meals_per_day, layout, {m.id: m for m in meals})
    db.add(plan)
    db.commit()
    flash(request, "Your plan is ready and saved." if layout else "Plan created. Pick a meal for each day.", "success")
    return redirect(f"/plans/{plan.id}")


@router.get("/plans/{plan_id}")
def plan_detail(request: Request, plan_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    plan = get_owned_plan(db, user, plan_id)
    meals = _user_meals(db, user)
    meals_by_type = {t: [m for m in meals if m.meal_type.value == t] for t in MEAL_TYPE_LABELS}
    return render(
        request,
        "plans/detail.html",
        plan=plan,
        today=dates.today(),
        meals_by_type=meals_by_type,
        share_url=absolute_url(request, f"/p/{plan.share_id}"),
        image_url=f"/p/{plan.share_id}/plan.png",
    )


def _apply_entry_changes(plan: MealPlan, form, meals_by_id: dict[int, Meal]) -> None:
    name = (form.get("name") or "").strip()[:120]
    if name:
        plan.name = name
    for entry in plan.entries:
        value = form.get(f"entry-{entry.id}")
        if value is None or value == "keep":  # "keep": meal was deleted, keep the name snapshot
            continue
        if value == "skip":
            entry.skip()
            continue
        meal_id = _parse_int(value)
        if meal_id is None:
            entry.set_meal(None)
        elif meal_id != entry.meal_id and meal_id in meals_by_id:
            entry.set_meal(meals_by_id[meal_id])


@router.post("/plans/{plan_id}/entries")
def save_entries(
    request: Request,
    plan_id: int,
    form=Depends(form_data),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    plan = get_owned_plan(db, user, plan_id)
    _apply_entry_changes(plan, form, {m.id: m for m in _user_meals(db, user)})
    db.commit()
    flash(request, "Plan saved.", "success")
    return redirect(f"/plans/{plan.id}")


@router.post("/plans/{plan_id}/entries/{entry_id}/reroll")
def reroll_entry(
    request: Request,
    plan_id: int,
    entry_id: int,
    form=Depends(form_data),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    plan = get_owned_plan(db, user, plan_id)
    entry = next((e for e in plan.entries if e.id == entry_id), None)
    if entry is None:
        raise HTTPException(404, "Entry not found.")
    meals = _user_meals(db, user)
    # The reroll button lives inside the edit form, so keep any unsaved selections too.
    _apply_entry_changes(plan, form, {m.id: m for m in meals})

    current_type = entry.display_type
    candidates = [m for m in meals if current_type is None or m.meal_type.value == current_type]
    used = {e.meal_id for e in plan.entries}
    pool = (
        [m for m in candidates if m.id not in used]
        or [m for m in candidates if m.id != entry.meal_id]
        or candidates
    )
    if pool:
        entry.set_meal(random.choice(pool))
    else:
        flash(request, "You have no other meals of that type to pick from.", "error")
    db.commit()
    return redirect(f"/plans/{plan.id}#entry-{entry.id}")


@router.post("/plans/{plan_id}/regenerate")
def regenerate_plan(request: Request, plan_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    plan = get_owned_plan(db, user, plan_id)
    options = plan.options or {}
    plan_days = sorted({e.day for e in plan.entries}) or [
        plan.week_start + timedelta(days=i) for i in options.get("days", range(7))
    ]
    meals_per_day = options.get("meals_per_day") or max((e.slot for e in plan.entries), default=0) + 1
    meals = _user_meals(db, user)
    try:
        layout = _generate(meals, plan_days, meals_per_day, options.get("type_days") or {})
    except GenerationError as exc:
        flash(request, str(exc), "error")
        return redirect(f"/plans/{plan.id}")

    plan.entries.clear()
    db.flush()  # delete old rows before inserting new ones with the same (day, slot)
    _fill_entries(plan, plan_days, meals_per_day, layout, {m.id: m for m in meals})
    plan.options = {**options, "mode": "random"}
    db.commit()
    flash(request, "Plan regenerated.", "success")
    return redirect(f"/plans/{plan.id}")


@router.post("/plans/{plan_id}/share/rotate")
def rotate_share(request: Request, plan_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    plan = get_owned_plan(db, user, plan_id)
    plan.share_id = uuid.uuid4()
    db.commit()
    flash(request, "New link created. The old one no longer works.", "success")
    return redirect(f"/plans/{plan.id}#share")


@router.post("/plans/{plan_id}/delete")
def delete_plan(request: Request, plan_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    plan = get_owned_plan(db, user, plan_id)
    db.delete(plan)
    db.commit()
    flash(request, "Plan deleted.", "success")
    return redirect("/plans")
