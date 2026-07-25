import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv(override=True)

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
AVIATION_STACK_API_KEY = os.getenv("AVIATIONSTACK_API_KEY")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

def get_llm(model_name: str = "llama-3.3-70b-versatile"):
    return ChatGroq(model=model_name)
