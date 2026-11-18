from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import MEAL_TYPE_LABELS, Meal, MealType, User
from app.security import csrf_protect, flash
from app.web import current_user, redirect, render

router = APIRouter(prefix="/meals", dependencies=[Depends(csrf_protect)])


def get_owned_meal(db: Session, user: User, meal_id: int) -> Meal:
    meal = db.get(Meal, meal_id)
    if meal is None or meal.user_id != user.id:
        raise HTTPException(404, "Meal not found.")
    return meal


def _validate(name: str, meal_type: str, ingredients: str, description: str) -> tuple[dict, str | None]:
    values = {
        "name": name.strip(),
        "meal_type": meal_type,
        "ingredients": "\n".join(line.strip() for line in ingredients.splitlines() if line.strip()),
        "description": description.strip(),
    }
    if not values["name"]:
        return values, "Give the meal a name."
    if len(values["name"]) > 120:
        return values, "Names can be at most 120 characters."
    if meal_type not in MEAL_TYPE_LABELS:
        return values, "Pick a meal type."
    if len(values["ingredients"]) > 5000 or len(values["description"]) > 5000:
        return values, "Ingredients and notes can be at most 5000 characters each."
    return values, None


@router.get("")
def list_meals(
    request: Request,
    type: str = "",
    q: str = "",
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    query = select(Meal).where(Meal.user_id == user.id).order_by(func.lower(Meal.name))
    if type in MEAL_TYPE_LABELS:
        query = query.where(Meal.meal_type == MealType(type))
    if q.strip():
        query = query.where(Meal.name.ilike(f"%{q.strip()}%"))
    counts = dict(
        db.execute(select(Meal.meal_type, func.count()).where(Meal.user_id == user.id).group_by(Meal.meal_type)).all()
    )
    return render(
        request,
        "meals/list.html",
        meals=db.scalars(query).all(),
        counts={t: counts.get(MealType(t), 0) for t in MEAL_TYPE_LABELS},
        total=sum(counts.values()),
        active_type=type,
        q=q,
    )


@router.get("/new")
def new_meal(request: Request, user: User = Depends(current_user)):
    return render(request, "meals/form.html", meal=None, values={"meal_type": "meat"})


@router.post("")
def create_meal(
    request: Request,
    name: str = Form(""),
    meal_type: str = Form(""),
    ingredients: str = Form(""),
    description: str = Form(""),
    another: str = Form(""),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    values, error = _validate(name, meal_type, ingredients, description)
    if error:
        return render(request, "meals/form.html", status_code=400, meal=None, values=values, error=error)
    values["meal_type"] = MealType(values["meal_type"])
    db.add(Meal(user_id=user.id, **values))
    db.commit()
    flash(request, f"Added “{values['name']}”.", "success")
    return redirect("/meals/new" if another else "/meals")


@router.get("/{meal_id}/edit")
def edit_meal(request: Request, meal_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    meal = get_owned_meal(db, user, meal_id)
    values = {
        "name": meal.name,
        "meal_type": meal.meal_type.value,
        "ingredients": meal.ingredients,
        "description": meal.description,
    }
    return render(request, "meals/form.html", meal=meal, values=values)


@router.post("/{meal_id}")
def update_meal(
    request: Request,
    meal_id: int,
    name: str = Form(""),
    meal_type: str = Form(""),
    ingredients: str = Form(""),
    description: str = Form(""),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    meal = get_owned_meal(db, user, meal_id)
    values, error = _validate(name, meal_type, ingredients, description)
    if error:
        return render(request, "meals/form.html", status_code=400, meal=meal, values=values, error=error)
    values["meal_type"] = MealType(values["meal_type"])
    for key, value in values.items():
        setattr(meal, key, value)
    db.commit()
    flash(request, "Meal updated.", "success")
    return redirect("/meals")


@router.post("/{meal_id}/delete")
def delete_meal(request: Request, meal_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    meal = get_owned_meal(db, user, meal_id)
    db.delete(meal)
    db.commit()
    flash(request, f"Deleted “{meal.name}”.", "success")
    return redirect("/meals")
