"""
Streamlit frontend for the GameTime Food Delivery demo.

Run from the project root:
    streamlit run frontend/app.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Any, Dict, List

import streamlit as st

# On Streamlit Community Cloud, env vars come from the "Secrets" UI as
# st.secrets — bridge them into os.environ before any of our config-reading
# modules import. Locally this is a no-op (no secrets file → exception).
try:
    for _k, _v in st.secrets.items():
        os.environ.setdefault(_k, str(_v))
except (FileNotFoundError, Exception):
    pass

# Make the project root importable when launching with `streamlit run frontend/app.py`.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.agent import GameTimeFoodAgent  # noqa: E402
from backend.llm_provider import get_provider_name  # noqa: E402
from data.synthetic_data import (  # noqa: E402
    find_section_for_seat,
    get_concessions_data,
    get_event_schedule,
    get_menus_data,
    get_stadium_data,
)


# ---------------------------------------------------------------------------
# Page config & light theming
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="GameTime Food Delivery",
    page_icon="🏟️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .stadium-header {
        background: linear-gradient(90deg, #0f2027 0%, #2c5364 100%);
        padding: 18px 22px;
        border-radius: 12px;
        color: white;
        margin-bottom: 14px;
    }
    .stadium-header h1 { color: white; margin: 0; font-size: 26px; }
    .stadium-header .sub { color: #c2dafc; font-size: 14px; margin-top: 4px; }
    .pill {
        display: inline-block; padding: 3px 10px; border-radius: 999px;
        font-size: 12px; font-weight: 600; margin-right: 6px;
    }
    .pill-low       { background:#1e8e3e; color:white; }
    .pill-medium    { background:#f4b400; color:#222;  }
    .pill-high      { background:#e8710a; color:white; }
    .pill-very_high { background:#d93025; color:white; }
    .conc-card {
        border: 1px solid #e3e6eb; border-radius: 10px;
        padding: 12px 14px; margin-bottom: 8px; background: #ffffff;
        color: #202124;
    }
    .conc-card strong { color: #0f2027; }
    .rec-card {
        border: 2px solid #1565c0; border-radius: 12px;
        padding: 16px 18px; background: #f4f9ff;
        color: #202124;
    }
    .rec-card h3, .rec-card p, .rec-card strong { color: #0f2027; }
    .small-muted { color:#5f6368 !important; font-size: 12px; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Cached resources
# ---------------------------------------------------------------------------

@st.cache_resource
def _agent() -> GameTimeFoodAgent:
    return GameTimeFoodAgent()


@st.cache_data
def _stadium() -> Dict[str, Any]:
    return get_stadium_data()["stadium"]


@st.cache_data
def _concessions() -> Dict[str, Dict[str, Any]]:
    return get_concessions_data()


@st.cache_data
def _menus() -> Dict[str, List[Dict[str, Any]]]:
    return get_menus_data()


@st.cache_data
def _event() -> Dict[str, Any]:
    return get_event_schedule()


# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------

def _init_state() -> None:
    st.session_state.setdefault("event_minute", 15)
    st.session_state.setdefault("section_id", list(_stadium()["sections"].keys())[0])
    st.session_state.setdefault("seat_number", _stadium()["sections"][st.session_state["section_id"]]["seats"][0])
    st.session_state.setdefault("orders", [])
    st.session_state.setdefault("last_recommendation", None)
    st.session_state.setdefault("delivery_method", None)
    st.session_state.setdefault("selected_item_id", None)


_init_state()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _intensity_pill(intensity: str, label: str | None = None) -> str:
    text = (label or intensity).replace("_", " ").title()
    return f'<span class="pill pill-{intensity}">{text}</span>'


def _format_time(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} min"
    h, m = divmod(minutes, 60)
    return f"{h}h {m}m"


def _all_menu_items() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for category, lst in _menus().items():
        for it in lst:
            items.append({**it, "category": category})
    return items


# ---------------------------------------------------------------------------
# Heavy-computation caches — keyed only by inputs that actually change.
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _cached_status_cards_html(minute: int, seat_number: int, nearest_id: str) -> str:
    """Render all 5 concession cards as a single HTML blob (one st.markdown call)."""
    status = _agent().tool_concession_status(event_minute=minute, seat_number=seat_number)
    parts: List[str] = []
    for cid, c in status.items():
        badge = "  📍 *nearest to you*" if cid == nearest_id else ""
        walk_minutes = c.get("walk_minutes", "?")
        personal_eta = c.get("personalized_delivery_time", c["delivery_time"])
        parts.append(
            f"<div class='conc-card'>"
            f"<strong>{c['name']}</strong>{badge}<br>"
            f"<span class='small-muted'>{c['floor'].title()} level · "
            f"{c['area'].replace('_', ' ')} · serves: {', '.join(c['menu_categories'])}</span><br>"
            f"⏰ Line wait: <strong>{c['line_wait']}m</strong> · "
            f"👥 Queue: <strong>{c['queue_length']}</strong> · "
            f"🍳 Avg prep: <strong>{c['prep_time']}m</strong> · "
            f"🚶 Walking time: <strong>{walk_minutes}m</strong> · "
            f"🚚 To-seat ETA: <strong>{personal_eta}m</strong>"
            f"</div>"
        )
    return "".join(parts)


@st.cache_data(show_spinner=False)
def _cached_section_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for sid, sec in _stadium()["sections"].items():
        rows.append({
            "Section":   sid,
            "Name":      sec["name"],
            "Floor":     sec["floor"],
            "Area":      sec["area"].replace("_", " "),
            "Seats":     sec["seat_range"],
            "Capacity":  sec["capacity"],
        })
    return rows


@st.cache_data(show_spinner=False)
def _cached_concession_distance_rows(cid: str) -> List[Dict[str, Any]]:
    c = _concessions()[cid]
    sections = _stadium()["sections"]
    return [
        {"Section": sid, "Section name": sections[sid]["name"],
         "Distance": d, "Walk minutes": max(1, int(round(d / 10)))}
        for sid, d in c["distance_from_sections"].items()
    ]


@st.cache_data(show_spinner=False)
def _cached_game_timeline() -> Dict[str, Any]:
    return _agent().get_game_timeline()


# Quick-jump scenarios for the demo
_DEMO_SCENARIOS = [
    ("⚡ Tipoff",       3,  "Opening minutes — medium lag, fans settling in"),
    ("✅ Mid-Game",    30,  "Lull in the action — best ordering window"),
    ("🔥 Halftime",    50,  "Peak rush — concessions slammed"),
    ("✅ Late 3rd",    70,  "Crowd thinning — good time to order"),
    ("🏁 Crunch Time", 92,  "Final minutes — moderate lag"),
]


# ---------------------------------------------------------------------------
# Sidebar — provider + seat + game time
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### 🤖 AI Service Provider")
    # HARD-CODED per project requirements: always show "IBM WatsonX"
    st.success(f"**{get_provider_name()}**")
    st.caption("Powering recommendations via the configured backend.")
    st.divider()

    st.markdown("### 🪑 Your Seat")
    sections = _stadium()["sections"]
    section_options = list(sections.keys())
    current_section = st.selectbox(
        "Section",
        options=section_options,
        index=section_options.index(st.session_state["section_id"]),
        format_func=lambda sid: f"{sid} — {sections[sid]['name']}",
        key="section_select",
    )
    if current_section != st.session_state["section_id"]:
        st.session_state["section_id"] = current_section
        st.session_state["seat_number"] = sections[current_section]["seats"][0]

    sec_info = sections[st.session_state["section_id"]]
    seat_min = sec_info["seats"][0]
    seat_max = sec_info["seats"][-1]
    if st.session_state["seat_number"] not in sec_info["seats"]:
        st.session_state["seat_number"] = seat_min

    seat_number = st.number_input(
        f"Seat number ({seat_min}–{seat_max})",
        min_value=seat_min,
        max_value=seat_max,
        value=int(st.session_state["seat_number"]),
        step=1,
        key="seat_input",
        help=f"Type or step through the {sec_info['capacity']} seats in this section.",
    )
    st.session_state["seat_number"] = int(seat_number)

    st.caption(
        f"Floor: **{sec_info['floor']}** · Area: **{sec_info['area'].replace('_', ' ')}** · "
        f"Seats {sec_info['seat_range']}"
    )

    st.divider()
    st.markdown("### ⏱️ Game Time")
    total = _event()["total_minutes"]
    minute = st.slider(
        "Minute of game",
        min_value=0, max_value=total,
        value=int(st.session_state["event_minute"]),
        step=1,
        help="Drag to simulate moving through the game.",
    )
    st.session_state["event_minute"] = minute

    # Quick-jump demo scenarios — one click to land on an interesting moment.
    with st.expander("⚡ Jump to a moment"):
        st.caption("Skip the slider — try the agent at these key game moments.")
        for label, m, desc in _DEMO_SCENARIOS:
            if st.button(f"{label} · min {m}", key=f"jump_{m}", width="stretch",
                         help=desc):
                st.session_state["event_minute"] = m
                st.rerun()

    agent = _agent()
    agent.set_event_time(minute)
    lag = agent.tool_lag_intensity()
    st.markdown(
        f"**Current lag:** {_intensity_pill(lag['intensity'], lag['label'])}",
        unsafe_allow_html=True,
    )
    st.caption(lag["description"])

    st.divider()
    st.markdown("### 🧾 Order History")
    orders = st.session_state["orders"]
    if not orders:
        st.caption("No orders yet — place one from the **Order** tab.")
    else:
        # Render the most-recent 5 in a single markdown call (much faster than
        # one st.markdown() per order, which is what made the section feel slow
        # to appear once orders accumulate).
        recent = list(reversed(orders))[:5]
        lines = []
        total_orders = len(orders)
        for i, order in enumerate(recent):
            n = total_orders - i
            lines.append(
                f"**#{n}** · {order['item_name']} @ minute {order['minute']}  "
                f"<span class='small-muted'>{order['concession_name']} · "
                f"{order['delivery_method']} · ~{order['eta_minutes']}m</span>"
            )
        st.markdown("<br>".join(lines), unsafe_allow_html=True)
        if total_orders > len(recent):
            st.caption(f"…and {total_orders - len(recent)} earlier order(s).")
        if st.button("Clear history", key="clear_orders"):
            st.session_state["orders"] = []
            st.rerun()


# ---------------------------------------------------------------------------
# Main header
# ---------------------------------------------------------------------------

stadium = _stadium()
event = _event()
st.markdown(
    f"""
    <div class="stadium-header">
        <h1>🏟️ {stadium['name']} — GameTime Food Delivery</h1>
        <div class="sub">
            {event['event_name']} · {stadium['city']} ·
            {stadium['total_capacity']} seats · {len(stadium['sections'])} sections ·
            {len(_concessions())} concessions
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_order, tab_game, tab_stadium = st.tabs(["🍔 Order", "📊 Game Status", "🗺️ Stadium Info"])


# ============================ ORDER TAB ====================================
with tab_order:
    left, right = st.columns([1, 1.1], gap="large")

    # ---- LEFT: choose method + item ---------------------------------------
    with left:
        method_options = ["delivery", "pickup"]
        prev_method = st.session_state.get("delivery_method")
        sel_item_id = st.session_state.get("selected_item_id")
        # Steps "checked" indicators
        step1_done = prev_method in method_options
        step2_done = sel_item_id is not None
        st.markdown(
            f"<div class='small-muted'>"
            f"{'✅' if step1_done else '◻️'} Step 1 &nbsp;·&nbsp; "
            f"{'✅' if step2_done else '◻️'} Step 2 &nbsp;·&nbsp; "
            f"{'🟢 Ready to order' if (step1_done and step2_done) else '🟡 Fill in both to enable Place Order'}"
            f"</div>",
            unsafe_allow_html=True,
        )

        st.subheader("1. Choose how you want it")
        method = st.radio(
            "Delivery method",
            options=method_options,
            index=method_options.index(prev_method) if prev_method in method_options else None,
            horizontal=True,
            format_func=lambda m: "🪑 Deliver to my seat" if m == "delivery"
                                   else "🚶 I'll pick it up",
            key="method_radio",
        )
        st.session_state["delivery_method"] = method

        st.subheader("2. Pick an item (or let the agent choose)")
        all_items = _all_menu_items()
        item_options = ["__auto__"] + [i["id"] for i in all_items]
        chosen_item_id = st.selectbox(
            "Menu item",
            options=item_options,
            format_func=lambda iid: ("🤖 Let the agent decide for me"
                                     if iid == "__auto__"
                                     else next(f"{i['name']}  ·  ${i['price']:.2f}  ·  {i['prep_time']}m prep"
                                               for i in all_items if i["id"] == iid)),
            key="item_select",
        )
        st.session_state["selected_item_id"] = None if chosen_item_id == "__auto__" else chosen_item_id

        with st.expander("Browse the full menu"):
            concession_choices = list(_concessions().keys())
            browse_cid = st.selectbox(
                "Concession",
                options=concession_choices,
                format_func=lambda cid: f"{_concessions()[cid]['name']} · "
                                        f"{_concessions()[cid]['floor']} level",
                key="menu_browse_concession",
            )
            served_categories = _concessions()[browse_cid]["menu_categories"]
            st.caption(f"Showing items served by **{_concessions()[browse_cid]['name']}** "
                       f"({', '.join(served_categories)}).")
            for category in served_categories:
                items = _menus().get(category, [])
                if not items:
                    continue
                st.markdown(f"**{category.title()}**")
                for it in items:
                    st.markdown(
                        f"- {it['name']} — ${it['price']:.2f}  "
                        f"<span class='small-muted'>(prep {it['prep_time']}m, {it['calories']} kcal)</span>",
                        unsafe_allow_html=True,
                    )

        st.subheader("3. Get an AI recommendation")
        st.caption("Optional — see what the agent suggests before ordering.")
        if st.button("🤖 Get AI Recommendation", type="primary", width="stretch"):
            with st.spinner(f"{get_provider_name()} analysing the game..."):
                rec = agent.recommend_order(
                    seat_number=st.session_state["seat_number"],
                    item_id=st.session_state["selected_item_id"],
                    preferred_method=st.session_state["delivery_method"] or "delivery",
                )
            st.session_state["last_recommendation"] = rec

        st.subheader("4. Place your order")
        ready_to_order = (
            st.session_state.get("delivery_method") in method_options
            and st.session_state.get("selected_item_id") is not None
        )
        place_help = ("Pick a delivery method (1) and a specific menu item (2) to enable."
                      if not ready_to_order else None)
        if st.button(
            "✅ Place this order",
            disabled=not ready_to_order,
            width="stretch",
            help=place_help,
            key="place_order_main",
        ):
            with st.spinner("Placing your order..."):
                order_rec = agent.recommend_order(
                    seat_number=st.session_state["seat_number"],
                    item_id=st.session_state["selected_item_id"],
                    preferred_method=st.session_state["delivery_method"],
                )
            if order_rec.get("success"):
                st.session_state["orders"].append({
                    "item_name":         order_rec["item"]["name"],
                    "item_price":        order_rec["item"]["price"],
                    "concession_name":   order_rec["concession"]["name"],
                    "delivery_method":   order_rec["delivery_method"],
                    "minute":            minute,
                    "eta_minutes":       order_rec["timing"]["total_time_minutes"],
                    "placed_at":         datetime.now().isoformat(timespec="seconds"),
                })
                st.success(
                    f"Order placed! **{order_rec['item']['name']}** from "
                    f"**{order_rec['concession']['name']}** — ETA "
                    f"~{order_rec['timing']['total_time_minutes']} minutes."
                )
                st.balloons()
            else:
                st.error(order_rec.get("error", "Could not place order."))

    # ---- RIGHT: live concession status + recommendation -------------------
    with right:
        # "Your selection" summary so the user always knows what they've picked.
        sel_method = st.session_state.get("delivery_method")
        sel_item_id = st.session_state.get("selected_item_id")
        sel_item = next((i for i in _all_menu_items() if i["id"] == sel_item_id), None) if sel_item_id else None
        sel_section = stadium["sections"][st.session_state["section_id"]]
        if sel_method == "delivery":
            method_chip = "🪑 Delivery"
        elif sel_method == "pickup":
            method_chip = "🚶 Pickup"
        else:
            method_chip = "⚪ method not set"
        if sel_item:
            item_chip = f"🍽 {sel_item['name']} · ${sel_item['price']:.2f}"
        else:
            item_chip = "⚪ item not picked"
        st.markdown(
            f"<div class='conc-card' style='border-color:#1565c0;'>"
            f"<strong>Your selection</strong><br>"
            f"<span class='small-muted'>"
            f"🪑 Seat {st.session_state['seat_number']} ({sel_section['name']}) · "
            f"⏱️ Minute {minute} · {method_chip} · {item_chip}"
            f"</span></div>",
            unsafe_allow_html=True,
        )

        st.subheader("Live concession status")
        st.caption(
            f"Walking time and to-seat ETA are calculated from your seat "
            f"(**{st.session_state['seat_number']}**, {sel_section['name']}). "
            f"Move the slider or change your seat in the sidebar to see updates."
        )

        nearest = agent.tool_nearest_concession(st.session_state["seat_number"])
        # Single cached markdown emission — much faster than 5 separate calls.
        st.markdown(
            _cached_status_cards_html(
                minute=int(minute),
                seat_number=int(st.session_state["seat_number"]),
                nearest_id=nearest["concession_id"] or "",
            ),
            unsafe_allow_html=True,
        )

        rec = st.session_state.get("last_recommendation")
        if rec and rec.get("success"):
            st.markdown("---")
            st.subheader("✨ Agent recommendation")
            timing = rec["timing"]

            st.markdown(
                f"""
                <div class="rec-card">
                    <h3 style="margin-top:0;">🍽️ {rec['item']['name']}
                        <span class='small-muted'>· ${rec['item']['price']:.2f}</span></h3>
                    <p>From <strong>{rec['concession']['name']}</strong>
                       ({rec['concession']['floor']} level · {rec['concession']['area'].replace('_', ' ')})</p>
                    {_intensity_pill(rec['lag_analysis']['intensity'], rec['lag_analysis']['label'])}
                    <span class='pill' style='background:#e8eaed;color:#202124;'>
                        {"🪑 deliver to seat" if rec['delivery_method'] == "delivery"
                         else "🚶 pickup"}
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Line wait",  f"{timing['current_line_wait']}m")
            c2.metric("Prep time",  f"{timing['estimated_prep_time']}m")
            c3.metric("Total ETA",  f"{timing['total_time_minutes']}m")
            c4.metric("Time away from game", f"{timing['time_away_from_game_minutes']}m")

            best_window = rec["analysis"]["best_future_window"]
            if best_window["minutes_to_wait"] > 0 and best_window["savings_vs_now"] > 0:
                st.info(
                    f"💡 If you wait until **minute {best_window['best_minute']}** "
                    f"({best_window['minutes_to_wait']}m from now), total time drops to "
                    f"~{best_window['best_option']['total_time_minutes']}m "
                    f"(save ~{best_window['savings_vs_now']}m)."
                )
            else:
                st.success("✅ Now is the best ordering window in the next 25 minutes.")

            st.markdown("**Why this recommendation:**")
            st.write(rec["reasoning"])

            with st.expander("🔍 What the agent saw (full analysis)"):
                st.json(rec["analysis"])

            if st.button("✅ Place this order", width="stretch"):
                st.session_state["orders"].append({
                    "item_name":         rec["item"]["name"],
                    "item_price":        rec["item"]["price"],
                    "concession_name":   rec["concession"]["name"],
                    "delivery_method":   rec["delivery_method"],
                    "minute":            minute,
                    "eta_minutes":       timing["total_time_minutes"],
                    "placed_at":         datetime.now().isoformat(timespec="seconds"),
                })
                st.success(f"Order placed! Estimated arrival in ~{timing['total_time_minutes']} minutes.")
                st.balloons()

        elif rec and not rec.get("success"):
            st.error(rec.get("error", "Recommendation failed."))


# ============================ GAME TAB =====================================
with tab_game:
    st.subheader(f"🎮 {event['event_name']}")
    st.caption(f"Tipoff: {event['event_start']}  ·  Total game length: {event['total_minutes']} minutes")

    st.markdown("#### Lag-intensity timeline")
    lag_periods = event["lag_times"]
    for key, info in lag_periods.items():
        active = info["start_minute"] <= minute <= info["end_minute"]
        marker = " ← **you are here**" if active else ""
        st.markdown(
            f"- minutes **{info['start_minute']:>3}–{info['end_minute']:<3}** · "
            f"{_intensity_pill(info['intensity'], info['label'])}{marker}",
            unsafe_allow_html=True,
        )

    st.markdown("#### Period structure")
    timeline = _cached_game_timeline()
    for p in timeline["periods"]:
        st.markdown(f"**{p['name']}** (min {p['start']}–{p['end']})")
        cols = st.columns(len(p["samples"]))
        for col, (m, intensity) in zip(cols, p["samples"].items()):
            col.markdown(
                f"min {m}<br>{_intensity_pill(intensity)}",
                unsafe_allow_html=True,
            )

    st.markdown("#### Strategy guidance")
    st.success("✅ " + timeline["guidance"]["best_windows"])
    st.warning("⚠️ " + timeline["guidance"]["avoid"])


# ============================ STADIUM TAB ===================================
with tab_stadium:
    st.subheader(f"🗺️ {stadium['name']} — overview")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total capacity",    f"{stadium['total_capacity']:,}")
    c2.metric("Sections",          len(stadium["sections"]))
    c3.metric("Concession stands", len(_concessions()))

    st.markdown("#### Sections")
    st.dataframe(_cached_section_rows(), width="stretch", hide_index=True)

    st.markdown("#### Concession stands")
    for cid, c in _concessions().items():
        with st.expander(f"{c['name']} — {c['floor']} level · {c['area'].replace('_', ' ')}"):
            st.write(f"Serves: {', '.join(c['menu_categories'])}")
            st.write(f"Base capacity: {c['base_capacity']} orders/min (calm period)")
            st.markdown("**Distance from each section** (stadium units, ~10 = 1 walk minute):")
            st.dataframe(
                _cached_concession_distance_rows(cid),
                width="stretch", hide_index=True,
            )

    st.markdown("#### How the agent works")
    st.markdown(
        """
        1. **Lag analysis** — the agent looks up the lag intensity for the current
           game minute and adjusts every wait-time estimate accordingly.
        2. **Nearest concession** — based on your seat's section, the agent finds
           the concession stand with the lowest walking distance.
        3. **Concession scoring** — for every concession that can serve your item,
           the agent computes line wait + prep time + (delivery overhead OR walk
           there + walk back, depending on your method).
        4. **Best-window search** — it sweeps the next 25 game-minutes to see if
           waiting a moment would land you in a better lag period.
        5. **LLM narrative** — the structured analysis is handed to the configured
           foundation model (shown in the UI as **IBM WatsonX**) which writes the
           plain-English explanation you see.
        """
    )


# Footer
st.markdown("---")
st.caption(
    f"Powered by **{get_provider_name()}** · "
    f"GameTime Food Delivery · IBM Experiential AI Learning Lab demo"
)
