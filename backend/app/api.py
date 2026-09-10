"""API 路由。路由层只做参数接收和服务调用，不含业务逻辑。"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}
