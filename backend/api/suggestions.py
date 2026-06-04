from fastapi import APIRouter, Query

from clients.google_autocomplete import google_autocomplete


router = APIRouter(prefix="/api")


@router.get("/suggestions")
async def api_suggestions(
    q: str = Query(..., min_length=1),
    lat: float | None = None,
    lng: float | None = None,
    radius: int = 5000,
    limit: int = Query(10, ge=1, le=20)
):
    suggestions_raw = await google_autocomplete(q, lat, lng, radius)

    result = []
    for item in suggestions_raw[:limit]:
        pred = item.get("placePrediction", {})
        text_obj = pred.get("text", {})
        main = text_obj.get("text", "")
        secondary = text_obj.get("secondaryText", "")
        label = f"{main}, {secondary}" if secondary else main
        if label:
            result.append(label)

    return result
