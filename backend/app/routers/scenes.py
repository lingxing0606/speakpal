from fastapi import APIRouter, Depends

from ..schemas import SceneOut
from ..security import get_current_user
from ..services.scenes import public_scenes

router = APIRouter(prefix="/api", tags=["scenes"])


@router.get("/scenes", response_model=list[SceneOut])
def list_scenes(user=Depends(get_current_user)):
    return public_scenes()
