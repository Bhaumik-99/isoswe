"""API Version 1 Router Aggregator"""

from fastapi import APIRouter

from app.api.v1.billing import router as billing_router
from app.api.v1.committee import router as committee_router
from app.api.v1.complaints import router as complaints_router
from app.api.v1.events import router as events_router
from app.api.v1.finance import router as finance_router
from app.api.v1.flats import router as flats_router
from app.api.v1.gate import router as gate_router
from app.api.v1.me import router as me_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.reconciliation import router as reconciliation_router
from app.api.v1.registry import router as registry_router
from app.api.v1.resident_visitors import router as resident_visitors_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(me_router)
api_v1_router.include_router(flats_router)
api_v1_router.include_router(events_router)
api_v1_router.include_router(finance_router)
api_v1_router.include_router(billing_router)
api_v1_router.include_router(complaints_router)
api_v1_router.include_router(notifications_router)
api_v1_router.include_router(reconciliation_router)
api_v1_router.include_router(registry_router)
api_v1_router.include_router(committee_router)
api_v1_router.include_router(gate_router)
api_v1_router.include_router(resident_visitors_router)
