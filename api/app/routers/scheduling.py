from fastapi import APIRouter, Depends, Request

from ..auth import optional_user
from ..templates import render_template

router = APIRouter(tags=["scheduling"])


@router.get("/scheduling")
def scheduling_page(request: Request, user=Depends(optional_user)):
    return render_template(
        request,
        "scheduling/index.html",
        {"user": user},
    )
