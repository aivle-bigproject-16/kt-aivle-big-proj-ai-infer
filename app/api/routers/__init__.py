"""엔드포인트 정의. 라우터 하나가 리소스 하나를 맡는다.

- `infer` — `/infer/ct` · `/infer/rgb`
- `cells` — `/ai/cells/analyze`
- `health` — `/health`
"""
from app.api.routers import cells, health, infer


ROUTERS = (infer.router, cells.router, health.router)

__all__ = ["ROUTERS", "cells", "health", "infer"]
