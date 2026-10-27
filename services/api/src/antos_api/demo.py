"""Sample activity for a demonstration deployment.

Every item goes through the real pipeline (ingest, the 19-step loop, the audit
log), so a demo node behaves exactly like a live one. The data is illustrative,
and the actor on every record says so: ``system:demo-seed``.
"""

from datetime import timedelta
from functools import partial
from typing import Any

from antos_api import service
from antos_api.auth import Principal
from antos_core.contracts import SignalInput

SEEDER = Principal(subject="system:demo-seed", roles=frozenset({"analyst", "operator"}),
                   nation_id=None, method="api_key")

ALL_FIT = dict.fromkeys(["institutional_alignment", "linguistic_appropriateness",
                         "infrastructure_feasibility", "cultural_safety",
                         "regulatory_grounding", "resource_realism"], True)


def _sig(rt: service.Runtime, signal_type: str, source: str, minutes_ago: int,
         payload: dict[str, Any], kind: str = "formal_institution") -> SignalInput:
    return SignalInput.model_validate({
        "signal_type": signal_type, "source_id": source, "source_type": kind,
        "observed_at": rt.clock() - timedelta(minutes=minutes_ago), "payload": payload})


async def seed(rt: service.Runtime) -> list[str]:
    s = partial(_sig, rt)
    cases: list[dict[str, Any]] = [
        {"sector": "health", "objective": "Assess ICU capacity at Korle Bu Teaching Hospital",
         "local_fit": ALL_FIT, "signals": [
             s("bed_capacity_signal", "korle_bu_emr", 15, {"occupancy_rate": 0.84, "source_ref": "KBH-ICU-1026"}),
             s("bed_capacity_signal", "ghs_dhims2", 25, {"occupancy_rate": 0.85, "source_ref": "DHIMS-7731"})]},
        {"sector": "health", "objective": "Plan oxygen supply for Tamale Teaching Hospital",
         "signals": [
             s("drug_stock_level", "tth_pharmacy", 20, {"stock_days": 9, "essential": True, "safety_stock_days": 7, "source_ref": "TTH-O2"}),
             s("drug_stock_level", "ghs_dhims2", 35, {"stock_days": 9.5, "essential": True, "safety_stock_days": 7, "source_ref": "DHIMS-O2"})]},
        {"sector": "agriculture", "objective": "Release buffer maize stock in the Northern Region",
         "local_fit": ALL_FIT, "signals": [
             s("farmgate_price_signal", "nafco", 120, {"price_ghs": 620, "mom_change": 0.12, "source_ref": "NAFCO-W43"}),
             s("farmgate_price_signal", "esoko", 200, {"price_ghs": 640, "mom_change": 0.14, "source_ref": "ESOKO-118"}, "api_feed")]},
        {"sector": "finance", "objective": "Assess cedi pressure after weekend trading", "signals": [
            s("exchange_rate_signal", "bog_fx", 30, {"rate": 15.9, "depreciation_24h": 0.062, "source_ref": "BOG-FX-1026"}),
            s("exchange_rate_signal", "reuters_fx", 25, {"rate": 15.95, "depreciation_24h": 0.064, "source_ref": "RTRS-GHS"}, "api_feed")]},
        {"sector": "energy", "objective": "Schedule fuel imports for thermal plants", "signals": [
            s("fuel_stock_signal", "npa", 30, {"stock_days": 12, "source_ref": "NPA-1"}),
            s("fuel_stock_signal", "bost", 40, {"stock_days": 4, "source_ref": "BOST-9"}, "api_feed")]},
        {"sector": "transport", "objective": "Clear the truck backlog at the Aflao border", "signals": [
            s("border_crossing", "gra_customs", 90, {"wait_hours": 52, "source_ref": "GRA-AFL-22"}),
            s("border_crossing", "drivers_union", 60, {"wait_hours": 55, "source_ref": "GPRTU-AFL"}, "informal_operator")]},
        {"sector": "governance", "objective": "Verify district turnout figures", "signals": [
            s("electoral_signal", "ec_ghana", 300, {"turnout_rate": 0.61, "source_ref": "EC-D14"}),
            s("electoral_signal", "codeo", 280, {"turnout_rate": 0.79, "source_ref": "CODEO-D14"}, "community_source")]},
        {"sector": "ports", "objective": "Night-shift staffing plan for Tema port",
         "hae": {"worker_dignity_preserved": False}, "signals": [
             s("berth_occupancy", "gpha_tema", 10, {"occupancy_rate": 0.72, "source_ref": "TEMA-B1"})]},
    ]
    refs = []
    for case in cases:
        stored = await service.resolve(rt, SEEDER, service.ResolveBody(nation_id="GH", **case))
        refs.append(stored.audit_ref)
    return refs
