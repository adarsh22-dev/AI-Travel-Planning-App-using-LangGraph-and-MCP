import os
from langgraph.graph import END, START, StateGraph
from dotenv import load_dotenv

from agents import (
    supervisor_agent,
    flight_agent,
    hotel_agent,
    weather_agent,
    budget_agent,
    itinerary_agent,
    human_approval_agent,
    final_response_agent,
)
from state import TravelState

load_dotenv(override=True)
DATABASE_URL = os.getenv("DATABASE_URL")

AGENT_ORDER = [
    "flight_agent",
    "hotel_agent",
    "weather_agent",
    "budget_agent",
    "itinerary_agent",
]

ROUTE_MAP = {
    "flight_agent": "flight_agent",
    "hotel_agent": "hotel_agent",
    "weather_agent": "weather_agent",
    "budget_agent": "budget_agent",
    "itinerary_agent": "itinerary_agent",
    END: END,
}


def _selected_agents(state) -> list[str]:
    selected = state.get("selected_agents", [])
    return [a for a in AGENT_ORDER if a in selected]


def route_from_supervisor(state) -> str:
    selected = _selected_agents(state)
    if not selected:
        return END
    return selected[0]


def route_after_agent(current_agent: str):
    def route(state) -> str:
        selected = _selected_agents(state)
        idx = AGENT_ORDER.index(current_agent)
        for next_agent in AGENT_ORDER[idx + 1:]:
            if next_agent in selected:
                return next_agent
        if "itinerary_agent" in selected:
            return "itinerary_agent"
        return END
    return route


def build_graph():
    graph = StateGraph(TravelState)

    graph.add_node("supervisor", supervisor_agent)
    graph.add_node("flight_agent", flight_agent)
    graph.add_node("hotel_agent", hotel_agent)
    graph.add_node("weather_agent", weather_agent)
    graph.add_node("budget_agent", budget_agent)
    graph.add_node("itinerary_agent", itinerary_agent)
    graph.add_node("human_approval", human_approval_agent)
    graph.add_node("final_response", final_response_agent)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges("supervisor", route_from_supervisor, ROUTE_MAP)
    graph.add_conditional_edges("flight_agent", route_after_agent("flight_agent"), ROUTE_MAP)
    graph.add_conditional_edges("hotel_agent", route_after_agent("hotel_agent"), ROUTE_MAP)
    graph.add_conditional_edges("weather_agent", route_after_agent("weather_agent"), ROUTE_MAP)
    graph.add_conditional_edges("budget_agent", route_after_agent("budget_agent"), ROUTE_MAP)
    graph.add_edge("itinerary_agent", "human_approval")
    graph.add_edge("human_approval", "final_response")
    graph.add_edge("final_response", END)

    try:
        import psycopg
        from langgraph.checkpoint.postgres import PostgresSaver
        _conn = psycopg.connect(DATABASE_URL)
        _checkpointer = PostgresSaver(_conn)
        _checkpointer.setup()
        app = graph.compile(checkpointer=_checkpointer)
        print("[OK] PostgreSQL connected — memory enabled")
    except Exception as e:
        from langgraph.checkpoint.memory import MemorySaver
        app = graph.compile(checkpointer=MemorySaver())
        print(f"[WARN] PostgreSQL unavailable ({e}) — using in-memory checkpointer")

    return app


app = build_graph()
