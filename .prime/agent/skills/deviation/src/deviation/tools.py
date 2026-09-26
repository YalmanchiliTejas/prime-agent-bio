"""Manufacturing-domain retrieval interfaces for deviation investigations."""

from __future__ import annotations

import json
import os
from pathlib import Path
from statistics import mean
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class ManufacturingConnector(Protocol):
    def query(self, concept: str, criteria: dict[str, Any]) -> Any: ...


class LocalJsonConnector:
    """Reference connector for exported, read-only manufacturing context."""

    def __init__(self, root: str | Path | None = None) -> None:
        configured = os.environ.get("PRIME_DEVIATION_DATA_DIR")
        self.root = Path(root or configured or Path.cwd() / ".prime" / "deviation-data")

    def query(self, concept: str, criteria: dict[str, Any]) -> Any:
        path = self.root / f"{concept}.json"
        if not path.exists():
            return {"concept": concept, "criteria": criteria, "records": [], "status": "NOT_CONFIGURED"}
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload if isinstance(payload, list) else payload.get("records", [])
        matches = [record for record in records if _matches(record, criteria)]
        return {"concept": concept, "criteria": criteria, "records": matches, "status": "OK"}


class BioDemoConnector:
    """Read-only manufacturing connector backed by Bio-Demo's authorized API."""

    def __init__(self, base_url: str | None = None, timeout_seconds: float = 20) -> None:
        configured = base_url or os.environ.get("PRIME_DEVIATION_API_BASE")
        if not configured:
            raise ValueError("BioDemoConnector requires PRIME_DEVIATION_API_BASE or base_url")
        self.base_url = configured.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def query(self, concept: str, criteria: dict[str, Any]) -> Any:
        endpoint = f"{self.base_url}/api/agent/tools/{quote(concept, safe='')}"
        headers = {
            "Content-Type": "application/json",
            "X-Tenant-ID": os.environ.get("PRIME_DEVIATION_TENANT_ID", "demo-cdmo"),
            "X-Actor-ID": os.environ.get("PRIME_DEVIATION_ACTOR_ID", "deviation-agent"),
            "X-Roles": os.environ.get("PRIME_DEVIATION_ROLES", "agent"),
            "X-Site-IDs": os.environ.get("PRIME_DEVIATION_SITE_IDS", ""),
            "X-Clearances": os.environ.get("PRIME_DEVIATION_CLEARANCES", "internal"),
        }
        request = Request(
            endpoint,
            data=json.dumps({"criteria": criteria}).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Bio-Demo {concept} retrieval failed ({exc.code}): {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Bio-Demo {concept} retrieval unavailable: {exc.reason}") from exc


def _matches(record: dict[str, Any], criteria: dict[str, Any]) -> bool:
    for key, expected in criteria.items():
        if expected is None:
            continue
        if key == "query":
            haystack = json.dumps(record, sort_keys=True).lower()
            if str(expected).lower() not in haystack:
                return False
            continue
        if key in {"start", "end"}:
            timestamp = record.get("timestamp") or record.get("event_timestamp")
            if timestamp is None:
                return False
            if key == "start" and str(timestamp) < str(expected):
                return False
            if key == "end" and str(timestamp) > str(expected):
                return False
            continue
        actual = record.get(key)
        values = expected if isinstance(expected, list) else [expected]
        if isinstance(actual, list):
            if not set(map(str, values)) & set(map(str, actual)):
                return False
        elif str(actual) not in {str(value) for value in values}:
            return False
    return True


def _default_connector() -> ManufacturingConnector:
    if os.environ.get("PRIME_DEVIATION_API_BASE"):
        return BioDemoConnector()
    return LocalJsonConnector()


_connector: ManufacturingConnector = _default_connector()


def configure_connector(connector: ManufacturingConnector) -> None:
    global _connector
    _connector = connector


def _query(concept: str, **criteria: Any) -> Any:
    return _connector.query(concept, criteria)


def get_batch(batch_id: str) -> Any:
    return _query("batches", batch_id=batch_id)


def get_process_steps(batch_id: str, process_version: str | None = None) -> Any:
    return _query("process_steps", batch_id=batch_id, process_version=process_version)


def get_process_trace(batch_id: str, process_step: str | None = None, parameters: list[str] | None = None) -> Any:
    return _query("process_traces", batch_id=batch_id, process_step=process_step, parameters=parameters)


def get_equipment_history(equipment_id: str, start: str | None = None, end: str | None = None) -> Any:
    return _query("equipment_history", equipment_id=equipment_id, start=start, end=end)


def get_material_lineage(batch_id: str | None = None, material_lot: str | None = None) -> Any:
    return _query("material_lineage", batch_id=batch_id, material_lot=material_lot)


def get_lab_results(batch_id: str, tests: list[str] | None = None) -> Any:
    return _query("lab_results", batch_id=batch_id, tests=tests)


def find_similar_deviations(query: str, filters: dict[str, Any] | None = None) -> Any:
    return _query("deviations", query=query, **(filters or {}))


def get_previous_capas(deviation_ids: list[str] | None = None, equipment_id: str | None = None) -> Any:
    return _query("capas", deviation_id=deviation_ids, equipment_id=equipment_id)


def get_governing_documents(
    site: str | None = None,
    product: str | None = None,
    sponsor: str | None = None,
    document_types: list[str] | None = None,
) -> Any:
    return _query("governing_documents", site=site, product=product, sponsor=sponsor, document_type=document_types)


def find_related_batches(
    *,
    product: str | None = None,
    equipment: str | None = None,
    material_lot: str | None = None,
    supplier_lot: str | None = None,
    start: str | None = None,
    end: str | None = None,
    process_version: str | None = None,
    procedure: str | None = None,
) -> Any:
    return _query(
        "batch_relationships",
        product=product,
        equipment=equipment,
        material_lot=material_lot,
        supplier_lot=supplier_lot,
        start=start,
        end=end,
        process_version=process_version,
        procedure=procedure,
    )


def compare_batches(batch_ids: list[str], metrics: list[str]) -> dict[str, Any]:
    """Deterministically summarize numeric metrics from batch records."""
    response = _query("batch_metrics", batch_id=batch_ids)
    records = response.get("records", []) if isinstance(response, dict) else []
    by_metric: dict[str, Any] = {}
    for metric in metrics:
        values = [
            {"batch_id": row.get("batch_id"), "value": row.get(metric)}
            for row in records
            if isinstance(row.get(metric), (int, float))
        ]
        numeric = [item["value"] for item in values]
        by_metric[metric] = {
            "values": values,
            "count": len(numeric),
            "min": min(numeric) if numeric else None,
            "max": max(numeric) if numeric else None,
            "mean": mean(numeric) if numeric else None,
            "range": max(numeric) - min(numeric) if numeric else None,
        }
    return {"batch_ids": batch_ids, "metrics": by_metric, "source_status": response.get("status", "UNKNOWN")}


def get_process_knowledge(product: str, topic: str | None = None) -> Any:
    return _query("process_knowledge", product=product, topic=topic)
