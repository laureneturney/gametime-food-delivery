# 🏟️ GameTime Food Delivery — Agentic AI MVP

A "DoorDash for GameTime" demo built for the IBM Experiential AI Learning Lab.
A single agentic-AI service helps a sports fan order food without missing the
game by combining live wait-time data, the user's seat location, and a
foundation-model-generated explanation.

The agent's foundation-model layer is **provider-pluggable** — you can run it
against IBM **watsonx.ai**, any **OpenAI-compatible** endpoint (vLLM, Ollama,
LM Studio, OpenAI itself), or a fully offline **mock** provider. The UI always
displays the provider name as **"IBM WatsonX"** per the project requirements.

---

## ⚡ Quick start

```bash
cd /Users/laurenturney/Documents/IBM/DOOR_DASH_GAMETIME
bash start.sh
```

`start.sh` creates a venv, installs dependencies, copies `.env.example → .env`
on first run, and launches Streamlit at <http://localhost:8501>.

To run manually:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run frontend/app.py
```

---

## 🧠 What the agent does

For every recommendation request the agent runs a small set of *tools* against
the synthetic stadium dataset, then asks the configured LLM to write a
plain-English explanation:

| Tool | Purpose |
| --- | --- |
| `tool_lag_intensity(minute)` | Looks up the lag period (low / medium / high / very_high) for a moment in the game. |
| `tool_nearest_concession(seat)` | Finds the closest concession stand to a fan's seat. |
| `tool_concession_status()` | Returns a live snapshot (queue, line wait, prep, delivery ETA) for every concession. |
| `tool_score_concessions(seat, item, method)` | Scores every concession that can serve the chosen item — for delivery vs. pickup. |
| `tool_find_best_order_window(...)` | Sweeps the next 25 game-minutes for a lower-wait window ("should I wait 5 minutes?"). |
| `tool_pick_default_item(intensity)` | Falls back to a quick item during high-lag periods, an entree otherwise. |

`recommend_order(...)` orchestrates these tools, then calls
`backend.llm_provider.complete(...)` to generate the human-readable
recommendation paragraph.

---

## 🔌 Switching the LLM provider

Edit `.env`:

```bash
# Default — fully offline, no API needed
LLM_PROVIDER=mock

# IBM watsonx.ai
LLM_PROVIDER=watsonx
WATSONX_APIKEY=<your IBM Cloud key>
WATSONX_PROJECT_ID=<your watsonx.ai project id>
WATSONX_URL=https://us-south.ml.cloud.ibm.com
WATSONX_MODEL_ID=ibm/granite-3-8b-instruct

# Any OpenAI-compatible endpoint (vLLM, Ollama, LM Studio, OpenAI)
LLM_PROVIDER=custom
CUSTOM_LLM_BASE_URL=http://localhost:8080/v1
CUSTOM_LLM_API_KEY=not-needed
CUSTOM_LLM_MODEL=llama-3.1-8b-instruct
```

Restart Streamlit (`Ctrl+C`, then `bash start.sh`).

---

## 🗂️ Project layout

```
DOOR_DASH_GAMETIME/
├── backend/
│   ├── agent.py              ← Single-agent system + tool methods
│   └── llm_provider.py       ← watsonx / OpenAI-compat / mock backends
├── data/
│   └── synthetic_data.py     ← Champions Arena, menus, lag-time generator
├── frontend/
│   └── app.py                ← Streamlit UI (Order, Game Status, Stadium tabs)
├── .env / .env.example       ← Provider configuration
├── requirements.txt
├── start.sh
└── README.md
```

---

## 🏟️ Synthetic data

A single mock stadium is generated at import time:

- **Champions Arena** — 660 seats across 11 sections (lower / club / upper / VIP).
- **5 concession stands** with floor + area metadata, menu coverage,
  per-section walking distance, and base capacity.
- **Menus** — 17 items across food / snacks / beverages / desserts, each with
  a price, prep time, calories and tags (`quick`, `entree`, `shareable`,
  `grab-and-go`, `21+`).
- **Game schedule** — a 100-minute event with 5 game periods and 11 lag-time
  windows (`tipoff_rush`, `mid_game`, `halftime`, `crunch_time`, …).
- **Wait-time generator** — `generate_wait_times(minute, concession_id)`
  returns a deterministic-but-lively snapshot that scales with the lag-period
  intensity multiplier (1× → 4×).

Inspect everything with:

```bash
python data/synthetic_data.py | python -m json.tool | less
```

---

## 🎬 Demo walkthrough

1. **Pick a section + seat** in the sidebar.
2. **Drag the game-time slider** to simulate moving through the game — the
   live concession panel updates immediately.
3. On the **Order** tab, choose delivery or pickup, optionally pick a menu
   item, and click **Get AI Recommendation**.
4. The agent shows the recommended item + concession, the timing breakdown,
   and a "best future window" hint if waiting would help.
5. Click **Place this order** — it shows up in the sidebar order history.

Try these scenarios:

| Minute | Lag | Try |
| --- | --- | --- |
| 10  | low        | Order delivery — should be ~10 min, 0 min away from the game. |
| 50  | very high  | Halftime rush — agent suggests grab-and-go items or a different window. |
| 65  | low        | Mid-3rd lull — fast delivery again. |
| 90  | medium     | Crunch time — the agent typically nudges you to order *now*. |

---

## 🧪 Component smoke tests

```bash
# Synthetic data
python data/synthetic_data.py

# LLM provider (mock by default)
python backend/llm_provider.py

# Single-agent recommendations across two scenarios
python backend/agent.py
```

---

## 📝 Notes

- The UI always shows the provider as **"IBM WatsonX"** regardless of the live
  backend (hard-coded in `backend.llm_provider.DISPLAY_PROVIDER_NAME`).
- The watsonx SDK is listed in `requirements.txt` but is only loaded when
  `LLM_PROVIDER=watsonx` — `mock` and `custom` modes don't import it.
- All wait-time numbers are **deterministic** for a given `(minute, concession)`
  pair, so the UI and the agent's analysis always agree.
