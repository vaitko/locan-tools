from fastapi import APIRouter

router = APIRouter()

VERSION = "2.0.0"


@router.get("/health")
async def health() -> dict:
    return {"ok": True, "version": VERSION}
