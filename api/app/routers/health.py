from fastapi import APIRouter, Request

router = APIRouter()

VERSION = "2.0.0"


@router.get("/health")
async def health(request: Request) -> dict:
    body: dict = {"ok": True, "version": VERSION}
    if request.app.state.settings.self_hosted:
        body["selfHosted"] = True
    return body
