import asyncio
import json
import time
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import interrupt

from config import get_llm
from mcp_client import (
    tavily_mcp_search, aviation_mcp_call,
    weather_mcp_search, forecast_mcp_search,
    extract_destination,
)
from prompts import (
    FLIGHT_SYSTEM_PROMPT, HOTEL_SYSTEM_PROMPT, WEATHER_SYSTEM_PROMPT,
    ITINERARY_SYSTEM_PROMPT, FLIGHT_PROMPT_TEMPLATE, HOTEL_PROMPT_TEMPLATE,
    WEATHER_PROMPT_TEMPLATE, ITINERARY_PROMPT_TEMPLATE,
    BUDGET_SYSTEM_PROMPT, BUDGET_PROMPT_TEMPLATE,
    FINAL_RESPONSE_SYSTEM_PROMPT,
)
from state import TravelState


FALLBACK_MODELS = ["llama-3.1-8b-instant", "gemma2-9b-it", "mixtral-8x7b-32768"]

def _llm_text(system: str, prompt: str, model: str = "llama-3.3-70b-versatile") -> str:
    return _llm_invoke(system, prompt, model).content

def _llm_invoke(system: str, prompt: str, model: str = "llama-3.3-70b-versatile"):
    _models = [model] + [m for m in FALLBACK_MODELS if m != model]
    last_err = None
    for m in _models:
        llm = get_llm(m)
        try:
            return llm.invoke([
                SystemMessage(content=system),
                HumanMessage(content=prompt),
            ])
        except Exception as e:
            last_err = e
            if "429" in str(e) or "rate_limit" in str(e).lower():
                continue
            raise
    raise last_err


def _json_from_llm(text: str) -> dict:
    start = text.index("{")
    end = text.rindex("}") + 1
    return json.loads(text[start:end])


def supervisor_agent(state: TravelState):
    t0 = time.time()
    query = state["user_query"]
    model = state.get("model_name", "llama-3.3-70b-versatile")

    guardrail_prompt = f"""
Determine whether the following request is a valid travel planning request.

Return only JSON in this format:
{{
    "allowed": true,
    "reason": ""
}}

User request:
{query}
"""

    guardrail_raw = _llm_text(
        "You are an input validation guardrail. Return strict JSON only.",
        guardrail_prompt,
        model,
    )

    try:
        guardrail_result = _json_from_llm(guardrail_raw)
    except (ValueError, json.JSONDecodeError):
        guardrail_result = {"allowed": True, "reason": ""}

    if not guardrail_result.get("allowed", True):
        reason = guardrail_result.get("reason", "Request rejected by input guardrail.")
        return {
            "selected_agents": [],
            "trip_constraints": {},
            "supervisor_reasoning": reason,
            "messages": [AIMessage(content=f"Guardrail blocked request: {reason}")],
            "llm_calls": state.get("llm_calls", 0) + 1,
            "agent_times": {"supervisor": round(time.time() - t0, 2)},
        }

    routing_prompt = f"""
You are the supervisor of a real-world multi-agent travel planning system.
Your job is to select ONLY the agents that are actually needed.

Available agents:
- flight_agent: only when flights/airlines/airfare guidance is requested
- hotel_agent: only when hotels/accommodation/stays are requested
- weather_agent: only when weather/climate/forecast is requested
- budget_agent: only when budget/cost/affordability is mentioned
- itinerary_agent: only when a day-by-day plan or schedule is needed

Return only JSON. Do NOT include agents that aren't explicitly needed.
Example: "Plan a trip to Paris" -> select only ["itinerary_agent"]
Example: "Find cheap flights to London" -> select only ["flight_agent"]
Example: "5-star hotels in Dubai with budget" -> select only ["hotel_agent", "budget_agent"]

Schema:
{{
  "selected_agents": [],
  "trip_constraints": {{
    "destination": "",
    "origin": "",
    "duration": "",
    "budget": "",
    "travel_style": "",
    "special_preferences": []
  }},
  "reasoning": ""
}}

User request:
{query}
"""

    raw = _llm_text(
        "You route work to specialist agents. Return strict JSON only.",
        routing_prompt,
        model,
    )

    parsed = _json_from_llm(raw)
    selected = parsed["selected_agents"]
    constraints = parsed["trip_constraints"]

    return {
        "selected_agents": selected,
        "trip_constraints": constraints,
        "supervisor_reasoning": parsed["reasoning"],
        "messages": [AIMessage(content="Supervisor created the agent plan.")],
        "llm_calls": state.get("llm_calls", 0) + 1,
        "agent_times": {"supervisor": round(time.time() - t0, 2)},
    }


def flight_agent(state: TravelState):
    t0 = time.time()
    query = state["user_query"]
    model = state.get("model_name", "llama-3.3-70b-versatile")

    airports = asyncio.run(aviation_mcp_call("list_airports"))
    airlines = asyncio.run(aviation_mcp_call("list_airlines"))

    if isinstance(airports, Exception):
        airports = str(airports)
    if isinstance(airlines, Exception):
        airlines = str(airlines)

    prompt = FLIGHT_PROMPT_TEMPLATE.format(
        query=query,
        airports=str(airports)[:2500],
        airlines=str(airlines)[:2500],
    )

    response = _llm_invoke(FLIGHT_SYSTEM_PROMPT, prompt, model)

    return {
        "flight_results": response.content,
        "messages": [AIMessage(content="Flight recommendations generated")],
        "llm_calls": 1,
        "agent_times": {"flight_agent": round(time.time() - t0, 2)},
    }


def hotel_agent(state: TravelState):
    t0 = time.time()
    query = state["user_query"]
    model = state.get("model_name", "llama-3.3-70b-versatile")

    raw = asyncio.run(tavily_mcp_search(f"Best hotels for {query}"))
    prompt = HOTEL_PROMPT_TEMPLATE.format(query=query, raw_data=str(raw)[:4000])

    response = _llm_invoke(HOTEL_SYSTEM_PROMPT, prompt, model)

    return {
        "hotel_results": response.content,
        "messages": [AIMessage(content="Hotel recommendations generated")],
        "llm_calls": 1,
        "agent_times": {"hotel_agent": round(time.time() - t0, 2)},
    }


def weather_agent(state: TravelState):
    t0 = time.time()
    query = state["user_query"]
    model = state.get("model_name", "llama-3.3-70b-versatile")

    constraints = state.get("trip_constraints", {})
    city = constraints.get("destination", "")
    if not city:
        city = extract_destination(query, model)

    w = asyncio.run(weather_mcp_search(city))
    f = asyncio.run(forecast_mcp_search(city))

    if isinstance(w, Exception):
        w = str(w)
    if isinstance(f, Exception):
        f = str(f)

    prompt = WEATHER_PROMPT_TEMPLATE.format(
        city=city,
        query=query,
        current=str(w)[:1500],
        forecast=str(f)[:3000],
    )

    response = _llm_invoke(WEATHER_SYSTEM_PROMPT, prompt, model)

    return {
        "weather_results": response.content,
        "messages": [AIMessage(content="Weather information compiled")],
        "llm_calls": 1,
        "agent_times": {"weather_agent": round(time.time() - t0, 2)},
    }


def budget_agent(state: TravelState):
    t0 = time.time()
    model = state.get("model_name", "llama-3.3-70b-versatile")

    prompt = BUDGET_PROMPT_TEMPLATE.format(
        query=state["user_query"],
        constraints=state.get("trip_constraints", {}),
        flight=state.get("flight_results", "Not available")[:2000],
        hotel=state.get("hotel_results", "Not available")[:2000],
        weather=state.get("weather_results", "Not available")[:1000],
    )

    response = _llm_invoke(BUDGET_SYSTEM_PROMPT, prompt, model)

    return {
        "budget_results": response.content,
        "messages": [AIMessage(content="Budget analysis completed")],
        "llm_calls": 1,
        "agent_times": {"budget_agent": round(time.time() - t0, 2)},
    }


def itinerary_agent(state: TravelState):
    t0 = time.time()
    model = state.get("model_name", "llama-3.3-70b-versatile")

    prompt = ITINERARY_PROMPT_TEMPLATE.format(
        query=state["user_query"],
        flight=state.get("flight_results", "Not requested")[:2000],
        hotel=state.get("hotel_results", "Not requested")[:2000],
        weather=state.get("weather_results", "Not requested")[:2000],
    )

    response = _llm_invoke(ITINERARY_SYSTEM_PROMPT, prompt, model)

    draft = response.content
    approval_request = f"""
Please review this draft travel plan.

{draft}

Reply with approval or feedback.
"""

    return {
        "itinerary": draft,
        "approval_request": approval_request,
        "messages": [AIMessage(content="Draft itinerary created for human review.")],
        "llm_calls": 1,
        "agent_times": {"itinerary_agent": round(time.time() - t0, 2)},
    }


def human_approval_agent(state: TravelState):
    feedback = interrupt({
        "question": "Do you approve this itinerary?",
        "draft_itinerary": state.get("itinerary", ""),
        "approval_request": state.get("approval_request", ""),
        "expected_response": {
            "approved": True,
            "feedback": "Optional feedback for revision",
        },
    })

    return {
        "approved": feedback["approved"],
        "human_feedback": feedback.get("feedback", ""),
        "messages": [AIMessage(content="Human approval step completed.")],
    }


def final_response_agent(state: TravelState):
    t0 = time.time()
    model = state.get("model_name", "llama-3.3-70b-versatile")

    if state.get("approved"):
        prompt = f"""
The human approved this draft itinerary.

Produce the final polished travel plan in markdown format.

Draft itinerary:
{state['itinerary']}

Budget notes:
{state.get('budget_results', 'Not available')}

Trip constraints:
{state.get('trip_constraints', {})}
"""
    else:
        prompt = f"""
The human did not approve the draft. Revise based on their feedback.

Original user request:
{state['user_query']}

Draft itinerary:
{state['itinerary']}

Human feedback:
{state.get('human_feedback', 'No feedback provided')}

Budget notes:
{state.get('budget_results', 'Not available')}

Trip constraints:
{state.get('trip_constraints', {})}
"""

    response = _llm_invoke(FINAL_RESPONSE_SYSTEM_PROMPT, prompt, model)

    return {
        "final_response": response.content,
        "messages": [response],
        "llm_calls": 1,
        "agent_times": {"final_response_agent": round(time.time() - t0, 2)},
    }
