from fastapi import APIRouter, Query, Depends
from src.middleware.auth import verify_firebase_token

router = APIRouter()

@router.get("/safety")
async def safety_score(city: str = Query(..., description="City to score"), token: dict = Depends(verify_firebase_token)):

    hash_val = len(city) % 3
    return {
        "city": city,
        "generalSafety": float(8.5 + hash_val * 0.4),
        "nightSafety": float(8.0 + hash_val * 0.3),
        "trafficIndex": "Mild Delays" if hash_val == 0 else "Moderate Traffic" if hash_val == 1 else "Heavy Transit",
        "weatherHazard": "Moderate (Windy)" if hash_val == 2 else "Low Risk",
        "gems": [
            {"name": f"{city.capitalize()} Secret Sunrise Cliff", "desc": "A quiet, spectacular valley view ideal for morning meditation"},
            {"name": "Old Heritage Alleyway", "desc": "19th century vintage buildings away from standard tourist maps"},
            {"name": "Cozy Riverbank Brews", "desc": "Local organic tea/coffee shop with relaxing wooden swing decks"},
        ]
    }
