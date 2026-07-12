# AI Travel Planning System using LangGraph

A real-time multi-agent AI travel planner with a glassmorphism Streamlit UI. Uses LangGraph to orchestrate parallel agent execution — flight search, hotel search, weather data, and itinerary generation — all running concurrently for maximum speed.

## Features

- **Parallel Agent Execution** — Flight, hotel, and weather agents run concurrently via `asyncio.gather`, reducing total response time
- **5-Step Trip Wizard** — Where → When → Who → Preferences → Review with interactive folium route maps
- **Glassmorphism UI** — Dark theme with backdrop blur, skeleton loaders, smooth animations, theme presets (Ocean, Emerald, Amethyst, Ruby, Amber, Rose)
- **Tabbed Results Dashboard** — Flight / Hotel / Weather / Itinerary tabs with stat cards and export
- **LLM-Refined Output** — Each agent formats raw API data through Groq LLMs into structured markdown (tables, budgets, day-by-day itineraries)
- **Autosave & History** — Form data auto-saves to `.travel_cache/autosave.json`; previous trips persist across reruns
- **Keyboard Shortcuts** — Ctrl+Enter to plan, 1-5 for wizard steps, Escape for back
- **PostgreSQL Memory** — Conversation checkpointing for multi-turn context (optional, graceful fallback)

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | LangGraph (StateGraph) |
| Agents | Query Analyzer, Flight, Hotel, Weather, Itinerary |
| LLM | Groq (Llama 3.3 70B / Mixtral 8x7B / Gemma 2 9B) |
| UI | Streamlit + Folium maps |
| Database | PostgreSQL (via `PostgresSaver`) |
| Search API | Tavily MCP |
| Flight API | AviationStack MCP |
| Weather API | OpenWeatherMap (custom MCP server) |

## Graph Architecture

```
START → query_analyzer → parallel_agents → itinerary_agent → END
                              ├── _run_flight (async)
                              ├── _run_hotel (async)
                              └── _run_weather (async)
```

- `query_analyzer`: Extracts destination, dates, travelers, interests, and routing flags
- `parallel_agents`: Fans out to flight/hotel/weather via `asyncio.gather` with `return_exceptions=True` for graceful degradation
- `itinerary_agent`: Compiles all results into a day-by-day plan with budget tables and practical tips
- **Reducers**: `llm_calls` (sum) and `agent_times` (dict merge) handle concurrent state updates correctly

## Setup

### Prerequisites

- Python 3.10+
- PostgreSQL 14+ (optional — app runs without it)

### 1. Create Environment

```bash
python -m venv langgraph_env3
source langgraph_env3/bin/activate    # Linux/Mac
langgraph_env3\Scripts\activate       # Windows
```

### 2. Install Dependencies

```bash
pip install langgraph langchain langchain-groq langchain-community langchain-tavily psycopg[binary] psycopg_pool python-dotenv tavily-python requests streamlit streamlit-folium folium
pip install -U "psycopg[binary,pool]" langgraph-checkpoint-postgres
```

### 3. Install AviationStack MCP (sub-project)

```bash
cd aviationstack-mcp
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

### 4. Setup PostgreSQL (optional)

```sql
CREATE DATABASE langgraph_memory_demo;
```

### 5. Environment Variables

Create `.env` in the project root:

```
GROQ_API_KEY=your_groq_api_key
TAVILY_API_KEY=your_tavily_api_key
AVIATIONSTACK_API_KEY=your_aviationstack_api_key
OPENWEATHER_API_KEY=your_openweathermap_api_key
DATABASE_URL=postgresql://postgres:postgres@localhost:5433/langgraph_memory_demo
```

### 6. Get API Keys

| Service | URL |
|---------|-----|
| Groq | https://console.groq.com |
| Tavily | https://tavily.com |
| AviationStack | https://aviationstack.com |
| OpenWeatherMap | https://openweathermap.org |

## Running

### Terminal (headless)

```bash
python main.py
```

### Streamlit Web App

```bash
streamlit run frontend.py
```

## Example Prompt

```
Plan a complete 7 days Japan trip including flights, hotels and sightseeing under 2 lakhs.
```

## Project Structure

```
.
├── main.py                         # LangGraph graph + agent functions
├── mcp_client.py                   # MCP client (Tavily, AviationStack, Weather)
├── frontend.py                     # Streamlit UI (wizard, map, dashboard, autosave)
├── custom_weather_mcp_server.py    # OpenWeatherMap MCP server
├── aviationstack-mcp/              # AviationStack MCP sub-project
├── .travel_cache/                  # Autosave data (git-ignored)
└── travel_plans/                   # Exported trip files
```

## Design

- **Color system**: Theme-aware CSS with `--accent`, `--glow`, `--dim` parameters — all derived from a single hex color
- **Animations**: `slideUp`, `fadeIn`, `scaleIn`, `nodePulse`, `gradientShift`, `shimmer` for skeleton loading
- **Custom SVG icons**: 30+ inline SVG icon components (plane, hotel, sun, compass, etc.) — zero external dependencies
- **Responsive**: Breakpoints at 768px collapse metrics, compress hero, stack columns
