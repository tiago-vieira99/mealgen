import enum
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MealType(str, enum.Enum):
    MEAT = "meat"
    FISH = "fish"
    VEGETARIAN = "vegetarian"

    @property
    def label(self) -> str:
        return MEAL_TYPE_LABELS[self.value]


MEAL_TYPE_LABELS = {"meat": "Meat", "fish": "Fish", "vegetarian": "Vegetarian"}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    meals: Mapped[list["Meal"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    plans: Mapped[list["MealPlan"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Meal(Base):
    __tablename__ = "meals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    meal_type: Mapped[MealType] = mapped_column(
        Enum(MealType, native_enum=False, length=20, values_callable=lambda e: [m.value for m in e])
    )
    ingredients: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="meals")
    # No delete cascade: deleting a meal nulls the reference, the plan keeps the name snapshot.
    plan_entries: Mapped[list["PlanEntry"]] = relationship(back_populates="meal")

    @property
    def ingredient_list(self) -> list[str]:
        return [line.strip() for line in self.ingredients.splitlines() if line.strip()]


class MealPlan(Base):
    __tablename__ = "meal_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    share_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, index=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    week_start: Mapped[date] = mapped_column(Date, index=True)
    # Generation parameters (mode, days, meals per day, type constraints), reused by "regenerate".
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="plans")
    entries: Mapped[list["PlanEntry"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by=lambda: [PlanEntry.day, PlanEntry.slot],
    )

    @property
    def week_end(self) -> date:
        return self.week_start + timedelta(days=6)

    def entries_by_day(self) -> list[tuple[date, list["PlanEntry"]]]:
        grouped: dict[date, list[PlanEntry]] = {}
        for entry in self.entries:
            grouped.setdefault(entry.day, []).append(entry)
        return sorted(grouped.items())

    def shopping_list(self) -> list[tuple[str, int]]:
        """Ingredients of every meal in the plan, deduplicated case-insensitively, with counts."""
        counts: dict[str, list] = {}
        for entry in self.entries:
            if entry.meal is None:
                continue
            for ingredient in entry.meal.ingredient_list:
                key = ingredient.casefold()
                if key in counts:
                    counts[key][1] += 1
                else:
                    counts[key] = [ingredient, 1]
        return sorted(((name, n) for name, n in counts.values()), key=lambda item: item[0].casefold())


class PlanEntry(Base):
    __tablename__ = "plan_entries"
    __table_args__ = (UniqueConstraint("plan_id", "day", "slot"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("meal_plans.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date)
    slot: Mapped[int] = mapped_column(Integer, default=0)
    meal_id: Mapped[int | None] = mapped_column(ForeignKey("meals.id", ondelete="SET NULL"), nullable=True)
    meal_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    meal_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Deliberately nothing on this slot (eating out, leftovers…), as opposed to "not decided yet".
    skipped: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    plan: Mapped[MealPlan] = relationship(back_populates="entries")
    meal: Mapped[Meal | None] = relationship(back_populates="plan_entries")

    def set_meal(self, meal: Meal | None) -> None:
        self.meal = meal
        self.meal_name = meal.name if meal else None
        self.meal_type = meal.meal_type.value if meal else None
        self.skipped = False

    def skip(self) -> None:
        self.set_meal(None)
        self.skipped = True

    @property
    def display_name(self) -> str | None:
        return self.meal.name if self.meal else self.meal_name

    @property
    def display_type(self) -> str | None:
        return self.meal.meal_type.value if self.meal else self.meal_type
