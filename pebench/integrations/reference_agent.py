from __future__ import annotations

import importlib
import json
import re
import sys
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

from pebench.utils.io import load_yaml
from pebench.utils.paths import DEFAULT_CATALOG_PATH, REPO_ROOT


REFERENCE_AGENT_ROOT = REPO_ROOT / ("PE" + "-MAS")
REFERENCE_AGENT_RUNTIME_DIR = REFERENCE_AGENT_ROOT / ".reference_agent_runtime"
REFERENCE_AGENT_COMPONENT_DB_DIR = REFERENCE_AGENT_ROOT / "core" / "knowledge" / "component_db"
REFERENCE_AGENT_RAW_EXPORT_DIR = REFERENCE_AGENT_COMPONENT_DB_DIR / "raw_exports"
REFERENCE_AGENT_READINESS_JSON = REFERENCE_AGENT_COMPONENT_DB_DIR / "mas_component_readiness.json"

EXPECTED_BOM_SLOTS = ("controller", "mosfet", "diode", "output_capacitor", "core")

BENCHMARK_COMPONENT_DETAILS: dict[str, dict[str, Any]] = {
    "UCC28740": {
        "raw_json": {
            "Topology": "Flyback",
            "Control Mode": "Primary-side regulated QR flyback",
            "Voltage - Input (Max)": "700 V",
        }
    },
    "NCP1342": {
        "raw_json": {
            "Topology": "Flyback",
            "Control Mode": "QR flyback",
            "Voltage - Input (Max)": "700 V",
        }
    },
    "STF7N65M2": {
        "raw_json": {
            "Technology": "MOSFET (Metal Oxide)",
            "FET Type": "N-Channel",
            "Drain to Source Voltage (Vdss)": "650 V",
            "Current - Continuous Drain (Id) @ 25°C": "5.5 A",
            "Rds On (Max) @ Id, Vgs": "1.0 ohm @ 2.5A, 10V",
            "Gate Charge (Qg) (Max) @ Vgs": "14 nC @ 10 V",
        }
    },
    "IPD60R380P7": {
        "raw_json": {
            "Technology": "MOSFET (Metal Oxide)",
            "FET Type": "N-Channel",
            "Drain to Source Voltage (Vdss)": "700 V",
            "Current - Continuous Drain (Id) @ 25°C": "8.3 A",
            "Rds On (Max) @ Id, Vgs": "380 mohms @ 3A, 10V",
            "Gate Charge (Qg) (Max) @ Vgs": "16.4 nC @ 10 V",
        }
    },
    "MBR20100CT": {
        "raw_json": {
            "Technology": "Schottky",
            "Voltage - DC Reverse (Vr) (Max)": "100 V",
            "Current - Average Rectified (Io)": "10 A",
            "Voltage - Forward (Vf) (Max) @ If": "0.85 V @ 10 A",
            "Reverse Recovery Time (trr)": "35 ns",
        }
    },
    "STPS8H100": {
        "raw_json": {
            "Technology": "Schottky",
            "Voltage - DC Reverse (Vr) (Max)": "100 V",
            "Current - Average Rectified (Io)": "8 A",
            "Voltage - Forward (Vf) (Max) @ If": "0.68 V @ 8 A",
            "Reverse Recovery Time (trr)": "25 ns",
        }
    },
    "EEU-FR1E221": {
        "raw_json": {
            "Capacitance": "220 uF",
            "Voltage - Rated": "25 V",
            "Ripple Current": "1.35 A",
            "Technology": "Aluminum Electrolytic",
        }
    },
    "EEU-FR1V471": {
        "raw_json": {
            "Capacitance": "470 uF",
            "Voltage - Rated": "35 V",
            "Ripple Current": "2.0 A",
            "Technology": "Aluminum Electrolytic",
        }
    },
    "EFD20_3C95": {
        "raw_json": {
            "Technology": "Ferrite Core",
            "Ae_mm2": "31.0",
            "Ve_mm3": "2500",
            "Max Power": "18 W",
        }
    },
    "EFD25_3C95": {
        "raw_json": {
            "Technology": "Ferrite Core",
            "Ae_mm2": "52.0",
            "Ve_mm3": "4800",
            "Max Power": "40 W",
        }
    },
}


def reference_agent_present() -> bool:
    return REFERENCE_AGENT_ROOT.exists()


def _ensure_reference_agent_on_path() -> None:
    if reference_agent_present() and str(REFERENCE_AGENT_ROOT) not in sys.path:
        sys.path.insert(0, str(REFERENCE_AGENT_ROOT))


def _optional_import(module_name: str) -> Any | None:
    if not reference_agent_present():
        return None
    _ensure_reference_agent_on_path()
    try:
        return importlib.import_module(module_name)
    except Exception:
        return None


@lru_cache(maxsize=1)
def get_reference_agent_assets() -> dict[str, Any]:
    assets: dict[str, Any] = {
        "present": reference_agent_present(),
        "root": REFERENCE_AGENT_ROOT,
        "runtime_dir": REFERENCE_AGENT_RUNTIME_DIR,
        "modules": {},
    }
    module_names = {
        "flyback_math": "core.flyback_mas.tools.flyback_math",
        "formula_guardrails": "core.flyback_mas.formula_guardrails",
        "input_semantics": "core.flyback_mas.tools.input_semantics",
        "efficiency_calculator": "core.flyback_mas.tools.flyback_efficiency_calculator",
        "plecs_interface": "core.flyback_mas.tools.plecs_interface",
        "plecs_mcp_client": "core.flyback_mas.tools.plecs_mcp_client",
        "digikey_local_db": "core.utils.digikey_local_db",
        "component_rag_bridge": "core.utils.component_rag_bridge",
        "design_peer_review_tools": "core.skills.design_peer_review.tools",
        "simulation_consistency_tools": "core.skills.simulation_consistency_checker.tools",
        "final_report_writer_tools": "core.skills.final_report_writer.tools",
    }
    for key, module_name in module_names.items():
        module = _optional_import(module_name)
        if module is not None:
            assets["modules"][key] = module

    assets["available"] = {
        "math": "flyback_math" in assets["modules"],
        "guardrails": "formula_guardrails" in assets["modules"],
        "input_semantics": "input_semantics" in assets["modules"],
        "efficiency": "efficiency_calculator" in assets["modules"],
        "plecs_xmlrpc": "plecs_interface" in assets["modules"],
        "plecs_mcp": "plecs_mcp_client" in assets["modules"],
        "digikey": "digikey_local_db" in assets["modules"],
        "rag": "component_rag_bridge" in assets["modules"],
        "peer_review": "design_peer_review_tools" in assets["modules"],
        "sim_consistency": "simulation_consistency_tools" in assets["modules"],
        "report_writer": "final_report_writer_tools" in assets["modules"],
    }
    return assets


def build_reference_agent_specs(task: dict[str, Any]) -> dict[str, Any]:
    spec = task["structured_spec"]
    return {
        "is_chitchat": False,
        "response_text": None,
        "input_voltage_min": float(spec["input_range_volts"]["min"]),
        "input_voltage_max": float(spec["input_range_volts"]["max"]),
        "output_voltage": float(spec["output"]["voltage_v"]),
        "output_current": float(spec["output"]["current_a"]),
        "efficiency_target": float(spec["targets"]["efficiency_percent"]) / 100.0,
        "max_ripple_voltage": float(spec["targets"]["ripple_mv"]) / 1000.0,
        "isolation": True,
        "application_type": "benchmark",
    }


def build_reference_agent_design(task: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    theory = candidate["theoretical_design"]
    output_voltage = float(task["structured_spec"]["output"]["voltage_v"])
    reflected_output_voltage = (
        candidate.get("metadata", {})
        .get("reference_agent_design", {})
        .get("reflected_output_voltage")
    )
    if reflected_output_voltage is None:
        reflected_output_voltage = theory["turns_ratio_primary_to_secondary"] * (output_voltage + 1.0)

    return {
        "topology": "Flyback",
        "switching_frequency": float(theory["switching_frequency_khz"]) * 1000.0,
        "primary_inductance": float(theory["magnetizing_inductance_uh"]) * 1e-6,
        "primary_peak_current": float(theory["primary_peak_current_a"]),
        "turns_ratio": float(theory["turns_ratio_primary_to_secondary"]),
        "max_duty_cycle": float(theory["duty_cycle_max"]),
        "ripple_factor": float(
            candidate.get("metadata", {}).get("reference_agent_design", {}).get("ripple_factor", 0.4)
        ),
        "magnetizing_current_ripple": float(
            candidate.get("metadata", {})
            .get("reference_agent_design", {})
            .get("magnetizing_current_ripple", 0.0)
        ),
        "snubber_r": float(candidate.get("metadata", {}).get("reference_agent_design", {}).get("snubber_r", 1000.0)),
        "snubber_c": float(candidate.get("metadata", {}).get("reference_agent_design", {}).get("snubber_c", 1e-9)),
        "reflected_output_voltage": float(reflected_output_voltage),
    }


def _nested_raw_row(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("raw_json")
    if isinstance(raw, dict):
        payload = raw
    else:
        try:
            payload = json.loads(str(raw or ""))
        except Exception:
            payload = {}
    nested = payload.get("Raw Row JSON")
    if isinstance(nested, str):
        try:
            nested_payload = json.loads(nested)
            if isinstance(nested_payload, dict):
                return nested_payload
        except Exception:
            pass
    if payload:
        return payload if isinstance(payload, dict) else {}
    if isinstance(row, dict):
        return dict(row)
    return payload if isinstance(payload, dict) else {}


def _extract_float(value: Any, unit_scale: dict[str, float] | None = None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower()
    if not text:
        return None
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*([a-zµμΩohm/]+)?", text.replace(",", ""))
    if not match:
        return None
    try:
        numeric = float(match.group(1))
    except Exception:
        return None
    unit = str(match.group(2) or "")
    if unit_scale:
        for token, scale in unit_scale.items():
            if token in unit:
                return numeric * scale
    return numeric


def _first_numeric(raw: dict[str, Any], keys: list[str], unit_scale: dict[str, float] | None = None) -> float | None:
    for key in keys:
        if key in raw and raw.get(key) not in (None, "", "-"):
            value = _extract_float(raw.get(key), unit_scale)
            if value is not None:
                return value
    return None


def _reference_agent_component_dict(bom_items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    alias_map = {
        "controller": "controller",
        "mosfet": "mosfet",
        "diode": "diode",
        "output_capacitor": "output_cap",
        "output_cap": "output_cap",
        "input_cap": "input_cap",
        "core": "transformer",
        "transformer": "transformer",
        "clamp_snubber": "clamp_snubber",
    }
    for item in bom_items:
        alias = alias_map.get(str(item.get("category") or ""))
        if not alias:
            continue
        entry = dict(item.get("attributes") or {})
        entry.setdefault("part_number", item.get("part_id"))
        entry.setdefault("title", item.get("title"))
        entry.setdefault("price", item.get("price"))
        entry.setdefault("stock", item.get("stock"))
        mapped[alias] = entry
    return mapped


def build_reference_agent_bom(candidate: dict[str, Any]) -> dict[str, dict[str, Any]]:
    metadata_bom = candidate.get("metadata", {}).get("reference_agent_bom")
    if isinstance(metadata_bom, dict) and metadata_bom:
        return metadata_bom
    return _reference_agent_component_dict(candidate.get("bom", []))


def _load_benchmark_catalog() -> dict[str, list[dict[str, Any]]]:
    catalog = load_yaml(DEFAULT_CATALOG_PATH)
    return {
        "controller": catalog["controllers"],
        "mosfet": catalog["mosfets"],
        "diode": catalog["diodes"],
        "output_capacitor": catalog["output_capacitors"],
        "core": catalog["cores"],
    }


def _fallback_catalog_item(category: str, task: dict[str, Any]) -> dict[str, Any]:
    catalog = _load_benchmark_catalog()
    items = catalog[category]
    power_w = task["structured_spec"]["output"]["power_w"]
    current_a = task["structured_spec"]["output"]["current_a"]
    ripple_mv = float(task["structured_spec"]["targets"]["ripple_mv"])
    if category == "mosfet":
        items = sorted(items, key=lambda item: (item["voltage_rating_v"], item["current_rating_a"]))
    elif category == "diode":
        items = sorted(items, key=lambda item: (item["voltage_rating_v"], item["current_rating_a"]))
    elif category == "output_capacitor":
        items = sorted(items, key=lambda item: (item["voltage_rating_v"], item["ripple_current_a"]))
    elif category == "core":
        items = sorted(items, key=lambda item: (item["max_power_w"], item["cost_usd"]))
    else:
        items = sorted(items, key=lambda item: item["cost_usd"])
    if category == "core" and (power_w >= 10 or current_a >= 1.0):
        return items[-1]
    if category == "output_capacitor" and (current_a >= 1.0 or ripple_mv <= 60.0 or power_w >= 10):
        return items[-1]
    if category in {"mosfet", "core"} or power_w > 18 or current_a > 1.5:
        return items[-1]
    return items[0]


def _fallback_bom_entry(category: str, task: dict[str, Any]) -> dict[str, Any]:
    item = _fallback_catalog_item(category, task)
    details = BENCHMARK_COMPONENT_DETAILS.get(item["part_id"], {})
    raw_json = dict(details.get("raw_json") or {})
    if category == "mosfet":
        attributes = {
            "Vds": item["voltage_rating_v"],
            "Id": item["current_rating_a"],
            "price": item["cost_usd"],
            "raw_json": raw_json,
        }
    elif category == "diode":
        attributes = {
            "voltage_rating": item["voltage_rating_v"],
            "current_rating": item["current_rating_a"],
            "price": item["cost_usd"],
            "Vr": item["voltage_rating_v"],
            "If": item["current_rating_a"],
            "raw_json": raw_json,
        }
    elif category == "output_capacitor":
        attributes = {
            "Value": 470e-6 if item["part_id"] == "EEU-FR1V471" else 220e-6,
            "voltage_rating": item["voltage_rating_v"],
            "ripple_current_a": item["ripple_current_a"],
            "price": item["cost_usd"],
            "raw_json": raw_json,
        }
    elif category == "core":
        attributes = {
            "max_power_w": item["max_power_w"],
            "price": item["cost_usd"],
            "raw_json": raw_json,
        }
    elif category == "controller":
        attributes = {
            "price": item["cost_usd"],
            "raw_json": raw_json,
        }
    else:
        attributes = {"price": item["cost_usd"]}
    return {
        "category": category,
        "part_id": item["part_id"],
        "title": item["part_id"],
        "source": "benchmark_catalog",
        "price": item.get("cost_usd"),
        "attributes": attributes,
    }


def _row_to_bom_item(category: str, row: dict[str, Any]) -> dict[str, Any]:
    raw_json = _nested_raw_row(row)
    attributes = {
        **row,
        "raw_json": raw_json,
    }
    if category == "mosfet":
        voltage_rating = _extract_row_voltage_rating(row, ["Drain to Source Voltage (Vdss)", "Vds"])
        current_rating = _extract_row_current_rating(row, ["Current - Continuous Drain (Id) @ 25°C", "Id"])
        if voltage_rating is not None:
            attributes.setdefault("Vds", voltage_rating)
        if current_rating is not None:
            attributes.setdefault("Id", current_rating)
    elif category == "diode":
        voltage_rating = _extract_row_voltage_rating(row, ["Voltage - DC Reverse (Vr) (Max)", "Vr"])
        current_rating = _extract_row_current_rating(row, ["Current - Average Rectified (Io)", "If"])
        if voltage_rating is not None:
            attributes.setdefault("voltage_rating", voltage_rating)
            attributes.setdefault("Vr", voltage_rating)
        if current_rating is not None:
            attributes.setdefault("current_rating", current_rating)
            attributes.setdefault("If", current_rating)
    elif category == "output_capacitor":
        cap_value_f = _first_numeric(
            raw_json,
            ["Capacitance", "Value"],
            {"uf": 1e-6, "µf": 1e-6, "nf": 1e-9, "pf": 1e-12, "f": 1.0},
        )
        voltage_rating = _extract_row_voltage_rating(row, ["Voltage - Rated", "voltage_rating"])
        if cap_value_f is not None:
            attributes.setdefault("Value", cap_value_f)
        if voltage_rating is not None:
            attributes.setdefault("voltage_rating", voltage_rating)
    elif category == "core":
        max_power = _first_numeric(raw_json, ["Max Power", "max_power_w"], {"w": 1.0})
        if max_power is not None:
            attributes.setdefault("max_power_w", max_power)

    return {
        "category": category,
        "part_id": row.get("part_number") or row.get("title") or f"{category}_unknown",
        "title": row.get("title"),
        "source": "reference_agent_local_db",
        "price": row.get("price"),
        "stock": row.get("stock"),
        "attributes": attributes,
    }


def _slot_text_blob(row: dict[str, Any]) -> str:
    raw = _nested_raw_row(row)
    parts = [
        str(row.get("part_number") or ""),
        str(row.get("title") or ""),
        str(row.get("description") or ""),
        json.dumps(raw, sort_keys=True, ensure_ascii=False),
    ]
    return " ".join(parts).lower()


def _extract_row_voltage_rating(row: dict[str, Any], keys: list[str] | None = None) -> float | None:
    raw = _nested_raw_row(row)
    search_keys = keys or [
        "Drain to Source Voltage (Vdss)",
        "Voltage - DC Reverse (Vr) (Max)",
        "Voltage - Rated",
        "Vds",
        "Vr",
    ]
    value = _first_numeric(raw, search_keys, {"kv": 1000.0, "v": 1.0})
    if value is not None:
        return value
    return _extract_float(row.get("vds"), {"kv": 1000.0, "v": 1.0})


def _extract_row_current_rating(row: dict[str, Any], keys: list[str] | None = None) -> float | None:
    raw = _nested_raw_row(row)
    search_keys = keys or [
        "Current - Continuous Drain (Id) @ 25°C",
        "Current - Average Rectified (Io)",
        "Id",
        "If",
        "Current - Output",
    ]
    value = _first_numeric(raw, search_keys, {"ma": 1e-3, "a": 1.0})
    if value is not None:
        return value
    parsed = _extract_float(row.get("id_current"), {"ma": 1e-3, "a": 1.0})
    if parsed is None:
        return None
    # The optional local DB sometimes stores milliamps as plain numbers.
    if parsed > 100.0:
        return parsed / 1000.0
    return parsed


def _controller_slot_validator(row: dict[str, Any], task: dict[str, Any], design: dict[str, Any]) -> tuple[bool, list[str]]:
    del task, design
    text = _slot_text_blob(row)
    reasons: list[str] = []
    if "flyback" not in text and "offline" not in text and "primary-side" not in text:
        reasons.append("controller_missing_flyback_or_offline_cue")
    if "buck adjustable" in text and "flyback" not in text:
        reasons.append("controller_is_plain_buck_regulator")
    if "pmic" in text:
        reasons.append("controller_is_generic_pmic")
    return not reasons, reasons


def _mosfet_slot_validator(row: dict[str, Any], task: dict[str, Any], design: dict[str, Any]) -> tuple[bool, list[str]]:
    text = _slot_text_blob(row)
    reasons: list[str] = []
    required_vds = 1.2 * (
        float(task["structured_spec"]["input_range_volts"]["max"])
        + float(design.get("reflected_output_voltage") or 0.0)
    )
    required_id = 1.5 * float(design.get("primary_peak_current") or 0.0)
    if "mosfet" not in text and "sicfet" not in text:
        reasons.append("mosfet_slot_missing_fet_type")
    if "p-ch" in text or "p-channel" in text:
        reasons.append("mosfet_slot_selected_p_channel")
    if any(token in text for token in ["dual", "half bridge", "full bridge", "module"]):
        reasons.append("mosfet_slot_selected_multi_device_package")
    voltage_rating = _extract_row_voltage_rating(row, ["Drain to Source Voltage (Vdss)", "Vds"])
    if voltage_rating is None or voltage_rating < required_vds:
        reasons.append("mosfet_slot_voltage_below_margin")
    current_rating = _extract_row_current_rating(row, ["Current - Continuous Drain (Id) @ 25°C", "Id"])
    if current_rating is None or current_rating < required_id:
        reasons.append("mosfet_slot_current_below_margin")
    return not reasons, reasons


def _diode_slot_validator(row: dict[str, Any], task: dict[str, Any], design: dict[str, Any]) -> tuple[bool, list[str]]:
    text = _slot_text_blob(row)
    reasons: list[str] = []
    turns_ratio = max(float(design.get("turns_ratio") or 1.0), 1.0)
    vout = float(task["structured_spec"]["output"]["voltage_v"])
    iout = float(task["structured_spec"]["output"]["current_a"])
    required_vr = 1.2 * (vout + float(task["structured_spec"]["input_range_volts"]["max"]) / turns_ratio)
    required_if = 1.5 * iout
    if any(token in text for token in ["mosfet", "zener", "tvs", "esd"]):
        reasons.append("diode_slot_selected_wrong_device_family")
    voltage_rating = _extract_row_voltage_rating(row, ["Voltage - DC Reverse (Vr) (Max)", "Vr"])
    if voltage_rating is None or voltage_rating < required_vr:
        reasons.append("diode_slot_voltage_below_margin")
    current_rating = _extract_row_current_rating(row, ["Current - Average Rectified (Io)", "If"])
    if current_rating is None or current_rating < required_if:
        reasons.append("diode_slot_current_below_margin")
    return not reasons, reasons


def _output_cap_slot_validator(row: dict[str, Any], task: dict[str, Any], design: dict[str, Any]) -> tuple[bool, list[str]]:
    del design
    raw = _nested_raw_row(row)
    text = _slot_text_blob(row)
    reasons: list[str] = []
    vout = float(task["structured_spec"]["output"]["voltage_v"])
    iout = float(task["structured_spec"]["output"]["current_a"])
    ripple_target_v = float(task["structured_spec"]["targets"]["ripple_mv"]) / 1000.0
    fsw_hz = 1000.0 * (
        float(task["structured_spec"]["switching_frequency_khz"]["min"])
        + float(task["structured_spec"]["switching_frequency_khz"]["max"])
    ) / 2.0
    min_cap_f = max(100e-6, 1.2 * iout / (8.0 * fsw_hz * max(ripple_target_v, 0.005)))
    cap_value_f = _first_numeric(
        raw,
        ["Capacitance", "Value"],
        {"uf": 1e-6, "µf": 1e-6, "nf": 1e-9, "pf": 1e-12, "f": 1.0},
    )
    if cap_value_f is None or cap_value_f < min_cap_f:
        reasons.append("output_cap_slot_capacitance_too_small")
    voltage_rating = _extract_row_voltage_rating(row, ["Voltage - Rated", "voltage_rating"])
    if voltage_rating is None or voltage_rating < 1.25 * vout:
        reasons.append("output_cap_slot_voltage_below_margin")
    if any(token in text for token in ["100pf", "1000pf", "0.033uf", "0.1uf", "0402", "0603", "0805"]):
        reasons.append("output_cap_slot_looks_like_small_signal_cap")
    return not reasons, reasons


def _core_slot_validator(row: dict[str, Any], task: dict[str, Any], design: dict[str, Any]) -> tuple[bool, list[str]]:
    del design
    raw = _nested_raw_row(row)
    text = _slot_text_blob(row)
    reasons: list[str] = []
    power_w = float(task["structured_spec"]["output"]["power_w"])
    if "laminated" in text or "power xfmr" in text:
        reasons.append("core_slot_selected_finished_line_transformer")
    if "ferrite" not in text and "efd" not in text and "e core" not in text and "e " not in text:
        reasons.append("core_slot_missing_ferrite_core_signal")
    max_power = _first_numeric(raw, ["Max Power", "max_power_w"], {"w": 1.0})
    if max_power is not None and max_power < 1.15 * power_w:
        reasons.append("core_slot_power_margin_too_low")
    return not reasons, reasons


SLOT_VALIDATORS: dict[str, Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], tuple[bool, list[str]]]] = {
    "controller": _controller_slot_validator,
    "mosfet": _mosfet_slot_validator,
    "diode": _diode_slot_validator,
    "output_capacitor": _output_cap_slot_validator,
    "core": _core_slot_validator,
}


def _select_local_component_for_slot(
    digikey: Any,
    *,
    category: str,
    component_type: str,
    min_vds: float,
    min_id: float,
    text_query: str,
    preference_profile: dict[str, Any],
    task: dict[str, Any],
    design: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    rows = digikey.query_local_components(
        component_type,
        min_vds=min_vds,
        min_id=min_id,
        limit=25,
        preference_profile=preference_profile,
        text_query=text_query,
    )
    diagnostics: list[dict[str, Any]] = []
    validator = SLOT_VALIDATORS[category]
    for row in rows:
        ok, reasons = validator(row, task, design)
        diagnostics.append(
            {
                "category": category,
                "part_number": row.get("part_number"),
                "accepted": ok,
                "reasons": reasons,
            }
        )
        if ok:
            return _row_to_bom_item(category, row), diagnostics
    return None, diagnostics


def _pre_sim_grounding_validation(task: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    bom_lookup = {item["category"]: item for item in candidate.get("bom", [])}
    design = build_reference_agent_design(task, candidate)
    claims = candidate["final_claimed_metrics"]
    violations: list[dict[str, Any]] = []

    for slot in EXPECTED_BOM_SLOTS:
        item = bom_lookup.get(slot)
        if item is None:
            violations.append({"slot": slot, "reason": "missing_slot"})
            continue
        ok, reasons = SLOT_VALIDATORS[slot](item.get("attributes") or item, task, design)
        for reason in reasons:
            violations.append({"slot": slot, "reason": reason})

    mosfet = bom_lookup.get("mosfet", {})
    diode = bom_lookup.get("diode", {})
    output_cap = bom_lookup.get("output_capacitor", {})
    mosfet_vds = _extract_row_voltage_rating(mosfet.get("attributes") or mosfet, ["Drain to Source Voltage (Vdss)", "Vds"])
    mosfet_id = _extract_row_current_rating(mosfet.get("attributes") or mosfet, ["Current - Continuous Drain (Id) @ 25°C", "Id"])
    diode_vr = _extract_row_voltage_rating(diode.get("attributes") or diode, ["Voltage - DC Reverse (Vr) (Max)", "Vr"])
    diode_if = _extract_row_current_rating(diode.get("attributes") or diode, ["Current - Average Rectified (Io)", "If"])
    output_cap_raw = _nested_raw_row(output_cap.get("attributes") or output_cap)
    output_cap_value_f = _first_numeric(
        output_cap_raw,
        ["Capacitance", "Value"],
        {"uf": 1e-6, "µf": 1e-6, "nf": 1e-9, "pf": 1e-12, "f": 1.0},
    )
    output_cap_voltage = _extract_row_voltage_rating(output_cap.get("attributes") or output_cap, ["Voltage - Rated", "voltage_rating"])

    if mosfet_vds is None or mosfet_vds < 1.2 * float(claims["mosfet_voltage_stress_v"]):
        violations.append({"slot": "mosfet", "reason": "mosfet_vds_margin"})
    if mosfet_id is None or mosfet_id < 1.5 * float(candidate["theoretical_design"]["primary_peak_current_a"]):
        violations.append({"slot": "mosfet", "reason": "mosfet_id_margin"})
    if diode_vr is None or diode_vr < 1.2 * float(claims["diode_reverse_voltage_v"]):
        violations.append({"slot": "diode", "reason": "diode_reverse_voltage_margin"})
    if diode_if is None or diode_if < 1.5 * float(task["structured_spec"]["output"]["current_a"]):
        violations.append({"slot": "diode", "reason": "diode_forward_current_margin"})
    if output_cap_value_f is None or output_cap_value_f < 100e-6:
        violations.append({"slot": "output_capacitor", "reason": "output_cap_ripple_formula"})
    if output_cap_voltage is None or output_cap_voltage < 1.25 * float(task["structured_spec"]["output"]["voltage_v"]):
        violations.append({"slot": "output_capacitor", "reason": "output_cap_voltage_margin"})

    return {"passed": not violations, "violations": violations}


def _repair_invalid_bom_slots(task: dict[str, Any], candidate: dict[str, Any], validation: dict[str, Any]) -> list[dict[str, Any]]:
    bom_lookup = {item["category"]: item for item in candidate.get("bom", [])}
    bad_slots = {entry["slot"] for entry in validation["violations"]}
    for slot in bad_slots:
        if slot in EXPECTED_BOM_SLOTS:
            bom_lookup[slot] = _fallback_bom_entry(slot, task)
    repaired: list[dict[str, Any]] = []
    for slot in EXPECTED_BOM_SLOTS:
        if slot in bom_lookup:
            repaired.append(bom_lookup[slot])
    return repaired


def _estimate_dc_bus_min(task: dict[str, Any]) -> float:
    vin_min = float(task["structured_spec"]["input_range_volts"]["min"])
    domain = str(task["structured_spec"]["input_range_volts"]["domain"]).lower()
    if domain == "dc":
        return vin_min
    return max(vin_min * 1.414 - 20.0, 50.0)


def _estimate_dc_bus_max(task: dict[str, Any]) -> float:
    vin_max = float(task["structured_spec"]["input_range_volts"]["max"])
    domain = str(task["structured_spec"]["input_range_volts"]["domain"]).lower()
    if domain == "dc":
        return vin_max
    return vin_max * 1.414


def _repair_theory_and_magnetics(
    task: dict[str, Any],
    benchmark_design: dict[str, Any],
    reference_agent_design: dict[str, Any],
) -> list[str]:
    constraints = task["structured_spec"]["constraints"]
    output = task["structured_spec"]["output"]
    notes: list[str] = []

    max_duty = float(constraints["max_duty_cycle"])
    if float(benchmark_design["duty_cycle_max"]) > max_duty:
        benchmark_design["duty_cycle_max"] = round(max(0.05, max_duty - 0.02), 3)
        notes.append("clamped_duty_cycle_to_constraint_margin")

    dc_bus_max = _estimate_dc_bus_max(task)
    max_diode_reverse_voltage = float(constraints["max_diode_reverse_voltage_v"])
    output_voltage = float(output["voltage_v"])
    max_allowed_reflected_voltage = 0.9 * float(constraints["max_mosfet_voltage_v"]) - dc_bus_max
    if max_allowed_reflected_voltage > output_voltage + 1.0:
        max_turns_ratio = max_allowed_reflected_voltage / (output_voltage + 1.0)
    else:
        max_turns_ratio = float(benchmark_design["turns_ratio_primary_to_secondary"])

    min_diode_denominator = max(8.0, 0.92 * max_diode_reverse_voltage - output_voltage)
    min_turns_ratio_for_diode = dc_bus_max / min_diode_denominator
    current_turns_ratio = float(benchmark_design["turns_ratio_primary_to_secondary"])
    repaired_turns_ratio = max(current_turns_ratio, min_turns_ratio_for_diode)
    repaired_turns_ratio = min(repaired_turns_ratio, max_turns_ratio)
    if repaired_turns_ratio > current_turns_ratio + 0.05:
        benchmark_design["turns_ratio_primary_to_secondary"] = round(repaired_turns_ratio, 3)
        notes.append("raised_turns_ratio_for_diode_margin")

    benchmark_design["turns_ratio_primary_to_secondary"] = max(
        1.05,
        float(benchmark_design["turns_ratio_primary_to_secondary"]),
    )
    reference_agent_design["reflected_output_voltage"] = round(
        float(benchmark_design["turns_ratio_primary_to_secondary"]) * (output_voltage + 1.0),
        3,
    )

    power_w = float(output["power_w"])
    current_i_pk = float(benchmark_design["primary_peak_current_a"])
    current_lp_uh = float(benchmark_design["magnetizing_inductance_uh"])
    max_i_pk = float(constraints["max_primary_peak_current_a"])
    domain = str(task["structured_spec"]["input_range_volts"]["domain"]).lower()
    desired_i_pk_floor = 0.7 if power_w <= 6.0 else 0.95
    if domain == "dc" and power_w >= 8.0:
        desired_i_pk_floor = 1.1
    desired_i_pk = min(max_i_pk * 0.78, max(current_i_pk, desired_i_pk_floor))
    if (current_lp_uh > 2000.0 or current_i_pk < desired_i_pk_floor) and desired_i_pk > current_i_pk:
        scale = (current_i_pk / desired_i_pk) ** 2 if current_i_pk > 0 else 1.0
        repaired_lp_uh = max(120.0, current_lp_uh * scale)
        benchmark_design["primary_peak_current_a"] = round(desired_i_pk, 3)
        benchmark_design["magnetizing_inductance_uh"] = round(repaired_lp_uh, 2)
        notes.append("rebalanced_primary_current_and_magnetizing_inductance")

    frequency_khz = float(benchmark_design["switching_frequency_khz"])
    if frequency_khz < float(task["structured_spec"]["switching_frequency_khz"]["min"]):
        benchmark_design["switching_frequency_khz"] = float(task["structured_spec"]["switching_frequency_khz"]["min"])
        notes.append("clamped_switching_frequency_low")
    if frequency_khz > float(task["structured_spec"]["switching_frequency_khz"]["max"]):
        benchmark_design["switching_frequency_khz"] = float(task["structured_spec"]["switching_frequency_khz"]["max"])
        notes.append("clamped_switching_frequency_high")

    return notes


def _build_claim_metrics_metadata(
    *,
    status: str,
    metric_sources: dict[str, str],
) -> dict[str, Any]:
    return {
        "status": status,
        "estimated_only": status == "estimated_only",
        "metric_sources": metric_sources,
    }


def build_runtime_asset_snapshot() -> dict[str, Any]:
    events_path = REFERENCE_AGENT_RUNTIME_DIR / "events.jsonl"
    metrics_path = REFERENCE_AGENT_RUNTIME_DIR / "metrics.json"
    reports_dir = REFERENCE_AGENT_RUNTIME_DIR / "reports"
    snapshot = {
        "runtime_dir_exists": REFERENCE_AGENT_RUNTIME_DIR.exists(),
        "metrics_path": str(metrics_path),
        "events_path": str(events_path),
        "reports_dir": str(reports_dir),
        "reports_dir_exists": reports_dir.exists(),
        "events_present": events_path.exists(),
        "metrics_present": metrics_path.exists(),
    }
    if metrics_path.exists():
        try:
            snapshot["historical_metrics"] = json.loads(metrics_path.read_text(encoding="utf-8"))
        except Exception:
            snapshot["historical_metrics"] = None
    if events_path.exists():
        try:
            with events_path.open("r", encoding="utf-8") as handle:
                lines = handle.readlines()
            snapshot["event_count"] = len(lines)
            snapshot["recent_events"] = [line.strip() for line in lines[-3:]]
        except Exception:
            snapshot["event_count"] = None
            snapshot["recent_events"] = []
    return snapshot


def _inventory_entry(
    *,
    name: str,
    role: str,
    path: Path | None = None,
    module_key: str | None = None,
    note: str,
) -> dict[str, Any]:
    assets = get_reference_agent_assets()
    present = False
    if module_key is not None:
        present = module_key in assets["modules"]
    elif path is not None:
        present = path.exists()
    return {
        "name": name,
        "role": role,
        "present": present,
        "path": str(path) if path is not None else None,
        "module_key": module_key,
        "note": note,
    }


def build_reference_agent_benchmark_inventory() -> dict[str, Any]:
    assets = get_reference_agent_assets()
    return {
        "present": assets["present"],
        "root": str(REFERENCE_AGENT_ROOT),
        "available_modules": dict(assets["available"]),
        "benchmark_roles": {
            "baseline_assets": [
                _inventory_entry(
                    name="flyback_math",
                    role="baseline",
                    module_key="flyback_math",
                    note="Used by the reference-agent baseline adapter for theory synthesis.",
                ),
                _inventory_entry(
                    name="formula_guardrails",
                    role="baseline",
                    module_key="formula_guardrails",
                    note="Used by the reference-agent baseline adapter for spec normalization and engineering checks.",
                ),
                _inventory_entry(
                    name="digikey_components.sqlite",
                    role="baseline",
                    path=REFERENCE_AGENT_COMPONENT_DB_DIR / "digikey_components.sqlite",
                    note="Local component grounding database reused by the reference-agent baseline path.",
                ),
                _inventory_entry(
                    name="mas_component_readiness.json",
                    role="baseline",
                    path=REFERENCE_AGENT_READINESS_JSON,
                    note="Category readiness metadata used to justify component-grounding quality.",
                ),
                _inventory_entry(
                    name="raw_exports",
                    role="baseline",
                    path=REFERENCE_AGENT_RAW_EXPORT_DIR,
                    note="Category-specific DigiKey exports available for future baseline adapters and audits.",
                ),
            ],
            "evaluator_assets": [
                _inventory_entry(
                    name="flyback_efficiency_calculator",
                    role="evaluator",
                    module_key="efficiency_calculator",
                    note="Used by the evaluator for formula-side efficiency and loss estimates.",
                ),
                _inventory_entry(
                    name="design_peer_review",
                    role="evaluator",
                    module_key="design_peer_review_tools",
                    note="Optional false-pass audit for benchmark evaluator outputs.",
                ),
                _inventory_entry(
                    name="simulation_consistency_checker",
                    role="evaluator",
                    module_key="simulation_consistency_tools",
                    note="Optional corner-consistency and stability analysis for evaluator diagnostics.",
                ),
                _inventory_entry(
                    name="final_report_writer",
                    role="evaluator",
                    module_key="final_report_writer_tools",
                    note="Reusable reporting backend for artifact-grade benchmark reports.",
                ),
            ],
            "artifact_assets": [
                _inventory_entry(
                    name="server.py",
                    role="artifact",
                    path=REFERENCE_AGENT_ROOT / "server.py",
                    note="SSE and runtime event plumbing useful for artifact appendix and debugging.",
                ),
                _inventory_entry(
                    name="events.jsonl",
                    role="artifact",
                    path=REFERENCE_AGENT_RUNTIME_DIR / "events.jsonl",
                    note="Historical runtime event log useful for artifact observability.",
                ),
                _inventory_entry(
                    name="metrics.json",
                    role="artifact",
                    path=REFERENCE_AGENT_RUNTIME_DIR / "metrics.json",
                    note="Historical runtime metrics useful for artifact observability.",
                ),
                _inventory_entry(
                    name="plecs-mcp",
                    role="artifact",
                    path=REFERENCE_AGENT_ROOT / "plecs-mcp",
                    note="Reusable PLECS control layer for future non-stub benchmark execution.",
                ),
            ],
            "deferred_non_core": [
                _inventory_entry(
                    name="memory_synthesizer",
                    role="deferred",
                    path=REFERENCE_AGENT_ROOT / "core" / "flyback_mas" / "nodes" / "memory_synthesizer.py",
                    note="Useful system feature, but intentionally not treated as benchmark core.",
                ),
                _inventory_entry(
                    name="run_autocurriculum.py",
                    role="deferred",
                    path=REFERENCE_AGENT_ROOT / "scripts" / "run_autocurriculum.py",
                    note="Curriculum/autonomy tooling is intentionally out of scope for Phase 1 benchmark work.",
                ),
                _inventory_entry(
                    name="frontend",
                    role="deferred",
                    path=REFERENCE_AGENT_ROOT / "frontend",
                    note="Frontend UX is useful for demos but not a primary benchmark artifact.",
                ),
                _inventory_entry(
                    name="prune_lifelong_memory.py",
                    role="deferred",
                    path=REFERENCE_AGENT_ROOT / "scripts" / "prune_lifelong_memory.py",
                    note="Memory maintenance is outside the benchmark's main contribution.",
                ),
            ],
        },
        "runtime_snapshot": build_runtime_asset_snapshot(),
    }


def _select_component_rows(task: dict[str, Any], design: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    assets = get_reference_agent_assets()
    digikey = assets["modules"].get("digikey_local_db")
    rag = assets["modules"].get("component_rag_bridge")
    input_semantics = assets["modules"].get("input_semantics")
    if digikey is None or input_semantics is None:
        return [], {"selector_context": "", "references": []}

    specs = build_reference_agent_specs(task)
    power_stage = input_semantics.resolve_power_stage_input(specs)
    dc_bus_max = float(power_stage.get("dc_bus_max", specs["input_voltage_max"]))
    turns_ratio = max(float(design.get("turns_ratio") or 1.0), 1.0)
    vout = float(specs["output_voltage"])
    iout = float(specs["output_current"])
    reflected_output_voltage = float(design.get("reflected_output_voltage") or turns_ratio * (vout + 1.0))

    preference_profile = {
        "component_actions": [
            "prioritize_voltage_margin",
            "prefer_low_vf_diode",
            "check_output_cap_esr_and_ripple",
        ]
    }
    if task["difficulty_tier"] in {"hard", "stress"}:
        preference_profile["component_actions"].append("reduce_switching_loss_focus")

    queries = {
        "mosfet": {
            "strategy": "local_db_then_fallback",
            "component_type": "mosfet",
            "min_vds": 1.2 * (dc_bus_max + reflected_output_voltage),
            "min_id": 1.5 * float(design.get("primary_peak_current") or 1.0),
            "text_query": f"flyback offline mosfet {int(dc_bus_max)}V bus {task['structured_spec']['output']['power_w']}W",
        },
        "diode": {
            "strategy": "local_db_then_fallback",
            "component_type": "diode",
            "min_vds": 1.2 * (vout + dc_bus_max / turns_ratio),
            "min_id": 1.5 * iout,
            "text_query": f"flyback schottky rectifier {vout}V {iout}A",
        },
        "controller": {
            "strategy": "benchmark_catalog",
            "component_type": "controller",
            "min_vds": 0.0,
            "min_id": 0.0,
            "text_query": "offline flyback pwm controller",
        },
        "output_capacitor": {
            "strategy": "benchmark_catalog",
            "component_type": "output_cap",
            "min_vds": 1.25 * vout,
            "min_id": 0.0,
            "text_query": f"low esr output capacitor {vout}V flyback",
        },
        "core": {
            "strategy": "benchmark_catalog",
            "component_type": "transformer",
            "min_vds": 0.0,
            "min_id": 0.0,
            "text_query": f"ferrite transformer flyback {task['structured_spec']['output']['power_w']}W",
        },
    }

    bom_items: list[dict[str, Any]] = []
    selection_trace: list[dict[str, Any]] = []
    for category, config in queries.items():
        strategy = config["strategy"]
        if strategy == "benchmark_catalog":
            item = _fallback_bom_entry(category, task)
            selection_trace.append(
                {
                    "category": category,
                    "strategy": strategy,
                    "selected_part_id": item["part_id"],
                    "reason": "slot_hardening_prefers_benchmark_catalog",
                }
            )
            bom_items.append(item)
        else:
            selected, diagnostics = _select_local_component_for_slot(
                digikey,
                category=category,
                component_type=config["component_type"],
                min_vds=config["min_vds"],
                min_id=config["min_id"],
                text_query=config["text_query"],
                preference_profile=preference_profile,
                task=task,
                design=design,
            )
            if selected is None:
                selected = _fallback_bom_entry(category, task)
                selection_trace.append(
                    {
                        "category": category,
                        "strategy": "fallback_benchmark_catalog",
                        "selected_part_id": selected["part_id"],
                        "diagnostics": diagnostics[:5],
                    }
                )
            else:
                selection_trace.append(
                    {
                        "category": category,
                        "strategy": "reference_agent_local_db",
                        "selected_part_id": selected["part_id"],
                        "diagnostics": diagnostics[:5],
                    }
                )
            bom_items.append(selected)

    selector_context = {"selector_context": "", "references": [], "inferred_categories": []}
    if rag is not None:
        try:
            selector_context = rag.retrieve_component_rag_context(
                (
                    f"flyback offline controller mosfet schottky output capacitor "
                    f"{task['structured_spec']['output']['power_w']}W "
                    f"{task['structured_spec']['input_range_volts']['min']}-"
                    f"{task['structured_spec']['input_range_volts']['max']}"
                )
            )
        except Exception:
            selector_context = {"selector_context": "", "references": [], "inferred_categories": []}
    selector_context["selection_trace"] = selection_trace
    return bom_items, selector_context


def _estimate_output_ripple_v(design: dict[str, Any], task: dict[str, Any], bom_dict: dict[str, dict[str, Any]]) -> float:
    output_cap = bom_dict.get("output_cap", {})
    raw = _nested_raw_row(output_cap)
    cap_value_f = _first_numeric(
        raw,
        ["Capacitance", "Value"],
        {"uf": 1e-6, "µf": 1e-6, "nf": 1e-9, "pf": 1e-12, "f": 1.0},
    )
    if cap_value_f is None or cap_value_f <= 0:
        cap_value_f = 470e-6
    iout = float(task["structured_spec"]["output"]["current_a"])
    fsw = max(float(design.get("switching_frequency") or 100000.0), 1.0)
    ripple_v = iout / (8.0 * fsw * cap_value_f)
    return max(ripple_v, 0.005)


def estimate_formula_metrics(task: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    assets = get_reference_agent_assets()
    efficiency_module = assets["modules"].get("efficiency_calculator")
    input_semantics = assets["modules"].get("input_semantics")
    if efficiency_module is None or input_semantics is None:
        return {}

    specs = build_reference_agent_specs(task)
    design = build_reference_agent_design(task, candidate)
    bom_dict = build_reference_agent_bom(candidate)
    power_stage = input_semantics.resolve_power_stage_input(specs)
    vin = float(power_stage.get("dc_bus_min", specs["input_voltage_min"]))

    mosfet_raw = _nested_raw_row(bom_dict.get("mosfet", {}))
    diode_raw = _nested_raw_row(bom_dict.get("diode", {}))
    transformer_raw = _nested_raw_row(bom_dict.get("transformer", {}))

    rds_on = _first_numeric(
        mosfet_raw,
        ["Rds On (Max) @ Id, Vgs", "Drain to Source On Resistance (Rds On)", "Rds", "Rds On"],
        {"mohm": 1e-3, "ohm": 1.0},
    ) or 0.18
    qg_nc = _first_numeric(
        mosfet_raw,
        ["Gate Charge (Qg) (Max) @ Vgs", "Qg"],
        {"nc": 1.0, "pc": 1e-3},
    ) or 18.0
    vf = _first_numeric(
        diode_raw,
        ["Voltage - Forward (Vf) (Max) @ If", "Forward Voltage (Vf) (Max) @ If", "Vf"],
        {"mv": 1e-3, "v": 1.0},
    ) or 0.65
    qrr_nc = _first_numeric(
        diode_raw,
        ["Reverse Recovery Time (trr)", "trr"],
        {"ns": 1e-9, "us": 1e-6},
    ) or 25e-9
    ae = _first_numeric(transformer_raw, ["Ae", "Ae_mm2", "core_area"], {"mm2": 1e-6, "cm2": 1e-4}) or 25e-6
    ve = _first_numeric(transformer_raw, ["Ve", "Ve_mm3", "core_volume"], {"mm3": 1e-9, "cm3": 1e-6}) or 2e-6

    result = efficiency_module.calculate_flyback_efficiency(
        vin=vin,
        vout=float(task["structured_spec"]["output"]["voltage_v"]),
        iout=float(task["structured_spec"]["output"]["current_a"]),
        fsw=float(design["switching_frequency"]),
        lpri=float(design["primary_inductance"]),
        n=max(float(design["turns_ratio"]), 1.0),
        d=min(max(float(design["max_duty_cycle"]), 0.05), 0.85),
        r_ds_on=rds_on,
        t_r=40e-9,
        t_f=35e-9,
        v_f=vf,
        q_rr=qrr_nc,
        v_r=float(task["structured_spec"]["constraints"]["max_diode_reverse_voltage_v"]),
        np=36,
        r_winding_pri=0.22,
        r_winding_sec=0.08,
        k_fe=2.46,
        alpha=1.63,
        beta=2.62,
        ve=ve,
        ae=ae,
        core_loss_scale=0.12,
        max_core_loss_ratio_of_pout=0.35,
    )

    ripple_v = _estimate_output_ripple_v(design, task, bom_dict)
    power_stage = input_semantics.resolve_power_stage_input(specs)
    dc_bus_max = float(power_stage.get("dc_bus_max", specs["input_voltage_max"]))
    reflected_output_voltage = float(design["reflected_output_voltage"])
    turns_ratio = max(float(design["turns_ratio"]), 1.0)

    return {
        "efficiency_percent": round(float(result["efficiency"]), 2),
        "efficiency_raw_percent": round(float(result["efficiency_raw"]), 2),
        "mode": result["mode"],
        "confidence": result["confidence"],
        "confidence_reasons": list(result["confidence_reasons"]),
        "losses": dict(result["losses"]),
        "guardrails": dict(result["guardrails"]),
        "delta_b_pkpk_mt": round(float(result["currents"]["delta_b_pkpk_mT"]), 2),
        "flux_density_mt": round(float(result["currents"]["b_hat_mT"]), 2),
        "ripple_mv": round(ripple_v * 1000.0, 2),
        "mosfet_voltage_stress_v": round(dc_bus_max + reflected_output_voltage, 2),
        "diode_reverse_voltage_v": round(
            float(task["structured_spec"]["output"]["voltage_v"]) + dc_bus_max / turns_ratio,
            2,
        ),
        "estimated_cost_usd": round(
            sum(float(item.get("price") or 0.0) for item in candidate.get("bom", [])),
            2,
        ),
        "r_ds_on_ohm": rds_on,
        "qg_nc": qg_nc,
        "v_f_v": vf,
    }


def generate_reference_agent_candidate(
    task: dict[str, Any],
    model_name: str,
    seed: int,
    baseline_name: str,
    disable_correction_memory: bool = False,
) -> dict[str, Any] | None:
    assets = get_reference_agent_assets()
    flyback_math = assets["modules"].get("flyback_math")
    guardrails = assets["modules"].get("formula_guardrails")
    if flyback_math is None or guardrails is None:
        return None

    raw_specs = build_reference_agent_specs(task)
    normalized = guardrails.normalize_and_validate_specs(raw_specs)
    specs = normalized["normalized"]
    frequency_bounds = task["structured_spec"]["switching_frequency_khz"]
    midpoint_fsw_hz = 1000.0 * (frequency_bounds["min"] + frequency_bounds["max"]) / 2.0
    design = flyback_math.calculate_flyback_params(
        specs,
        overrides={"switching_frequency": midpoint_fsw_hz},
    )
    bom_items, selector_context = _select_component_rows(task, design)

    parsed_spec = {
        "input_range_volts": dict(task["structured_spec"]["input_range_volts"]),
        "output": dict(task["structured_spec"]["output"]),
        "targets": dict(task["structured_spec"]["targets"]),
    }
    benchmark_design = {
        "topology": "flyback",
        "turns_ratio_primary_to_secondary": round(float(design["turns_ratio"]), 3),
        "magnetizing_inductance_uh": round(float(design["primary_inductance"]) * 1e6, 2),
        "switching_frequency_khz": round(float(design["switching_frequency"]) / 1000.0, 2),
        "duty_cycle_max": round(float(design["max_duty_cycle"]), 3),
        "primary_peak_current_a": round(float(design["primary_peak_current"]), 3),
    }
    reference_agent_design = {
        "reflected_output_voltage": float(design["reflected_output_voltage"]),
        "ripple_factor": float(design["ripple_factor"]),
        "magnetizing_current_ripple": float(design["magnetizing_current_ripple"]),
        "snubber_r": float(design["snubber_r"]),
        "snubber_c": float(design["snubber_c"]),
    }
    theory_repair_notes: list[str] = []
    if disable_correction_memory:
        theory_repair_notes.append("skipped_theory_and_magnetics_repair_due_to_correction_memory_ablation")
    else:
        theory_repair_notes = _repair_theory_and_magnetics(task, benchmark_design, reference_agent_design)

    candidate = {
        "task_id": task["task_id"],
        "baseline_name": baseline_name,
        "model_name": model_name,
        "seed": seed,
        "parsed_spec": parsed_spec,
        "design_rationale": (
            "Reference-agent baseline used formula modules for theory synthesis, "
            "DigiKey SQLite plus readiness/RAG context for component grounding, "
            "and formula models for claimed metrics."
        ),
        "theoretical_design": benchmark_design,
        "bom": bom_items,
        "simulation_config": {
            "mode": "stub",
            "max_sim_calls": 1 if disable_correction_memory else 2,
            "max_iterations": 1 if disable_correction_memory else 2,
        },
        "final_claimed_metrics": {},
        "uncertainty_or_escalation_flag": {
            "escalate": task["difficulty_tier"] == "stress",
            "reason": "Stress task triggers escalation-aware behavior in the reference-agent baseline"
            if task["difficulty_tier"] == "stress"
            else None,
        },
        "metadata": {
            "iterations_used": 1 if disable_correction_memory else 2,
            "sim_calls_used": 1 if disable_correction_memory else 2,
            "reference_agent_integration": {
                "enabled": True,
                "selector_context_preview": selector_context.get("context_text", "")[:800],
                "inferred_categories": selector_context.get("inferred_categories", []),
                "reference_count": len(selector_context.get("references", [])),
                "selection_trace": selector_context.get("selection_trace", []),
                "runtime_assets": build_runtime_asset_snapshot(),
                "theory_repair_notes": theory_repair_notes,
                "correction_memory_disabled": disable_correction_memory,
            },
            "reference_agent_design": reference_agent_design,
            "reference_agent_bom": _reference_agent_component_dict(bom_items),
        },
    }
    formula_metrics = estimate_formula_metrics(task, candidate)
    candidate["final_claimed_metrics"] = {
        "efficiency_percent": formula_metrics.get("efficiency_percent", task["reference_design"]["expected_metrics"]["efficiency_percent"]),
        "ripple_mv": formula_metrics.get("ripple_mv", task["reference_design"]["expected_metrics"]["ripple_mv"]),
        "mosfet_voltage_stress_v": formula_metrics.get("mosfet_voltage_stress_v", task["reference_design"]["expected_metrics"]["mosfet_voltage_stress_v"]),
        "diode_reverse_voltage_v": formula_metrics.get("diode_reverse_voltage_v", task["reference_design"]["expected_metrics"]["diode_reverse_voltage_v"]),
        "flux_density_mt": formula_metrics.get("flux_density_mt", task["reference_design"]["expected_metrics"]["flux_density_mt"]),
        "estimated_cost_usd": formula_metrics.get("estimated_cost_usd", task["reference_design"]["cost_proxy_usd"]),
    }
    candidate["metadata"]["reference_agent_formula_metrics"] = formula_metrics
    candidate["metadata"]["claim_metrics"] = _build_claim_metrics_metadata(
        status="estimated_only",
        metric_sources={
            "efficiency_percent": "formula_estimate",
            "ripple_mv": "formula_estimate",
            "mosfet_voltage_stress_v": "formula_validation",
            "diode_reverse_voltage_v": "formula_validation",
            "flux_density_mt": "formula_validation",
            "estimated_cost_usd": "bom_sum",
        },
    )
    validation = _pre_sim_grounding_validation(task, candidate)
    if not validation["passed"]:
        repaired_bom = _repair_invalid_bom_slots(task, candidate, validation)
        candidate["bom"] = repaired_bom
        candidate["metadata"]["reference_agent_bom"] = _reference_agent_component_dict(repaired_bom)
        formula_metrics = estimate_formula_metrics(task, candidate)
        candidate["final_claimed_metrics"] = {
            "efficiency_percent": formula_metrics.get("efficiency_percent", task["reference_design"]["expected_metrics"]["efficiency_percent"]),
            "ripple_mv": formula_metrics.get("ripple_mv", task["reference_design"]["expected_metrics"]["ripple_mv"]),
            "mosfet_voltage_stress_v": formula_metrics.get("mosfet_voltage_stress_v", task["reference_design"]["expected_metrics"]["mosfet_voltage_stress_v"]),
            "diode_reverse_voltage_v": formula_metrics.get("diode_reverse_voltage_v", task["reference_design"]["expected_metrics"]["diode_reverse_voltage_v"]),
            "flux_density_mt": formula_metrics.get("flux_density_mt", task["reference_design"]["expected_metrics"]["flux_density_mt"]),
            "estimated_cost_usd": formula_metrics.get("estimated_cost_usd", task["reference_design"]["cost_proxy_usd"]),
        }
        candidate["metadata"]["reference_agent_formula_metrics"] = formula_metrics
        candidate["metadata"]["pre_sim_validation_initial"] = validation
        validation = _pre_sim_grounding_validation(task, candidate)
    candidate["metadata"]["pre_sim_validation"] = validation
    if not validation["passed"]:
        candidate["metadata"]["grounding_failed_before_sim"] = True
        candidate["uncertainty_or_escalation_flag"] = {
            "escalate": True,
            "reason": "Reference-agent grounding path could not satisfy slot-level sanity checks before simulation.",
        }
    return candidate
