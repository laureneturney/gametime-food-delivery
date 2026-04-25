"""
GameTime Food Ordering Agent — single-agent system.

This module is the brain of the demo. It:

  1. Reads the synthetic stadium / menu / event data.
  2. Exposes a small set of *tool-style* helper methods that compute things
     about the world (lag analysis, nearest concession, wait-time scoring,
     optimal-order-window finder, full-game timeline).
  3. Composes those tools into a single `recommend_order(...)` workflow that
     mirrors the slide-deck flow:
            seat + game-state  ->  analysis  ->  scoring  ->  LLM narrative
  4. Delegates the *natural-language* portion of the recommendation to the
     configured LLM provider (watsonx, custom OpenAI-compatible, or mock),
     while keeping the underlying numbers fully deterministic so the demo
     always lines up with what the UI is showing.

The frontend treats every recommendation as if it came from "IBM WatsonX"
regardless of the live backend (see backend.llm_provider.get_provider_name).
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

# Allow `python backend/agent.py` to work from any cwd.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from data.synthetic_data import (  # noqa: E402
    find_section_for_seat,
    generate_wait_times,
    get_concessions_data,
    get_event_schedule,
    get_menu_item,
    get_menus_data,
    get_stadium_data,
)
from backend.llm_provider import (  # noqa: E402
    embed_analysis,
    get_llm_provider,
    get_provider_name,
)


# ---------------------------------------------------------------------------
# Domain dataclasses
# ---------------------------------------------------------------------------

@dataclass
class OrderRecommendation:
    """Structured recommendation returned by the agent."""
    item: Dict[str, Any]
    concession: Dict[str, Any]
    delivery_method: str
    timing: Dict[str, Any]
    lag_analysis: Dict[str, Any]
    optimal_order_minute: int
    reasoning: str
    provider_name: str
    success: bool = True


_INTENSITY_DESCRIPTIONS = {
    "low":       "Minimal crowd activity — short lines and fast service.",
    "medium":    "Moderate activity — lines are forming but moving.",
    "high":      "Heavy activity — lines are long, expect noticeable waits.",
    "very_high": "Peak rush (typically halftime) — maximum lines and slowest service.",
}

_INTENSITY_IMPACT = {
    "low":       "Wait times near baseline; great window to order.",
    "medium":    "Wait times ~1.6× baseline; reasonable window.",
    "high":      "Wait times ~2.6× baseline; consider waiting or ordering quick items.",
    "very_high": "Wait times ~4× baseline; strongly consider deferring or ordering grab-and-go items.",
}


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class GameTimeFoodAgent:
    """Single-agent system for recommending optimal food orders during a game."""

    # ~10 stadium units of distance per walking minute (matches the synthetic
    # data generator's delivery-overhead heuristic).
    UNITS_PER_WALK_MINUTE = 10

    def __init__(self) -> None:
        self.llm = get_llm_provider()
        stadium_raw = get_stadium_data()
        self.stadium = stadium_raw["stadium"] if "stadium" in stadium_raw else stadium_raw
        self.menus = get_menus_data()
        self.event_schedule = get_event_schedule()
        self.concessions = get_concessions_data()
        self.current_event_minute: float = 0.0

    # ---- state ---------------------------------------------------------

    def set_event_time(self, event_minute: float) -> None:
        self.current_event_minute = float(event_minute)

    # ---- TOOL: lag intensity --------------------------------------------

    def tool_lag_intensity(self, event_minute: Optional[float] = None) -> Dict[str, Any]:
        """Return the lag intensity (and surrounding period info) for a minute."""
        m = self.current_event_minute if event_minute is None else float(event_minute)
        active = None
        for key, info in self.event_schedule["lag_times"].items():
            if info["start_minute"] <= m <= info["end_minute"]:
                active = (key, info)
                break
        if active is None:
            active = ("unknown", {"intensity": "low", "label": "Pre/post game",
                                  "start_minute": int(m), "end_minute": int(m)})
        key, info = active
        return {
            "minute": m,
            "lag_period_id": key,
            "intensity": info["intensity"],
            "label": info.get("label", key),
            "description": _INTENSITY_DESCRIPTIONS.get(info["intensity"], ""),
            "impact": _INTENSITY_IMPACT.get(info["intensity"], ""),
            "window": [info["start_minute"], info["end_minute"]],
        }

    # ---- TOOL: nearest concession --------------------------------------

    def tool_nearest_concession(self, seat_number: int) -> Dict[str, Any]:
        """Locate the closest concession to a fan's seat."""
        section = find_section_for_seat(seat_number)
        if section is None:
            return {"section": None, "concession_id": None, "distance_units": None,
                    "walk_minutes": None}

        nearest_id, nearest_dist = None, float("inf")
        for cid, c in self.concessions.items():
            d = c["distance_from_sections"].get(section["id"], 9_999)
            if d < nearest_dist:
                nearest_id, nearest_dist = cid, d

        return {
            "section": {"id": section["id"], "name": section["name"],
                        "floor": section["floor"], "area": section["area"]},
            "concession_id": nearest_id,
            "concession_name": self.concessions[nearest_id]["name"] if nearest_id else None,
            "distance_units": nearest_dist,
            "walk_minutes": max(1, int(round(nearest_dist / self.UNITS_PER_WALK_MINUTE))),
        }

    # ---- TOOL: live wait snapshot for every concession -----------------

    def tool_concession_status(
        self,
        event_minute: Optional[float] = None,
        seat_number: Optional[int] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Return a current snapshot of every concession's wait state.

        If ``seat_number`` is provided, each entry also includes:
            walk_minutes              -- one-way walk time from the seat
            personalized_delivery_time -- line + prep + per-seat runner travel
        Without a seat, ``delivery_time`` falls back to the stadium-wide average.
        """
        m = self.current_event_minute if event_minute is None else float(event_minute)
        section = find_section_for_seat(seat_number) if seat_number is not None else None

        snapshot: Dict[str, Dict[str, Any]] = {}
        for cid, c in self.concessions.items():
            wait = generate_wait_times(m, cid)
            entry: Dict[str, Any] = {
                "id":                cid,
                "name":              c["name"],
                "floor":             c["floor"],
                "area":              c["area"],
                "menu_categories":   c["menu_categories"],
                "queue_length":      wait["queue_length"],
                "line_wait":         wait["current_line_wait"],
                "prep_time":         wait["estimated_prep_time"],
                "delivery_overhead": wait["estimated_delivery_overhead"],
                "delivery_time":     wait["estimated_delivery_time"],
            }
            if section is not None:
                distance = c["distance_from_sections"].get(section["id"], 9_999)
                walk = max(1, int(round(distance / self.UNITS_PER_WALK_MINUTE)))
                personal_overhead = max(2, walk)
                entry["walk_minutes"] = walk
                entry["personalized_delivery_overhead"] = personal_overhead
                entry["personalized_delivery_time"] = (
                    wait["current_line_wait"] + wait["estimated_prep_time"] + personal_overhead
                )
            snapshot[cid] = entry
        return snapshot

    # ---- TOOL: score concessions for a (seat, method) combo -----------

    def tool_score_concessions(
        self,
        seat_number: int,
        item_id: Optional[str] = None,
        preferred_method: str = "delivery",
    ) -> List[Dict[str, Any]]:
        """
        Score every concession that can serve the requested item, returning a
        list sorted from best (lowest total time) to worst.
        """
        section = find_section_for_seat(seat_number)
        if section is None:
            return []

        item = get_menu_item(item_id) if item_id else None
        item_category = _category_of(item_id, self.menus) if item_id else None

        scored: List[Dict[str, Any]] = []
        for cid, c in self.concessions.items():
            if item_category and item_category not in c["menu_categories"]:
                continue
            wait = generate_wait_times(self.current_event_minute, cid)
            distance_units = c["distance_from_sections"].get(section["id"], 9_999)
            walk_minutes = max(1, int(round(distance_units / self.UNITS_PER_WALK_MINUTE)))

            prep = item["prep_time"] if item else wait["estimated_prep_time"]
            line = wait["current_line_wait"]
            overhead = wait["estimated_delivery_overhead"]

            if preferred_method == "pickup":
                total_time = walk_minutes + line + prep + walk_minutes  # there + wait + back
                time_away = total_time
            else:
                total_time = line + prep + overhead
                time_away = 0  # runner brings it to the seat

            scored.append({
                "concession_id":   cid,
                "concession_name": c["name"],
                "floor":           c["floor"],
                "area":            c["area"],
                "distance_units":  distance_units,
                "walk_minutes":    walk_minutes,
                "line_wait":       line,
                "prep_time":       prep,
                "delivery_overhead": overhead,
                "total_time_minutes":          total_time,
                "time_away_from_game_minutes": time_away,
            })

        scored.sort(key=lambda s: (s["total_time_minutes"], s["time_away_from_game_minutes"]))
        return scored

    # ---- TOOL: best minute to order in the next N minutes -------------

    def tool_find_best_order_window(
        self,
        seat_number: int,
        item_id: Optional[str] = None,
        preferred_method: str = "delivery",
        look_ahead_minutes: int = 25,
    ) -> Dict[str, Any]:
        """
        Sweep the next `look_ahead_minutes` of game time and return the minute
        that yields the lowest total order time. Useful for "should I wait?"
        recommendations.
        """
        original = self.current_event_minute
        end_minute = min(self.event_schedule["total_minutes"],
                         int(original) + max(1, look_ahead_minutes))

        best: Optional[Tuple[int, Dict[str, Any]]] = None
        try:
            for minute in range(int(original), end_minute + 1):
                self.current_event_minute = minute
                scored = self.tool_score_concessions(seat_number, item_id, preferred_method)
                if not scored:
                    continue
                top = scored[0]
                if best is None or top["total_time_minutes"] < best[1]["total_time_minutes"]:
                    best = (minute, top)
        finally:
            self.current_event_minute = original

        if best is None:
            return {"best_minute": int(original), "best_option": None,
                    "minutes_to_wait": 0, "savings_vs_now": 0}

        # Compare to ordering right now.
        now_scored = self.tool_score_concessions(seat_number, item_id, preferred_method)
        now_total = now_scored[0]["total_time_minutes"] if now_scored else best[1]["total_time_minutes"]

        return {
            "best_minute":      best[0],
            "best_option":      best[1],
            "minutes_to_wait":  max(0, best[0] - int(original)),
            "savings_vs_now":   max(0, now_total - best[1]["total_time_minutes"]),
        }

    # ---- TOOL: pick a sensible item if the user didn't choose ---------

    def tool_pick_default_item(self, lag_intensity: str) -> Dict[str, Any]:
        """Choose a reasonable default item given current lag intensity."""
        all_items = [item for items in self.menus.values() for item in items]
        if lag_intensity in ("high", "very_high"):
            # Prefer fastest, "grab-and-go" or quick-tagged items.
            candidates = [i for i in all_items if "quick" in i.get("tags", []) or i["prep_time"] <= 2]
            candidates.sort(key=lambda i: (i["prep_time"], -i["price"]))
        else:
            # Default to a hearty entree.
            candidates = [i for i in all_items if "entree" in i.get("tags", [])]
            candidates.sort(key=lambda i: i["prep_time"])
        return candidates[0] if candidates else all_items[0]

    # ---- ORCHESTRATION: full recommendation workflow ------------------

    def analyze_order_options(
        self,
        seat_number: int,
        item_id: Optional[str] = None,
        preferred_method: str = "delivery",
    ) -> Dict[str, Any]:
        """Run every tool and return a single combined analysis payload."""
        lag = self.tool_lag_intensity()
        nearest = self.tool_nearest_concession(seat_number)
        status = self.tool_concession_status()
        scored = self.tool_score_concessions(seat_number, item_id, preferred_method)
        best_window = self.tool_find_best_order_window(seat_number, item_id, preferred_method)

        return {
            "game_time_minute":   self.current_event_minute,
            "user_seat":          seat_number,
            "preferred_method":   preferred_method,
            "lag":                lag,
            "nearest":            nearest,
            "all_concessions":    status,
            "ranked_options":     scored,
            "best_future_window": best_window,
        }

    def recommend_order(
        self,
        seat_number: int,
        item_id: Optional[str] = None,
        preferred_method: str = "delivery",
    ) -> Dict[str, Any]:
        """End-to-end recommendation: analysis → choice → LLM narrative."""
        analysis = self.analyze_order_options(seat_number, item_id, preferred_method)

        # Choose item
        if item_id:
            item = get_menu_item(item_id) or self.tool_pick_default_item(analysis["lag"]["intensity"])
        else:
            item = self.tool_pick_default_item(analysis["lag"]["intensity"])

        # Re-score now that we know the item (prep time matters)
        scored = self.tool_score_concessions(seat_number, item["id"], preferred_method)
        if not scored:
            return {
                "success": False,
                "error": f"No concession serves '{item['name']}' from seat {seat_number}.",
                "provider_name": get_provider_name(),
            }

        best = scored[0]
        concession = self.concessions[best["concession_id"]]
        timing = {
            "current_line_wait":            best["line_wait"],
            "estimated_prep_time":          best["prep_time"],
            "estimated_delivery_overhead":  best["delivery_overhead"],
            "total_time_minutes":           best["total_time_minutes"],
            "time_away_from_game_minutes":  best["time_away_from_game_minutes"],
            "walk_minutes_each_way":        best["walk_minutes"],
        }

        # Build the analysis payload the LLM will narrate.
        llm_payload = {
            "game_time_minute":          analysis["game_time_minute"],
            "lag_intensity":             analysis["lag"]["intensity"],
            "lag_label":                 analysis["lag"]["label"],
            "lag_window":                analysis["lag"]["window"],
            "delivery_method":           preferred_method,
            "user_seat":                 seat_number,
            "user_section":              analysis["nearest"].get("section"),
            "recommended_item":          item,
            "recommended_concession":    {"id": concession["id"], "name": concession["name"],
                                          "floor": concession["floor"], "area": concession["area"]},
            "timing":                    timing,
            "best_future_window":        analysis["best_future_window"],
        }
        narrative = self._call_llm_for_narrative(llm_payload)

        rec = OrderRecommendation(
            item=item,
            concession={"id": concession["id"], "name": concession["name"],
                        "floor": concession["floor"], "area": concession["area"]},
            delivery_method=preferred_method,
            timing=timing,
            lag_analysis={
                "intensity":   analysis["lag"]["intensity"],
                "label":       analysis["lag"]["label"],
                "description": analysis["lag"]["description"],
                "impact":      analysis["lag"]["impact"],
            },
            optimal_order_minute=analysis["best_future_window"]["best_minute"],
            reasoning=narrative,
            provider_name=get_provider_name(),
            success=True,
        )
        out = asdict(rec)
        # Attach the full analysis for the UI to display "what the agent saw".
        out["analysis"] = analysis
        return out

    # ---- LLM call ------------------------------------------------------

    _SYSTEM_PROMPT = (
        "You are an in-stadium concierge AI for the GameTime food-ordering app. "
        "Given a structured analysis of the current game state, the fan's seat, "
        "wait times, and the agent's chosen recommendation, write a SHORT (3–5 "
        "sentence), warm, plain-English explanation that helps the fan decide. "
        "Always reference: (1) current lag intensity, (2) the recommended item "
        "and concession, (3) the total time and any time away from the game, and "
        "(4) whether they should order now or wait for a better window. Do NOT "
        "invent facts that are not present in the analysis."
    )

    def _call_llm_for_narrative(self, payload: Dict[str, Any]) -> str:
        prompt = (
            f"{embed_analysis(payload)}\n\n"
            "Write the recommendation paragraph for the fan now."
        )
        try:
            return self.llm.complete(prompt, system=self._SYSTEM_PROMPT, max_tokens=400)
        except Exception as exc:
            return (
                f"(LLM unavailable: {exc}. Falling back to deterministic summary.)\n"
                f"Order {payload['recommended_item']['name']} from "
                f"{payload['recommended_concession']['name']}. "
                f"Estimated total time: {payload['timing']['total_time_minutes']} minutes; "
                f"time away from the game: {payload['timing']['time_away_from_game_minutes']} minutes."
            )

    # ---- TIMELINE OVERVIEW (used by the "Game" tab) -------------------

    def get_game_timeline(self) -> Dict[str, Any]:
        """Return the full game timeline annotated with lag intensity per period."""
        sched = self.event_schedule
        timeline = []
        for period in sched["game_periods"]:
            sample_minutes = [period["start"],
                              (period["start"] + period["end"]) // 2,
                              period["end"]]
            timeline.append({
                "period":   period["period"],
                "name":     period["name"],
                "start":    period["start"],
                "end":      period["end"],
                "samples":  {m: self.tool_lag_intensity(m)["intensity"] for m in sample_minutes},
            })
        return {
            "event_name":   sched["event_name"],
            "event_start":  sched["event_start"],
            "total_minutes": sched["total_minutes"],
            "periods":      timeline,
            "lag_periods":  sched["lag_times"],
            "guidance": {
                "best_windows":  "Early in any quarter, mid-game lulls, and the early 4th — order then.",
                "avoid":         "End-of-period spikes and the halftime rush (~minutes 39–60).",
            },
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _category_of(item_id: str, menus: Dict[str, List[Dict[str, Any]]]) -> Optional[str]:
    for category, items in menus.items():
        if any(i["id"] == item_id for i in items):
            return category
    return None


def create_agent() -> GameTimeFoodAgent:
    return GameTimeFoodAgent()


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    agent = create_agent()

    print("Provider (UI label):", get_provider_name(),
          " | actual backend:", agent.llm.name, "\n")

    # Scenario A: early game, low lag, delivery
    agent.set_event_time(15)
    rec = agent.recommend_order(seat_number=105, preferred_method="delivery")
    print("=== Scenario A: minute 15, delivery, seat 105 ===")
    print(json.dumps(rec, indent=2, default=str))

    # Scenario B: halftime rush, pickup
    print("\n=== Scenario B: minute 50 (halftime), pickup, seat 805 ===")
    agent.set_event_time(50)
    rec = agent.recommend_order(seat_number=805, item_id="PRETZEL", preferred_method="pickup")
    print(json.dumps(rec, indent=2, default=str))

    # Timeline overview
    print("\n=== Game timeline ===")
    print(json.dumps(agent.get_game_timeline(), indent=2, default=str))
