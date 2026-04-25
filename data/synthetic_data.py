"""
Synthetic data for the GameTime Food Delivery demo.

Provides a single mock stadium ("Champions Arena") with sections, seats,
concession stands, menus, a 100-minute event timeline with lag periods,
and a deterministic dynamic wait-time generator that produces "real-time"
looking values that change with the game minute.

Public API (used by backend.agent and frontend.app):
    get_stadium_data()     -> {"stadium": {...}}
    get_concessions_data() -> {conc_id: {...}}
    get_menus_data()       -> {category: [item, ...]}
    get_event_schedule()   -> {"event_name", "event_start", "lag_times", "game_periods"}
    generate_wait_times(event_minute, conc_id) -> {...}
    get_full_dataset()     -> bundles all of the above (handy for the UI / debugging)
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List


# ---------------------------------------------------------------------------
# Stadium layout
# ---------------------------------------------------------------------------

# 11 sections. Seat numbers are unique across the whole stadium so a single
# integer seat number is enough to identify a fan (matches the agent's
# `_get_nearest_concession(seat_number)` lookup).
_SECTIONS: List[Dict[str, Any]] = [
    # Lower bowl
    {"id": "L100", "name": "Lower Bowl - Section 100", "floor": "lower", "area": "north_sideline",
     "seat_start": 100, "seat_count": 60},
    {"id": "L110", "name": "Lower Bowl - Section 110", "floor": "lower", "area": "east_corner",
     "seat_start": 200, "seat_count": 60},
    {"id": "L120", "name": "Lower Bowl - Section 120", "floor": "lower", "area": "south_sideline",
     "seat_start": 300, "seat_count": 60},
    {"id": "L130", "name": "Lower Bowl - Section 130", "floor": "lower", "area": "west_corner",
     "seat_start": 400, "seat_count": 60},
    # Club / VIP
    {"id": "C200", "name": "Club Level - Section 200", "floor": "club", "area": "north_sideline",
     "seat_start": 500, "seat_count": 40},
    {"id": "C210", "name": "Club Level - Section 210", "floor": "club", "area": "south_sideline",
     "seat_start": 600, "seat_count": 40},
    {"id": "V250", "name": "VIP Suites", "floor": "club", "area": "center",
     "seat_start": 700, "seat_count": 20},
    # Upper bowl
    {"id": "U300", "name": "Upper Deck - Section 300", "floor": "upper", "area": "north_sideline",
     "seat_start": 800, "seat_count": 80},
    {"id": "U310", "name": "Upper Deck - Section 310", "floor": "upper", "area": "east_corner",
     "seat_start": 900, "seat_count": 80},
    {"id": "U320", "name": "Upper Deck - Section 320", "floor": "upper", "area": "south_sideline",
     "seat_start": 1000, "seat_count": 80},
    {"id": "U330", "name": "Upper Deck - Section 330", "floor": "upper", "area": "west_corner",
     "seat_start": 1100, "seat_count": 80},
]


def _build_sections() -> Dict[str, Dict[str, Any]]:
    sections: Dict[str, Dict[str, Any]] = {}
    for s in _SECTIONS:
        seats = list(range(s["seat_start"], s["seat_start"] + s["seat_count"]))
        sections[s["id"]] = {
            "id": s["id"],
            "name": s["name"],
            "floor": s["floor"],
            "area": s["area"],
            "seats": seats,
            "seat_range": f"{seats[0]}-{seats[-1]}",
            "capacity": len(seats),
        }
    return sections


# ---------------------------------------------------------------------------
# Concessions
# ---------------------------------------------------------------------------

# Each concession serves a curated subset of menu categories. The
# `distance_from_sections` map is in arbitrary "stadium units" that the agent
# converts into walking time (~10 units per minute).
_CONCESSIONS: List[Dict[str, Any]] = [
    {
        "id": "CONC_LOWER_NORTH",
        "name": "Grand Slam Grill",
        "floor": "lower",
        "area": "north_concourse",
        "menu_categories": ["food", "beverages"],
        "base_capacity": 14,  # orders per "stand minute" before lag multiplier
        "lower_floor": True,
    },
    {
        "id": "CONC_LOWER_SOUTH",
        "name": "End Zone Eats",
        "floor": "lower",
        "area": "south_concourse",
        "menu_categories": ["food", "beverages", "desserts"],
        "base_capacity": 12,
        "lower_floor": True,
    },
    {
        "id": "CONC_UPPER_EAST",
        "name": "Upper Deck Pub",
        "floor": "upper",
        "area": "east_concourse",
        "menu_categories": ["beverages", "snacks"],
        "base_capacity": 10,
        "lower_floor": False,
    },
    {
        "id": "CONC_UPPER_WEST",
        "name": "Skyline Snack Bar",
        "floor": "upper",
        "area": "west_concourse",
        "menu_categories": ["food", "snacks", "beverages"],
        "base_capacity": 11,
        "lower_floor": False,
    },
    {
        "id": "CONC_CLUB",
        "name": "Champions Club Lounge",
        "floor": "club",
        "area": "center",
        "menu_categories": ["food", "beverages", "desserts"],
        "base_capacity": 16,  # premium service, smaller crowd
        "lower_floor": False,
    },
]


def _section_to_concession_distance(section: Dict[str, Any], conc: Dict[str, Any]) -> int:
    """Synthesise a believable distance (in stadium units) between a section and concession.

    Heuristic:
      * 30 base units for being on the same floor/area
      * +25 for crossing concourse area
      * +50 for changing floors (stairs/escalator)
      * VIP and club seats get a small premium discount because of dedicated lifts
    """
    base = 30
    if section["area"] != conc["area"].replace("_concourse", "").replace("_corner", "").replace("_sideline", ""):
        # Compare cardinal directions roughly
        sec_dir = section["area"].split("_")[0]
        conc_dir = conc["area"].split("_")[0]
        if sec_dir != conc_dir and conc_dir not in ("center",):
            base += 25
    if section["floor"] != conc["floor"]:
        base += 50
    if section["floor"] == "club" and conc["floor"] == "club":
        base = max(20, base - 10)
    # Add a stable per-pair jitter so distances feel hand-tuned rather than uniform
    jitter_seed = f"{section['id']}::{conc['id']}"
    jitter = int(hashlib.md5(jitter_seed.encode()).hexdigest(), 16) % 15
    return base + jitter


def _build_concessions(sections: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    concessions: Dict[str, Dict[str, Any]] = {}
    for c in _CONCESSIONS:
        distances = {
            section_id: _section_to_concession_distance(sec, c)
            for section_id, sec in sections.items()
        }
        concessions[c["id"]] = {
            "id": c["id"],
            "name": c["name"],
            "floor": c["floor"],
            "area": c["area"],
            "menu_categories": c["menu_categories"],
            "base_capacity": c["base_capacity"],
            "distance_from_sections": distances,
        }
    return concessions


# ---------------------------------------------------------------------------
# Menus
# ---------------------------------------------------------------------------

_MENUS: Dict[str, List[Dict[str, Any]]] = {
    "food": [
        {"id": "HOT_DOG",    "name": "Classic Hot Dog",        "price":  8.50, "prep_time": 2, "calories": 290, "tags": ["quick", "classic"]},
        {"id": "BURGER",     "name": "Stadium Cheeseburger",   "price": 13.50, "prep_time": 6, "calories": 720, "tags": ["entree"]},
        {"id": "PIZZA",      "name": "Pepperoni Pizza Slice",  "price":  9.75, "prep_time": 4, "calories": 420, "tags": ["entree"]},
        {"id": "WINGS",      "name": "Buffalo Wings (8 pc)",   "price": 14.99, "prep_time": 8, "calories": 880, "tags": ["entree", "shareable"]},
        {"id": "NACHOS",     "name": "Loaded Nachos",          "price": 11.50, "prep_time": 5, "calories": 950, "tags": ["shareable"]},
        {"id": "CHIX_SAND",  "name": "Crispy Chicken Sandwich","price": 12.50, "prep_time": 6, "calories": 640, "tags": ["entree"]},
    ],
    "snacks": [
        {"id": "POPCORN",    "name": "Buttered Popcorn",       "price":  6.50, "prep_time": 1, "calories": 480, "tags": ["quick", "shareable"]},
        {"id": "PRETZEL",    "name": "Soft Pretzel",           "price":  7.25, "prep_time": 2, "calories": 380, "tags": ["quick"]},
        {"id": "FRIES",      "name": "Stadium Fries",          "price":  6.99, "prep_time": 3, "calories": 510, "tags": ["shareable"]},
        {"id": "PEANUTS",    "name": "Roasted Peanuts",        "price":  5.50, "prep_time": 0, "calories": 320, "tags": ["quick", "grab-and-go"]},
    ],
    "beverages": [
        {"id": "SODA",       "name": "Fountain Soda (24oz)",   "price":  6.00, "prep_time": 1, "calories": 240, "tags": ["quick"]},
        {"id": "WATER",      "name": "Bottled Water",          "price":  4.50, "prep_time": 0, "calories":   0, "tags": ["quick", "grab-and-go"]},
        {"id": "BEER",       "name": "Draft Beer (16oz)",      "price": 12.50, "prep_time": 1, "calories": 180, "tags": ["quick", "21+"]},
        {"id": "LEMONADE",   "name": "Fresh Lemonade",         "price":  7.50, "prep_time": 2, "calories": 220, "tags": []},
        {"id": "COFFEE",     "name": "Hot Coffee",             "price":  4.99, "prep_time": 1, "calories":   5, "tags": ["quick"]},
    ],
    "desserts": [
        {"id": "ICE_CREAM",  "name": "Ice Cream Cup",          "price":  6.99, "prep_time": 1, "calories": 280, "tags": ["quick"]},
        {"id": "FUNNEL",     "name": "Funnel Cake",            "price":  9.50, "prep_time": 5, "calories": 760, "tags": []},
    ],
}


# ---------------------------------------------------------------------------
# Event schedule + lag periods
# ---------------------------------------------------------------------------

_EVENT_SCHEDULE: Dict[str, Any] = {
    "event_name": "Champions Arena - Conference Finals",
    "event_start": "2026-04-25T19:00:00",
    "total_minutes": 100,
    "game_periods": [
        {"period": 1, "name": "1st Quarter",  "start":   0, "end":  20},
        {"period": 2, "name": "2nd Quarter",  "start":  20, "end":  40},
        {"period": 3, "name": "Halftime",     "start":  40, "end":  55},
        {"period": 4, "name": "3rd Quarter",  "start":  55, "end":  75},
        {"period": 5, "name": "4th Quarter",  "start":  75, "end": 100},
    ],
    # `intensity` ∈ {"low", "medium", "high", "very_high"}.
    # Periods are inclusive of their start_minute and end_minute.
    "lag_times": {
        "tipoff_rush":     {"start_minute":   0, "end_minute":   5,  "intensity": "medium",
                            "label": "Tipoff Rush"},
        "early_q1":        {"start_minute":   6, "end_minute":  18,  "intensity": "low",
                            "label": "Settled 1st Quarter"},
        "end_q1":          {"start_minute":  19, "end_minute":  22,  "intensity": "high",
                            "label": "End of 1st Quarter"},
        "mid_game":        {"start_minute":  23, "end_minute":  38,  "intensity": "low",
                            "label": "Mid-Game Lull"},
        "pre_halftime":    {"start_minute":  39, "end_minute":  41,  "intensity": "high",
                            "label": "Approaching Halftime"},
        "halftime":        {"start_minute":  42, "end_minute":  55,  "intensity": "very_high",
                            "label": "Halftime Rush"},
        "early_q3":        {"start_minute":  56, "end_minute":  60,  "intensity": "high",
                            "label": "Post-Halftime Tail"},
        "mid_q3":          {"start_minute":  61, "end_minute":  72,  "intensity": "low",
                            "label": "3rd Quarter Lull"},
        "end_q3":          {"start_minute":  73, "end_minute":  77,  "intensity": "medium",
                            "label": "End of 3rd"},
        "early_q4":        {"start_minute":  78, "end_minute":  88,  "intensity": "low",
                            "label": "Early 4th Quarter"},
        "crunch_time":     {"start_minute":  89, "end_minute": 100,  "intensity": "medium",
                            "label": "Crunch Time"},
    },
}


_INTENSITY_MULTIPLIER = {
    "low":       1.0,
    "medium":    1.6,
    "high":      2.6,
    "very_high": 4.0,
}


def _intensity_at(event_minute: float) -> str:
    for info in _EVENT_SCHEDULE["lag_times"].values():
        if info["start_minute"] <= event_minute <= info["end_minute"]:
            return info["intensity"]
    return "low"


# ---------------------------------------------------------------------------
# Cached datasets
# ---------------------------------------------------------------------------

_SECTIONS_CACHE = _build_sections()
_CONCESSIONS_CACHE = _build_concessions(_SECTIONS_CACHE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_stadium_data() -> Dict[str, Any]:
    """Return the stadium descriptor (wrapped under "stadium" for the agent)."""
    total_capacity = sum(sec["capacity"] for sec in _SECTIONS_CACHE.values())
    return {
        "stadium": {
            "id": "CHAMPIONS_ARENA",
            "name": "Champions Arena",
            "city": "Denver, CO",
            "total_capacity": total_capacity,
            "floors": ["lower", "club", "upper"],
            "sections": _SECTIONS_CACHE,
        }
    }


def get_concessions_data() -> Dict[str, Dict[str, Any]]:
    """Return concession metadata keyed by concession id."""
    return _CONCESSIONS_CACHE


def get_menus_data() -> Dict[str, List[Dict[str, Any]]]:
    """Return menus keyed by category."""
    return _MENUS


def get_event_schedule() -> Dict[str, Any]:
    """Return the event timeline + lag-period definitions."""
    return _EVENT_SCHEDULE


def generate_wait_times(event_minute: float, concession_id: str) -> Dict[str, Any]:
    """
    Produce a deterministic-but-lively snapshot of wait times for a concession
    at a given minute of the game.

    Returns a dict with:
        intensity                -- low/medium/high/very_high label for the moment
        intensity_multiplier     -- numeric multiplier applied to base load
        queue_length             -- number of people currently in the line
        current_line_wait        -- minutes a new arrival would wait in line
        estimated_prep_time      -- avg minutes to assemble a typical order
        estimated_delivery_time  -- minutes from order placed -> arrived at seat
        order_window_open        -- whether the kitchen is currently accepting orders
        last_updated_minute      -- the minute these numbers were sampled at
    """
    if concession_id not in _CONCESSIONS_CACHE:
        raise KeyError(f"Unknown concession_id: {concession_id}")

    conc = _CONCESSIONS_CACHE[concession_id]
    intensity = _intensity_at(event_minute)
    mult = _INTENSITY_MULTIPLIER[intensity]

    # Per-concession + per-minute jitter, deterministic so the demo is
    # reproducible across UI reruns.
    jitter_seed = f"{concession_id}::{int(event_minute)}"
    jitter_raw = int(hashlib.md5(jitter_seed.encode()).hexdigest(), 16)
    jitter = (jitter_raw % 11) - 5  # -5..+5

    base_queue = 4 + (conc["base_capacity"] // 4)
    queue_length = max(0, int(round(base_queue * mult + jitter)))

    # Throughput in orders per minute, scaled down by the lag multiplier.
    throughput = max(1.0, conc["base_capacity"] / mult)
    line_wait = math.ceil(queue_length / throughput)

    # Average kitchen prep time across this concession's menu (rounded up).
    prep_times = []
    for category in conc["menu_categories"]:
        prep_times.extend(item["prep_time"] for item in _MENUS.get(category, []))
    avg_prep = max(1, int(round(sum(prep_times) / max(1, len(prep_times)))))

    # Delivery overhead: a runner must traverse the average distance from this
    # concession to all sections. ~10 stadium units per minute.
    avg_distance = sum(conc["distance_from_sections"].values()) / len(conc["distance_from_sections"])
    delivery_overhead = max(2, int(round(avg_distance / 10)))

    delivery_time = line_wait + avg_prep + delivery_overhead

    return {
        "concession_id": concession_id,
        "concession_name": conc["name"],
        "intensity": intensity,
        "intensity_multiplier": mult,
        "queue_length": queue_length,
        "current_line_wait": line_wait,
        "estimated_prep_time": avg_prep,
        "estimated_delivery_overhead": delivery_overhead,
        "estimated_delivery_time": delivery_time,
        "order_window_open": True,
        "last_updated_minute": event_minute,
    }


def get_full_dataset() -> Dict[str, Any]:
    """Bundle everything for debugging / one-shot inspection."""
    return {
        "stadium":     get_stadium_data()["stadium"],
        "concessions": get_concessions_data(),
        "menus":       get_menus_data(),
        "event":       get_event_schedule(),
    }


# ---------------------------------------------------------------------------
# Convenience helpers used by the frontend
# ---------------------------------------------------------------------------

def list_all_seats() -> List[int]:
    """Flat list of every seat number in the stadium."""
    seats: List[int] = []
    for sec in _SECTIONS_CACHE.values():
        seats.extend(sec["seats"])
    return seats


def find_section_for_seat(seat_number: int) -> Dict[str, Any] | None:
    for sec in _SECTIONS_CACHE.values():
        if seat_number in sec["seats"]:
            return sec
    return None


def get_menu_item(item_id: str) -> Dict[str, Any] | None:
    for items in _MENUS.values():
        for item in items:
            if item["id"] == item_id:
                return item
    return None


if __name__ == "__main__":
    print(json.dumps(get_full_dataset(), indent=2, default=str))
    print("\n--- sample wait snapshot at minute 50 (halftime) ---")
    print(json.dumps(generate_wait_times(50, "CONC_LOWER_NORTH"), indent=2))
