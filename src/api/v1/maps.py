import math
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

router = APIRouter()

class RouteSpot(BaseModel):
    name: str
    latitude: float
    longitude: float

@router.post("/routes/optimize")
async def optimize_route(spots: List[RouteSpot]):
    if len(spots) <= 2:
        return spots
    
    # TSP nearest neighbor greedy solver algorithm
    def calculate_distance(s1, s2):
        return math.sqrt((s1.latitude - s2.latitude)**2 + (s1.longitude - s2.longitude)**2)

    unvisited = spots[1:]
    ordered_route = [spots[0]]

    while unvisited:
        last = ordered_route[-1]
        min_dist = float('inf')
        nearest_idx = 0

        for i, node in enumerate(unvisited):
            dist = calculate_distance(last, node)
            if dist < min_dist:
                min_dist = dist
                nearest_idx = i
        
        ordered_route.append(unvisited.pop(nearest_idx))

    return ordered_route
