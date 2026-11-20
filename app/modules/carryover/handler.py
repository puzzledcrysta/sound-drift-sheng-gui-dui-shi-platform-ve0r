from fastapi import APIRouter
from app.inputs import Source
from .service import judge

router = APIRouter()


@router.post('/api/carryover')
def carryover(source: Source, baseline: str | None = None):
    return judge(source.raw(), baseline)
