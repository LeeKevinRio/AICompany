"""Built-in airline table for the airline filter (FD-5, ADR-0002 FD-5 Decision 6, C-41).

Scope: carriers commonly flown from Taiwan (PRD FR-A1), 30-50 rows. Codes are the
two-character IATA airline designators. Verification (2026-10-28, dev-lead):

* ``GF-SHA`` -- the airline code/name table Google Flights itself embeds in its results
  payload (``payload[7][1][1]``), recorded live for TPE->SHA on 2026-10-26
  (``tests/fixtures/payload_TPE_SHA.json``).
* ``GF-NRT`` -- the same embedded airline table in the TPE->NRT payload recorded live on
  2026-10-28 (``tests/fixtures/payload_TPE_NRT_BR_06_12.json``, 50 carriers), plus the
  carrier codes / Chinese names of the itineraries recorded for TPE->NRT on 2026-10-25
  (``tests/fixtures/fixture_roundtrip_TPE_NRT.json``).
* ``qa-reviewer`` -- not present in any recorded Google payload (AK, DL, EK, QR);
  cross-checked by qa-reviewer against official carrier / IATA code search data
  (https://www.iata.org/en/publications/directories/code-search/) on 2026-10-28.
  Per-row results are recorded in ``work/tasks/FD-5.md``.

The filter is applied by Google Flights itself (hard filter); results are not
post-filtered here, and codeshare interpretation is Google's (Decision 6).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

MAX_AIRLINES = 5


@dataclass(frozen=True)
class Airline:
    code: str
    zh_name: str
    display_name: str
    en_name: str
    verified_note: str


_SHA = "GF-SHA 2026-10-26"
_NRT = "GF-NRT 2026-10-28"
_QA = "qa-reviewer 依記憶＋Codex 官方資料交叉確認 2026-10-28"

# Order matters: the form lists airlines in table order.
AIRLINES: tuple[Airline, ...] = (
    # Taiwan
    Airline("BR", "長榮航空", "長榮", "EVA Air", f"{_SHA}; {_NRT}"),
    Airline("CI", "中華航空", "華航", "China Airlines", f"{_SHA}; {_NRT}"),
    Airline("JX", "星宇航空", "星宇", "STARLUX Airlines", _NRT),
    Airline("IT", "台灣虎航", "台灣虎航", "Tigerair Taiwan", _NRT),
    # Japan
    Airline("JL", "日本航空", "日航", "Japan Airlines", f"{_SHA}; {_NRT}"),
    Airline("NH", "全日空航空", "全日空", "All Nippon Airways", f"{_SHA}; {_NRT}"),
    Airline("MM", "樂桃航空", "樂桃", "Peach Aviation", _NRT),
    Airline("GK", "捷星日本航空", "捷星日本", "Jetstar Japan", _NRT),
    # Korea
    Airline("KE", "大韓航空", "大韓", "Korean Air", f"{_SHA}; {_NRT}"),
    Airline("OZ", "韓亞航空", "韓亞", "Asiana Airlines", f"{_SHA}; {_NRT}"),
    Airline("7C", "濟州航空", "濟州", "Jeju Air", _NRT),
    Airline("LJ", "真航空", "真航空", "Jin Air", _NRT),
    Airline("BX", "釜山航空", "釜山", "Air Busan", _NRT),
    Airline("TW", "德威航空", "德威", "T'way Air", _NRT),
    Airline("ZE", "易斯達航空", "易斯達", "Eastar Jet", _NRT),
    # Hong Kong / Macau
    Airline("CX", "國泰航空", "國泰", "Cathay Pacific", f"{_SHA}; {_NRT}"),
    Airline("UO", "香港快運", "香港快運", "HK Express", _NRT),
    Airline("HX", "香港航空", "香港航空", "Hong Kong Airlines", f"{_SHA}; {_NRT}"),
    Airline("NX", "澳門航空", "澳門航空", "Air Macau", f"{_SHA}; {_NRT}"),
    Airline("HB", "大灣區航空", "大灣區", "Greater Bay Airlines", _NRT),
    # Southeast Asia
    Airline("SQ", "新加坡航空", "新航", "Singapore Airlines", _NRT),
    Airline("TR", "酷航", "酷航", "Scoot", _NRT),
    Airline("TG", "泰國國際航空", "泰航", "Thai Airways", _NRT),
    Airline("FD", "泰國亞洲航空", "泰國亞航", "Thai AirAsia", _NRT),
    Airline("VZ", "泰越捷航空", "泰越捷", "Thai Vietjet Air", _NRT),
    Airline("VJ", "越捷航空", "越捷", "VietJet Air", _NRT),
    Airline("VN", "越南航空", "越南航空", "Vietnam Airlines", _NRT),
    Airline("MH", "馬來西亞航空", "馬航", "Malaysia Airlines", _NRT),
    Airline("AK", "馬來西亞亞洲航空", "亞航", "AirAsia", _QA),
    Airline("PR", "菲律賓航空", "菲航", "Philippine Airlines", _NRT),
    Airline("5J", "宿霧太平洋航空", "宿霧太平洋", "Cebu Pacific", _NRT),
    # Mainland China
    Airline("MU", "中國東方航空", "東航", "China Eastern Airlines", f"{_SHA}; {_NRT}"),
    Airline("CZ", "中國南方航空", "南航", "China Southern Airlines", f"{_SHA}; {_NRT}"),
    Airline("CA", "中國國際航空", "國航", "Air China", f"{_SHA}; {_NRT}"),
    Airline("MF", "廈門航空", "廈航", "XiamenAir", f"{_SHA}; {_NRT}"),
    # Long haul
    Airline("UA", "聯合航空", "聯合", "United Airlines", _NRT),
    Airline("DL", "達美航空", "達美", "Delta Air Lines", _QA),
    Airline("EK", "阿聯酋航空", "阿聯酋", "Emirates", _QA),
    Airline("QR", "卡達航空", "卡達", "Qatar Airways", _QA),
    Airline("TK", "土耳其航空", "土航", "Turkish Airlines", _NRT),
    Airline("QF", "澳洲航空", "澳航", "Qantas", _NRT),
)

_BY_CODE: dict[str, Airline] = {a.code: a for a in AIRLINES}


def lookup_airline(code: str) -> Airline | None:
    return _BY_CODE.get(code.strip().upper())


def airline_label(code: str) -> str:
    """Short Chinese name; a code outside the table falls back to the code itself."""
    airline = _BY_CODE.get(code)
    return airline.display_name if airline else code


def airlines_label(codes: Iterable[str]) -> str:
    """Names in table order (codes outside the table last, sorted); empty -> ""."""
    wanted = set(codes)
    known = [a.display_name for a in AIRLINES if a.code in wanted]
    unknown = sorted(c for c in wanted if c not in _BY_CODE)
    return "、".join([*known, *unknown])
