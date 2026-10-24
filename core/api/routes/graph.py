from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api.routes.auth import optional_current_user
from core.logging_config import logger

# বাংলা মন্তব্য: ফ্রন্টএন্ডে নলেজ গ্রাফ ডেটা (Nodes & Edges) এবং লার্নিং পাথ এক্সপোজ করার API রাউটার।

router = APIRouter(prefix="/api/v1/graph", tags=["knowledge-graph"])

_graph_service = None


def get_graph_service():
    # বাংলা মন্তব্য: মেমরি ওভারহেড কমাতে GraphService অলসভাবে (lazy) লোড করা হচ্ছে।
    global _graph_service
    if _graph_service is None:
        from tools.graph_service import GraphService

        _graph_service = GraphService()
    return _graph_service


# বাংলা মন্তব্য: কাস্টম অথরাইজেশন ডিপেন্ডেন্সি হেল্পার
async def require_auth_token(current_user=Depends(optional_current_user)):
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return current_user


@router.get("/skills", response_model=dict[str, list[dict[str, Any]]])
async def get_skill_graph(user=Depends(require_auth_token)):
    """
    বাংলা মন্তব্য: ফ্রন্টএন্ডে ভিজ্যুয়ালাইজ করার জন্য গ্রাফের সমস্ত নোড এবং রিলেশনশিপ (Edges) ফেচ করবে।
    এটি React Flow বা D3.js এর উপযোগী ডেটা স্ট্রাকচার রিটার্ন করে।
    """
    try:
        # ড্রাই-রান বা মক মোডের জন্য ডামি ডেটা
        graph_svc = get_graph_service()
        if graph_svc.dry_run:
            return {
                "nodes": [
                    {
                        "id": "python",
                        "data": {"label": "Python", "category": "Language"},
                    },
                    {
                        "id": "fastapi",
                        "data": {"label": "FastAPI", "category": "Framework"},
                    },
                    {"id": "redis", "data": {"label": "Redis", "category": "Database"}},
                ],
                "edges": [
                    {
                        "id": "e1",
                        "source": "python",
                        "target": "fastapi",
                        "label": "PREREQUISITE",
                    },
                    {
                        "id": "e2",
                        "source": "fastapi",
                        "target": "redis",
                        "label": "INTEGRATES_WITH",
                    },
                ],
            }

        # রিয়েল ডাটাবেস থেকে ফেচ করার লজিক (Cypher Query)
        graph_svc = get_graph_service()
        async with graph_svc.driver.session() as session:
            result = await session.run(
                "MATCH (n:Skill) OPTIONAL MATCH (n)-[r]->(m:Skill) RETURN n, r, m LIMIT 100"
            )
            records = await result.data()

            nodes_dict = {}
            edges = []

            for record in records:
                n = record.get("n")
                if n and n.get("id") not in nodes_dict:
                    nodes_dict[n.get("id")] = {
                        "id": n.get("id"),
                        "data": {"label": n.get("name"), "category": n.get("category")},
                    }

                m = record.get("m")
                r = record.get("r")
                if m and r:
                    if m.get("id") not in nodes_dict:
                        nodes_dict[m.get("id")] = {
                            "id": m.get("id"),
                            "data": {
                                "label": m.get("name"),
                                "category": m.get("category"),
                            },
                        }
                    edges.append(
                        {
                            "id": f"{n.get('id')}-{m.get('id')}",
                            "source": n.get("id"),
                            "target": m.get("id"),
                            "label": type(r).__name__,
                        }
                    )

            return {"nodes": list(nodes_dict.values()), "edges": edges}

    except Exception as e:
        logger.error(f"Error fetching skill graph: {e!s}")
        raise HTTPException(status_code=500, detail="Failed to fetch knowledge graph") from e


@router.get("/path")
async def get_learning_path(
    start_skill: str = Query(..., description="Starting skill name"),
    end_skill: str = Query(..., description="Target skill name"),
    user=Depends(require_auth_token),
):
    """বাংলা মন্তব্য: দুটি স্কিলের মধ্যে অপ্টিমাইজড লার্নিং পাথ বের করবে।"""
    try:
        graph_svc = get_graph_service()
        path = await graph_svc.get_skill_path(start_skill, end_skill)
        if not path:
            raise HTTPException(
                status_code=404,
                detail=f"No path found between {start_skill} and {end_skill}",
            )
        return {"path": path}
    except Exception as e:
        logger.error(f"Error finding path: {e!s}")
        raise HTTPException(status_code=500, detail=str(e)) from e
