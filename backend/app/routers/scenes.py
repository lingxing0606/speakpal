from fastapi import APIRouter, Depends, HTTPException

from ..schemas import SceneFramesOut, SceneOut
from ..security import get_current_user
from ..services.scenes import get_frames, public_scenes

router = APIRouter(prefix="/api", tags=["scenes"])


@router.get("/scenes", response_model=list[SceneOut])
def list_scenes(user=Depends(get_current_user)):
    return public_scenes()


@router.get("/scenes/{scene_id}/frames", response_model=SceneFramesOut)
def scene_frames(scene_id: str, user=Depends(get_current_user)):
    """句型脚手架：卡住时可以照着说的三种句式，不计分。"""
    frames = get_frames(scene_id)
    if frames is None:
        raise HTTPException(status_code=404, detail="场景不存在")
    return SceneFramesOut(scene_id=scene_id, frames=frames)
