"""Configuration module for AI BI Assistant.

Loads environment variables with robust defaults for local and offline execution.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Base project directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env file if it exists
dotenv_path = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=dotenv_path)

# LLM settings
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "none").strip().lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

# Database & CSV settings
DATABASE_PATH = PROJECT_ROOT / os.getenv("DATABASE_PATH", "data/sales.db")
CSV_DATA_PATH = PROJECT_ROOT / os.getenv("CSV_DATA_PATH", "data/ai_bi_assistant_sales_data.csv")

# API settings
API_HOST = os.getenv("API_HOST", "127.0.0.1").strip()
API_PORT = int(os.getenv("API_PORT", "8000"))
API_BASE_URL = os.getenv("API_BASE_URL", f"http://{API_HOST}:{API_PORT}").strip()
