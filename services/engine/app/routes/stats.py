from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_session
from ..security import require_api_token
from ..stats import collect_stats

router = APIRouter(prefix="/stats", tags=["stats"], dependencies=[Depends(require_api_token)])


@router.get("/filters")
def filters_stats(session: Session = Depends(get_session)) -> dict:
    return collect_stats(session).model_dump()
