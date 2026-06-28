from fastapi import APIRouter


router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/hello")
async def hello() -> dict[str, str]:
    return {"message": "learning agent chat ready"}
