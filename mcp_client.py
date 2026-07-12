import os
import asyncio
import json
from datetime import datetime
import requests
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from tavily import TavilyClient

load_dotenv(override=True)

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
AVIATION_STACK_API_KEY = os.getenv("AVIATIONSTACK_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

_tavily_client = None

def _get_tavily():
    global _tavily_client
    if _tavily_client is None:
        _tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
    return _tavily_client

async def tavily_mcp_search(query: str):
    client = _get_tavily()
    result = await asyncio.to_thread(client.search, query=query, max_results=5)
    return _format_tavily(result)

def _format_tavily(response):
    results = []
    for i, r in enumerate(response.get("results", []), 1):
        title = r.get("title", "Unknown")
        url = r.get("url", "")
        snippet = r.get("content", "").strip()
        if len(snippet) > 300:
            snippet = snippet[:300].rsplit(" ", 1)[0] + "..."
        results.append(f"{i}. **{title}**\n   {url}\n   {snippet}")
    return "\n\n".join(results)

AVIATION_BASE = "https://api.aviationstack.com/v1"

_AVIATION_ENDPOINTS = {
    "list_airports": "airports",
    "list_airlines": "airlines",
    "flights_with_airline": "flights",
    "historical_flights_by_date": "flights",
    "flight_arrival_departure_schedule": "timetable",
    "future_flights_arrival_departure_schedule": "flightsFuture",
    "random_aircraft_type": "aircraft_types",
    "random_airplanes_detailed_info": "airplanes",
    "random_countries_detailed_info": "countries",
    "random_cities_detailed_info": "cities",
    "list_routes": "routes",
    "list_taxes": "taxes",
}

async def _aviation_api_call(endpoint: str, params: dict = None):
    url = f"{AVIATION_BASE}/{endpoint}"
    p = {"access_key": AVIATION_STACK_API_KEY}
    if params:
        p.update(params)
    resp = await asyncio.to_thread(requests.get, url, params=p)
    return resp.json()

async def aviation_mcp_call(tool_name: str, tool_args: dict = None):
    endpoint = _AVIATION_ENDPOINTS.get(tool_name)
    if not endpoint:
        return f"Unknown aviation tool: {tool_name}"
    return await _aviation_api_call(endpoint, tool_args or {})

async def get_airports():
    return await aviation_mcp_call("list_airports")

async def get_airlines():
    return await aviation_mcp_call("list_airlines")

WEATHER_BASE = "https://api.openweathermap.org/data/2.5"

async def _weather_api_call(endpoint: str, city: str):
    url = f"{WEATHER_BASE}/{endpoint}"
    params = {"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric"}
    resp = await asyncio.to_thread(requests.get, url, params=params)
    data = resp.json()
    if resp.status_code != 200:
        return data
    return data

async def weather_mcp_search(city: str):
    data = await _weather_api_call("weather", city)
    if "main" not in data:
        return data
    return {
        "city": data.get("name", city),
        "temperature_c": data["main"]["temp"],
        "feels_like_c": data["main"]["feels_like"],
        "humidity": data["main"]["humidity"],
        "condition": data["weather"][0]["description"],
        "wind_speed": data["wind"]["speed"],
    }

async def forecast_mcp_search(city: str):
    data = await _weather_api_call("forecast", city)
    if "list" not in data:
        return data
    forecast = []
    for item in data["list"][:5]:
        forecast.append({
            "datetime": item["dt_txt"],
            "temperature": item["main"]["temp"],
            "weather": item["weather"][0]["description"],
        })
    return {"city": city, "forecast": forecast}

async def _wikipedia_page_image(city: str):
    UA = {"User-Agent": "AITravelPlanner/1.0"}
    try:
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(city)}"
        resp = await asyncio.to_thread(requests.get, url, headers=UA, timeout=10)
        if resp.status_code != 200:
            # try with state/country qualifier for smaller cities
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(f'{city} city')}"
            resp = await asyncio.to_thread(requests.get, url, headers=UA, timeout=10)
            if resp.status_code != 200:
                return None, None, None
        data = resp.json()
        thumb = (data.get("thumbnail") or {}).get("source")
        extract = data.get("extract", "")[:200]
        title = data.get("title", city)
        return thumb, extract, data.get("pageid")
    except:
        return None, None, None

async def _wikipedia_page_images(page_id: int, count: int):
    UA = {"User-Agent": "AITravelPlanner/1.0"}
    try:
        api = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "pageids": page_id,
            "generator": "images",
            "gimlimit": count,
            "prop": "imageinfo",
            "iiprop": "url",
            "format": "json",
        }
        resp = await asyncio.to_thread(requests.get, api, params=params, headers=UA, timeout=10)
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        urls = []
        for pid, pdata in pages.items():
            if int(pid) < 0:
                continue
            info = pdata.get("imageinfo", [])
            if info and info[0].get("url", "").lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                urls.append(info[0]["url"])
        return urls[:count]
    except:
        return []

def _wikipedia_page_image_sync(city: str):
    UA = {"User-Agent": "AITravelPlanner/1.0"}
    try:
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(city)}"
        resp = requests.get(url, headers=UA, timeout=10)
        if resp.status_code != 200:
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(f'{city} city')}"
            resp = requests.get(url, headers=UA, timeout=10)
            if resp.status_code != 200:
                return None, None, None
        data = resp.json()
        thumb = (data.get("thumbnail") or {}).get("source")
        extract = data.get("extract", "")[:200]
        return thumb, extract, data.get("pageid")
    except:
        return None, None, None

def _wikipedia_page_images_sync(page_id: int, count: int):
    UA = {"User-Agent": "AITravelPlanner/1.0"}
    try:
        api = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "pageids": page_id,
            "generator": "images",
            "gimlimit": count,
            "prop": "imageinfo",
            "iiprop": "url",
            "format": "json",
        }
        resp = requests.get(api, params=params, headers=UA, timeout=10)
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        urls = []
        for pid, pdata in pages.items():
            if int(pid) < 0:
                continue
            info = pdata.get("imageinfo", [])
            if info and info[0].get("url", "").lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                urls.append(info[0]["url"])
        return urls[:count]
    except:
        return []

def get_destination_photos_sync(city: str, count: int = 6):
    thumb, extract, page_id = _wikipedia_page_image_sync(city)
    photos = []
    if thumb:
        photos.append({"src": thumb, "alt": city, "caption": extract[:200] if extract else ""})
    if page_id:
        more = _wikipedia_page_images_sync(page_id, count - 1)
        for url in more:
            photos.append({"src": url, "alt": city, "caption": ""})
    return photos

def _tavily_search_sync(query: str):
    client = _get_tavily()
    result = client.search(query=query, max_results=5)
    return _format_tavily(result)

def get_destination_events_sync(city: str):
    try:
        q = f"Upcoming events and festivals in {city} {datetime.now().year}"
        return _tavily_search_sync(q)
    except:
        return ""

# Async versions (for use inside async context)
async def get_destination_photos(city: str, count: int = 6):
    thumb, extract, page_id = await _wikipedia_page_image(city)
    photos = []
    if thumb:
        photos.append({"src": thumb, "alt": city, "caption": extract[:200] if extract else ""})
    if page_id:
        more = await _wikipedia_page_images(page_id, count - 1)
        for url in more:
            photos.append({"src": url, "alt": city, "caption": ""})
    return photos

async def get_destination_events(city: str):
    try:
        q = f"Upcoming events and festivals in {city} {datetime.now().year}"
        return await tavily_mcp_search(q)
    except:
        return ""

def get_llm(model_name: str = "llama-3.3-70b-versatile"):
    return ChatGroq(model=model_name)

def parse_json(text: str):
    start = text.find('{')
    end = text.rfind('}') + 1
    if start >= 0 and end > start:
        text = text[start:end]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None

def extract_destination(query: str, model_name: str = "llama-3.3-70b-versatile"):
    llm = get_llm(model_name)
    prompt = f"""From this travel query, extract ONLY the destination city or country (not the origin).
If multiple are mentioned, pick the primary destination.
Return ONLY the destination name, nothing else.

Query: {query}"""
    return llm.invoke(prompt).content.strip()

def analyze_query(query: str, model_name: str = "llama-3.3-70b-versatile"):
    llm = get_llm(model_name)
    prompt = f"""Analyze this travel query and return a JSON object with these exact fields:
- destination: str (primary destination city/country, or empty string)
- origin: str (departure city if mentioned, empty string if not)
- duration_days: int (estimated trip length in days, 0 if unknown)
- budget: str ("Budget", "Moderate", "Premium", "Luxury", or empty)
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
    search_results = await tavily_mcp_search(f"Best hotels and attractions in {dest}")
    print(f"Search: {str(search_results)[:200]}...")
    weather = await weather_mcp_search(dest)
    print(f"Weather: {weather}")

if __name__ == "__main__":
    asyncio.run(main())
