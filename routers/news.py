from fastapi import APIRouter
from services.news_service import refresh_news_for_all_clusters, get_cluster_news_context

router = APIRouter()

@router.post("/refresh")
def refresh_news():
    return refresh_news_for_all_clusters()

@router.get("/context/{cluster_id}")
def get_news_context(cluster_id: str):
    return {"cluster_id": cluster_id, "context": get_cluster_news_context(cluster_id)}
