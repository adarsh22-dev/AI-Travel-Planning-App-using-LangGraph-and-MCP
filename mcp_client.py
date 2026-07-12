import os
import sys
import asyncio
import time
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_groq import ChatGroq

load_dotenv(override=True)
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
AVIATION_STACK_API_KEY = os.getenv("AVIATIONSTACK_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

AVIATION_VENV_PYTHON = os.path.join(
    PROJECT_ROOT, "aviationstack-mcp", ".venv", "Scripts", "python.exe"
)
if not os.path.isfile(AVIATION_VENV_PYTHON):
    AVIATION_VENV_PYTHON = sys.executable

WEATHER_SERVER = os.path.join(PROJECT_ROOT, "custom_weather_mcp_server.py")

client = MultiServerMCPClient(
    {
        "tavily": {
            "transport": "streamable_http",
            "url": f"https://mcp.tavily.com/mcp/?tavilyApiKey={TAVILY_API_KEY}",
        },
        "aviationstack": {
            "transport": "stdio",
            "command": AVIATION_VENV_PYTHON,
            "args": ["-m", "aviationstack_mcp", "mcp", "run"],
            "env": {"AVIATION_STACK_API_KEY": AVIATION_STACK_API_KEY},
        },
        "weather": {
            "transport": "stdio",
            "command": sys.executable,
            "args": [WEATHER_SERVER],
            "env": {"OPENWEATHER_API_KEY": OPENWEATHER_API_KEY},
        },
    }
)

search_tool = None
aviation_tools = {}
weather_tool = None
forecast_tool = None

async def initialize_mcp():
    global search_tool, aviation_tools
    if search_tool is not None and aviation_tools:
        return
    tools = await client.get_tools()
    search_tool = next(t for t in tools if t.name == "tavily_search")
    aviation_tools = {t.name: t for t in tools if t.name != "tavily_search"}

async def initialize_weather_tools():
    global weather_tool, forecast_tool
    if weather_tool is not None:
        return
    tools = await client.get_tools()
    weather_tool = next(t for t in tools if t.name == "get_current_weather")
    forecast_tool = next(t for t in tools if t.name == "get_forecast")

async def tavily_mcp_search(query: str):
    await initialize_mcp()
    return await search_tool.ainvoke({"query": query})

async def aviation_mcp_call(tool_name: str, tool_args: dict = None):
    tools = await client.get_tools()
    tool = next(t for t in tools if t.name == tool_name)
    return await tool.ainvoke(tool_args or {})

async def get_airports():
    await initialize_mcp()
    tool = aviation_tools.get("list_airports")
    return await tool.ainvoke({}) if tool else "Airport tool unavailable"

async def get_airlines():
    await initialize_mcp()
    tool = aviation_tools.get("list_airlines")
    return await tool.ainvoke({}) if tool else "Airline tool unavailable"

async def weather_mcp_search(city: str):
    await initialize_weather_tools()
    return await weather_tool.ainvoke({"city": city})

async def forecast_mcp_search(city: str):
    await initialize_weather_tools()
    return await forecast_tool.ainvoke({"city": city})


def get_llm(model_name: str = "llama-3.3-70b-versatile"):
    return ChatGroq(model=model_name)

def extract_destination(query: str, model_name: str = "llama-3.3-70b-versatile"):
    llm = get_llm(model_name)
    prompt = f"""From this travel query, extract ONLY the destination city or country (not the origin).
If multiple are mentioned, pick the primary destination.
Return ONLY the destination name, nothing else.

Query: {query}"""
    return llm.invoke(prompt).content.strip()

def parse_json(text: str):
    start = text.find('{')
    end = text.rfind('}') + 1
    if start >= 0 and end > start:
        text = text[start:end]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None

def analyze_query(query: str, model_name: str = "llama-3.3-70b-versatile"):
    llm = get_llm(model_name)
    prompt = f"""Analyze this travel query and return a JSON object with these exact fields:
- destination: str (primary destination city/country, or empty string)
- origin: str (departure city if mentioned, empty string if not)
- duration_days: int (estimated trip length in days, 0 if unknown)
- budget: str (budget level: "Budget", "Moderate", "Premium", "Luxury", or empty)
- pace: str ("Relaxed", "Moderate", or "Packed", or empty)
- needs_flights: bool (whether flights are needed)
- needs_hotels: bool (whether hotels are needed)
- needs_weather: bool (whether weather info would be useful)
- travelers: int (number of travelers, 1 if not specified)
- interests: list of strings (mentioned activities/interests, empty list if none)

Query: {query}

Return ONLY valid JSON. No markdown, no extra text."""
    response = llm.invoke(prompt).content.strip()
    parsed = parse_json(response)
    if parsed:
        return parsed
    return {
        "destination": "", "origin": "", "duration_days": 0, "budget": "",
        "pace": "", "needs_flights": True, "needs_hotels": True,
        "needs_weather": True, "travelers": 1, "interests": [],
    }


async def main():
    query = "I want to visit Paris next week"
    analysis = analyze_query(query)
    print(f"Analysis: {analysis}")
    dest = extract_destination(query)
    print(f"Destination: {dest}")
    await initialize_mcp()
    await initialize_weather_tools()
    search_results = await tavily_mcp_search(f"Best hotels and attractions in {dest}")
    print(f"Search: {search_results[:200]}...")
    weather = await weather_mcp_search(dest)
    print(f"Weather: {weather}")

if __name__ == "__main__":
    asyncio.run(main())
