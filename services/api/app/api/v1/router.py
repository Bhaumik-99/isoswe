"""API Version 1 Router Aggregator"""

from fastapi import APIRouter

from app.api.v1.billing import router as billing_router
from app.api.v1.complaints import router as complaints_router
from app.api.v1.events import router as events_router
from app.api.v1.finance import router as finance_router
from app.api.v1.flats import router as flats_router
from app.api.v1.me import router as me_router
from app.api.v1.reconciliation import router as reconciliation_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(me_router)
api_v1_router.include_router(flats_router)
api_v1_router.include_router(events_router)
api_v1_router.include_router(finance_router)
api_v1_router.include_router(billing_router)
api_v1_router.include_router(complaints_router)
api_v1_router.include_router(reconciliation_router)
