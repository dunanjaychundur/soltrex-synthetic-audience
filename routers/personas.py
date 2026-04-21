from fastapi import APIRouter
from services.persona_store import CLUSTERS, get_personas_for_cluster

router = APIRouter()

@router.get("/clusters")
def get_clusters():
    return {"clusters": [
        {"id": k, "label": v["label"], "description": v["description"], "color": v["color"]}
        for k, v in CLUSTERS.items()
    ]}

@router.get("/cluster/{cluster_id}")
def get_cluster_personas(cluster_id: str):
    personas = get_personas_for_cluster(cluster_id)
    return {"cluster_id": cluster_id, "count": len(personas), "personas": personas}
