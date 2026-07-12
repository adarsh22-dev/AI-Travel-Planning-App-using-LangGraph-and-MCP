import os
import json
import time
import operator
import asyncio
import warnings
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_core.messages import AnyMessage, HumanMessage, AIMessage, SystemMessage
from mcp_client import (
    tavily_mcp_search, get_airports, get_airlines,
    aviation_mcp_call, extract_destination,
    forecast_mcp_search, weather_mcp_search,
    analyze_query, get_llm,
)
from prompts import (
    FLIGHT_SYSTEM_PROMPT, HOTEL_SYSTEM_PROMPT, WEATHER_SYSTEM_PROMPT,
    ITINERARY_SYSTEM_PROMPT, FLIGHT_PROMPT_TEMPLATE, HOTEL_PROMPT_TEMPLATE,
    WEATHER_PROMPT_TEMPLATE, ITINERARY_PROMPT_TEMPLATE,
)
from dotenv import load_dotenv

warnings.filterwarnings("ignore")
load_dotenv(override=True)
DATABASE_URL = os.getenv("DATABASE_URL")

def merge_dicts(a: dict, b: dict) -> dict:
    return {**a, **b}

class TravelState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    user_query: str
    query_analysis: dict
    model_name: str
    flight_results: str
    hotel_results: str
    weather_results: str
    itinerary: str
    llm_calls: Annotated[int, operator.add]
    agent_times: Annotated[dict, merge_dicts]
    active_agents: list

def query_analyzer(state: TravelState):
    t0 = time.time()
    llm = get_llm(state["model_name"])
    analysis = analyze_query(state["user_query"], state["model_name"])
    return {
        "query_analysis": analysis,
        "messages": [AIMessage(content=f"Query analyzed: {analysis.get('destination', 'unknown')}")],
        "llm_calls": 1,
        "agent_times": {"query_analyzer": round(time.time() - t0, 2)},
        "active_agents": [],
    }

# ── Async agent helpers (run concurrently via parallel_agents) ──

async def _run_flight(state: TravelState, llm):
    t0 = time.time()
    query = state["user_query"]
    try:
        airports, airlines = await asyncio.gather(
            aviation_mcp_call("list_airports"),
            aviation_mcp_call("list_airlines"),
            return_exceptions=True,
        )
        if isinstance(airports, Exception): airports = str(airports)
        if isinstance(airlines, Exception): airlines = str(airlines)
        prompt = FLIGHT_PROMPT_TEMPLATE.format(query=query, airports=str(airports)[:2500], airlines=str(airlines)[:2500])
        response = await asyncio.to_thread(
            llm.invoke,
            [SystemMessage(content=FLIGHT_SYSTEM_PROMPT), HumanMessage(content=prompt)]
        )
        flight_data = response.content
    except Exception as e:
        flight_data = f"Flight information currently unavailable. {str(e)}"
    return {
        "flight_results": flight_data,
        "agent_times": {"flight_agent": round(time.time() - t0, 2)},
        "llm_calls": 1,
        "messages": [AIMessage(content="Flight recommendations generated")],
    }

async def _run_hotel(state: TravelState, llm):
    t0 = time.time()
    try:
        raw = await tavily_mcp_search(f"Best hotels for {state['user_query']}")
        prompt = HOTEL_PROMPT_TEMPLATE.format(query=state['user_query'], raw_data=str(raw)[:4000])
        response = await asyncio.to_thread(
            llm.invoke,
            [SystemMessage(content=HOTEL_SYSTEM_PROMPT), HumanMessage(content=prompt)]
        )
        results = response.content
    except Exception as e:
        results = f"Hotel information currently unavailable. {str(e)}"
    return {
        "hotel_results": results,
        "agent_times": {"hotel_agent": round(time.time() - t0, 2)},
        "llm_calls": 1,
        "messages": [AIMessage(content="Hotel recommendations generated")],
    }

async def _run_weather(state: TravelState, llm):
    t0 = time.time()
    try:
        city = await asyncio.to_thread(extract_destination, state["user_query"], state["model_name"])
        w, f = await asyncio.gather(
            weather_mcp_search(city),
            forecast_mcp_search(city),
            return_exceptions=True,
        )
        if isinstance(w, Exception): w = str(w)
        if isinstance(f, Exception): f = str(f)
        prompt = WEATHER_PROMPT_TEMPLATE.format(city=city, query=state['user_query'], current=str(w)[:1500], forecast=str(f)[:3000])
        response = await asyncio.to_thread(
            llm.invoke,
            [SystemMessage(content=WEATHER_SYSTEM_PROMPT), HumanMessage(content=prompt)]
        )
        weather_results = response.content
    except Exception as e:
        weather_results = f"Weather data currently unavailable. {str(e)}"
    return {
        "weather_results": weather_results,
        "agent_times": {"weather_agent": round(time.time() - t0, 2)},
        "llm_calls": 1,
        "messages": [AIMessage(content="Weather information compiled")],
    }

def parallel_agents(state: TravelState):
    llm = get_llm(state["model_name"])
    analysis = state.get("query_analysis", {})

    async def run_all():
        tasks = []
        if analysis.get("needs_flights", True):
            tasks.append(_run_flight(state, llm))
        if analysis.get("needs_hotels", True):
            tasks.append(_run_hotel(state, llm))
        if analysis.get("needs_weather", True):
            tasks.append(_run_weather(state, llm))
        if not tasks:
            return {}

        results = await asyncio.gather(*tasks, return_exceptions=True)

        merged = {"llm_calls": 0, "agent_times": {}, "messages": [], "flight_results": "", "hotel_results": "", "weather_results": ""}
        for r in results:
            if isinstance(r, dict):
                for k in ("flight_results", "hotel_results", "weather_results"):
                    if r.get(k):
                        merged[k] = r[k]
                merged["llm_calls"] += r.get("llm_calls", 0)
                merged["agent_times"].update(r.get("agent_times", {}))
                merged["messages"].extend(r.get("messages", []))
        for r in results:
            if not isinstance(r, dict):
                merged["messages"].append(AIMessage(content=str(r)))
        return merged

    result = asyncio.run(run_all())
    return result

def itinerary_agent(state: TravelState):
    t0 = time.time()
    llm = get_llm(state["model_name"])
    prompt = ITINERARY_PROMPT_TEMPLATE.format(
        query=state['user_query'],
        flight=state.get('flight_results', 'Not requested')[:2000],
        hotel=state.get('hotel_results', 'Not requested')[:2000],
        weather=state.get('weather_results', 'Not requested')[:2000],
    )
    response = llm.invoke([
        SystemMessage(content=ITINERARY_SYSTEM_PROMPT),
        HumanMessage(content=prompt)
    ])
    return {
        "itinerary": response.content,
        "messages": [response],
        "llm_calls": 1,
        "agent_times": {"itinerary_agent": round(time.time() - t0, 2)},
    }

graph = StateGraph(TravelState)
graph.add_node("query_analyzer", query_analyzer)
graph.add_node("parallel_agents", parallel_agents)
graph.add_node("itinerary_agent", itinerary_agent)

graph.add_edge(START, "query_analyzer")
graph.add_edge("query_analyzer", "parallel_agents")
graph.add_edge("parallel_agents", "itinerary_agent")
graph.add_edge("itinerary_agent", END)

_checkpointer = None
_conn = None
try:
    import psycopg
    _conn = psycopg.connect(DATABASE_URL)
    _checkpointer = PostgresSaver(_conn)
    _checkpointer.setup()
    app = graph.compile(checkpointer=_checkpointer)
    print("[OK] PostgreSQL connected — memory enabled")
except Exception as e:
    app = graph.compile()
    print(f"[WARN] PostgreSQL unavailable ({e}) — running without memory")

if __name__ == "__main__":
    import uuid
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    user_input = input("Enter travel request: ")
    result = app.invoke(
        {
            "messages": [HumanMessage(content=user_input)],
            "user_query": user_input,
            "query_analysis": {},
            "model_name": "llama-3.3-70b-versatile",
            "flight_results": "",
            "hotel_results": "",
            "weather_results": "",
            "itinerary": "",
            "llm_calls": 0,
            "agent_times": {},
            "active_agents": [],
        },
        config=config,
    )
    print("\nFINAL RESPONSE:\n")
    for msg in result["messages"]:
        print(msg.content)
