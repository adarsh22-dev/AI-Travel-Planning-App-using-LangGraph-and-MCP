import uuid
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from graph import app


def run_cli():
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    user_input = input("Enter travel request: ")

    result = app.invoke(
        {
            "messages": [HumanMessage(content=user_input)],
            "user_query": user_input,
            "model_name": "llama-3.3-70b-versatile",
            "selected_agents": [],
            "trip_constraints": {},
            "supervisor_reasoning": "",
            "flight_results": "",
            "hotel_results": "",
            "weather_results": "",
            "budget_results": "",
            "itinerary": "",
            "approval_request": "",
            "human_feedback": "",
            "approved": False,
            "final_response": "",
            "llm_calls": 0,
            "agent_times": {},
            "active_agents": [],
        },
        config=config,
    )

    print("\n" + "=" * 60)

    if result.get("supervisor_reasoning"):
        print("\nSUPERVISOR PLAN:")
        print(result["supervisor_reasoning"])
        print("Selected:", result.get("selected_agents", []))

    if result.get("flight_results"):
        print("\n--- FLIGHT ---")
        print(result["flight_results"])

    if result.get("hotel_results"):
        print("\n--- HOTEL ---")
        print(result["hotel_results"])

    if result.get("weather_results"):
        print("\n--- WEATHER ---")
        print(result["weather_results"])

    if result.get("budget_results"):
        print("\n--- BUDGET ---")
        print(result["budget_results"])

    if result.get("itinerary"):
        print("\n--- DRAFT ITINERARY ---")
        print(result["itinerary"])

    if "__interrupt__" in result:
        print("\n--- HUMAN APPROVAL REQUIRED ---")
        approved = input("Approve this itinerary? (yes/no): ").strip().lower() == "yes"
        feedback = ""
        if not approved:
            feedback = input("Feedback for revision: ").strip()

        final = app.invoke(
            Command(resume={"approved": approved, "feedback": feedback}),
            config=config,
        )

        if final.get("final_response"):
            print("\n" + "=" * 60)
            print("FINAL TRAVEL PLAN:")
            print(final["final_response"])
    else:
        if result.get("final_response"):
            print("\nFINAL RESPONSE:")
            print(result["final_response"])

    total_time = sum(result.get("agent_times", {}).values())
    print(f"\nLLM calls: {result.get('llm_calls', 0)}")
    print(f"Total time: {total_time:.1f}s")


if __name__ == "__main__":
    run_cli()
