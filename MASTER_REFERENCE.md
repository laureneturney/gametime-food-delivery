# 🏟️ GAMETIME FOOD DELIVERY - MASTER REFERENCE

## 🎯 ULTIMATE QUICK START

**Copy this command and run it:**

```bash
cd /Users/laurenturney/Documents/IBM/DOOR_DASH_GAMETIME && bash start.sh
```

**That's all you need!** Everything else is automatic.

---

## 📋 COMPLETE FILE MANIFEST

### Documentation Files (Read These)
- [START_HERE.txt](START_HERE.txt) - **Quick reference card**
- [README.md](README.md) - Full documentation
- [QUICK_START.md](QUICK_START.md) - Fast setup guide
- [SETUP_GUIDE.md](SETUP_GUIDE.md) - Detailed guide
- [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) - Project overview

### Code Files (What Actually Runs)
- [frontend/app.py](frontend/app.py) - Streamlit UI (450+ lines)
- [backend/agent.py](backend/agent.py) - AI agent (340+ lines)
- [backend/llm_provider.py](backend/llm_provider.py) - LLM support (150+ lines)
- [data/synthetic_data.py](data/synthetic_data.py) - Data generation (280+ lines)

### Configuration Files
- [.env](.env) - Environment variables
- [requirements.txt](requirements.txt) - Dependencies
- [start.sh](start.sh) - Startup script (executable)

---

## 🎮 STEP-BY-STEP OPERATION

### Initial Setup (First Time Only)
```bash
cd /Users/laurenturney/Documents/IBM/DOOR_DASH_GAMETIME
bash start.sh
```

The script will:
1. Create Python virtual environment
2. Install all dependencies
3. Create .env configuration
4. Launch Streamlit
5. Open browser automatically

### On Subsequent Runs
```bash
cd /Users/laurenturney/Documents/IBM/DOOR_DASH_GAMETIME
bash start.sh
```

Or manually:
```bash
source venv/bin/activate
streamlit run frontend/app.py
```

### Stop the Application
Press `Ctrl+C` in the terminal

---

## 🧪 COMPONENT TESTING

### Quick Health Check
```bash
cd /Users/laurenturney/Documents/IBM/DOOR_DASH_GAMETIME
python data/synthetic_data.py
python backend/agent.py
```

Expected: JSON output with recommendations

---

## ⚙️ LLM PROVIDER CONFIGURATION

### Default (Already Configured)
```
LLM_PROVIDER=mock
```
No additional setup needed. Works immediately.

### Switch to Watson
Edit `.env`:
```
LLM_PROVIDER=watsonx
WATSONX_APIKEY=your_api_key_from_ibm_cloud
WATSONX_PROJECT_ID=your_project_id_from_ibm_cloud
```

### Switch to Custom/OpenAI
Edit `.env`:
```
LLM_PROVIDER=custom
CUSTOM_LLM_BASE_URL=http://localhost:8080/v1
CUSTOM_LLM_MODEL=llama-3.1-8b-instruct
```

Then restart Streamlit.

---

## 🎯 APPLICATION WALKTHROUGH

### 1. UI Opens at http://localhost:8501

### 2. Select Your Seat
- Choose section from dropdown
- Select seat number
- View section info

### 3. Explore the Three Tabs

**Tab 1: Game**
- Current game time display
- Current lag intensity
- Game timeline slider (0-100 minutes)
- Lag periods reference

**Tab 2: Ordering** (Main Tab)
- Left column: Seat selection, menu
- Right column: Concession status, recommendations
- Get AI recommendation button
- Place order button

**Tab 3: Info**
- Stadium statistics
- How it works explanation
- Lag intensity guide

### 4. Get Recommendation Flow
```
Select seat → Choose delivery method → Click "Get Recommendation"
             ↓
         AI analyzes:
         • Current game time
         • Lag intensity
         • Wait times at all concessions
         • Distance from seat
         • Prep times
             ↓
    Returns recommendation with:
    • Best item to order
    • Best concession location
    • Total time estimate
    • Time away from game
    • Detailed reasoning
```

### 5. Place Order
- Review recommendation
- Click "Place Order"
- See confirmation
- Order appears in sidebar history

---

## 📊 GAME TIMELINE REFERENCE

Use the slider to test these important moments:

| Time | Period | Lag | Best Action |
|------|--------|-----|------------|
| 5 min | Early | Low | ✅ BEST - Order now |
| 10 min | Early | Low | ✅ BEST - Order now |
| 15 min | Early | Low | ✅ BEST - Order now |
| 20 min | End P1 | High | Consider quick items |
| 30 min | Mid-Game | Low | ✅ Good time |
| 40 min | Pre-HT | Very High | Start of rush |
| 50 min | Halftime | Very High | ❌ AVOID - Very busy |
| 60 min | Post-HT | High | Still busy |
| 70 min | Mid P3 | Low | ✅ Good time |
| 85 min | Late | Low | ✅ Good time |
| 100 min | End | Medium | Game ending |

---

## 🛠️ COMMON ISSUES & FIXES

| Problem | Solution |
|---------|----------|
| Port 8501 in use | `streamlit run frontend/app.py --server.port 8502` |
| "ModuleNotFoundError" | `source venv/bin/activate && pip install -r requirements.txt` |
| Watson API fails | `LLM_PROVIDER=mock` in .env |
| Venv won't activate | Check path: `source venv/bin/activate` |
| Nothing happens | Check if Streamlit is running: `streamlit run frontend/app.py` |
| Clear cache issues | `streamlit cache clear` |

---

## 📁 DIRECTORY LAYOUT

```
DOOR_DASH_GAMETIME/
│
├── frontend/
│   ├── __pycache__/
│   └── app.py                    ← Main Streamlit UI
│
├── backend/
│   ├── __pycache__/
│   ├── __init__.py
│   ├── agent.py                  ← AI agent logic
│   └── llm_provider.py           ← LLM integration
│
├── data/
│   ├── __pycache__/
│   ├── __init__.py
│   └── synthetic_data.py         ← Stadium data
│
├── .env                          ← Configuration (EDIT THIS to switch LLMs)
├── .gitignore
├── requirements.txt              ← Python dependencies
├── start.sh                      ← Run this to start
│
└── Documentation/
    ├── README.md
    ├── QUICK_START.md
    ├── SETUP_GUIDE.md
    ├── PROJECT_SUMMARY.md
    ├── TERMINAL_COMMANDS.sh
    ├── START_HERE.txt            ← Quick reference
    └── MASTER_REFERENCE.md       ← This file
```

---

## 🔧 ADVANCED COMMANDS

### Run Without UI (Backend Only)
```bash
cd /Users/laurenturney/Documents/IBM/DOOR_DASH_GAMETIME
source venv/bin/activate
python backend/agent.py
```

### Test Data Generation
```bash
cd /Users/laurenturney/Documents/IBM/DOOR_DASH_GAMETIME
python data/synthetic_data.py | python -m json.tool
```

### View Current Config
```bash
cat /Users/laurenturney/Documents/IBM/DOOR_DASH_GAMETIME/.env
```

### Check Virtual Environment
```bash
cd /Users/laurenturney/Documents/IBM/DOOR_DASH_GAMETIME
source venv/bin/activate
which python
pip list
```

### Troubleshoot Imports
```bash
cd /Users/laurenturney/Documents/IBM/DOOR_DASH_GAMETIME
source venv/bin/activate
python -c "import streamlit; import httpx; print('✅ All imports OK')"
```

---

## 📊 DATA STRUCTURE

### Stadium
- **Name:** Champions Arena
- **Capacity:** 5,000 seats
- **Sections:** 11 (Lower/Upper, Corners, Sidelines, VIP)

### Concessions
- **Count:** 4 locations
- **Distribution:** 2 lower level, 2 upper level
- **Distance Tracking:** From each section to each concession

### Menu
- **Food:** 8 items (hot dogs, burgers, pizza, nachos, popcorn, pretzel, wings, fries)
- **Beverages:** 5 items (soda, beer, water, lemonade, coffee)
- **Pricing:** $3.99 - $16.99
- **Prep Times:** 0-8 minutes

### Game Simulation
- **Duration:** 100 minutes (4 periods)
- **Lag Periods:** 6 defined intensity zones
- **Wait Times:** Dynamic, based on game minute and lag

---

## ✨ PROJECT STATISTICS

| Metric | Value |
|--------|-------|
| Total Lines of Code | 1,400+ |
| Python Modules | 4 |
| Frontend Components | 450+ lines |
| Backend Logic | 340+ lines |
| LLM Providers | 3 (Watson, OpenAI, Mock) |
| Documentation Pages | 6 |
| Synthetic Data Points | 100+ |
| UI Elements | 20+ |
| Game Scenarios | 100+ |

---

## 🎓 LEARNING RESOURCES

### Understand the Agent Logic
Read: [backend/agent.py](backend/agent.py)
Key methods:
- `recommend_order()` - Main recommendation engine
- `analyze_order_options()` - Option analysis
- `get_game_timeline()` - Timeline generation

### Understand the UI
Read: [frontend/app.py](frontend/app.py)
Key functions:
- `display_game_status()` - Game overview
- `display_recommendation()` - AI results
- `display_order_history()` - Order tracking

### Understand Data Generation
Read: [data/synthetic_data.py](data/synthetic_data.py)
Key classes:
- `StadiumDataGenerator` - All data generation

---

## 🚀 DEPLOYMENT CHECKLIST

✅ Project structure created
✅ All code files generated
✅ Synthetic data working
✅ Agent recommendations working
✅ Streamlit UI functional
✅ LLM providers configured
✅ Environment setup complete
✅ Startup script created
✅ Documentation written
✅ Components tested
✅ Ready to deploy

---

## 📞 QUICK SUPPORT

### Application Won't Start?
1. Check: `cd /Users/laurenturney/Documents/IBM/DOOR_DASH_GAMETIME`
2. Try: `source venv/bin/activate`
3. Try: `pip install -r requirements.txt`
4. Try: `streamlit run frontend/app.py`

### Getting Import Errors?
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### Want to Switch LLMs?
1. Edit `.env` file
2. Change `LLM_PROVIDER` value
3. Restart Streamlit

### Need to Clear Everything?
```bash
cd /Users/laurenturney/Documents/IBM/DOOR_DASH_GAMETIME
rm -rf venv __pycache__ .streamlit
bash start.sh  # This will rebuild everything
```

---

## 🎉 FINAL NOTES

This is a **complete, production-ready** application demonstrating:

✅ Agentic AI systems
✅ Multiple LLM provider integration
✅ Full-stack web development
✅ Synthetic data generation
✅ Real-time data simulation
✅ Production code practices

Everything you need is included. Just run:

```bash
cd /Users/laurenturney/Documents/IBM/DOOR_DASH_GAMETIME && bash start.sh
```

Then visit: **http://localhost:8501**

**Enjoy! 🏟️🍔🍺**

---

## 📚 DOCUMENT QUICK LINKS

- [Application Start](START_HERE.txt)
- [Full Documentation](README.md)
- [Quick Start Guide](QUICK_START.md)
- [Setup Guide](SETUP_GUIDE.md)
- [Project Summary](PROJECT_SUMMARY.md)
- [Terminal Commands](TERMINAL_COMMANDS.sh)
- **← You are here: MASTER_REFERENCE.md**

---

**Built with ❤️ for IBM Experiential AI Learning Lab**
