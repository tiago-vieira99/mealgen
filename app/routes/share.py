import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.image import render_plan_image
from app.models import MealPlan
from app.web import absolute_url, render

router = APIRouter(prefix="/p")


def _shared_plan(db: Session, share_id: str) -> MealPlan:
    try:
        parsed = uuid.UUID(share_id)
    except ValueError:
        raise HTTPException(404, "Plan not found.") from None
    plan = db.scalar(select(MealPlan).where(MealPlan.share_id == parsed))
    if plan is None:
        raise HTTPException(404, "Plan not found.")
    return plan


@router.get("/{share_id}")
def shared_plan(request: Request, share_id: str, db: Session = Depends(get_db)):
    plan = _shared_plan(db, share_id)
    if request.session.get("user_id") == plan.user_id:
        request.state.user = plan.user  # owner gets the nav bar and an "edit" button
    response = render(
        request,
        "share.html",
        plan=plan,
        owner=plan.user.username,
        share_url=absolute_url(request, f"/p/{plan.share_id}"),
        image_url=absolute_url(request, f"/p/{plan.share_id}/plan.png"),
    )
    response.headers["X-Robots-Tag"] = "noindex"
    return response


@router.get("/{share_id}/plan.png")
def shared_plan_image(share_id: str, download: bool = False, db: Session = Depends(get_db)):
    plan = _shared_plan(db, share_id)
    headers = {"Cache-Control": "public, max-age=60", "X-Robots-Tag": "noindex"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="dinner-plan-{plan.week_start.isoformat()}.png"'
    return Response(render_plan_image(plan), media_type="image/png", headers=headers)
