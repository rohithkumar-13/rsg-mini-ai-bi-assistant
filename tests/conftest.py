"""Pytest fixtures for AI BI Assistant tests.

Provides isolated temporary SQLite databases and synthetic CSV helpers so tests
never modify or depend on the development/production database.
"""
import os
import tempfile
from pathlib import Path
from typing import Generator
import pytest

from app.config import CSV_DATA_PATH
from app.loader import load_csv_data


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Provide a path to a temporary database file."""
    return tmp_path / "test_sales.db"


@pytest.fixture
def loaded_temp_db(temp_db_path: Path) -> Path:
    """Provide a temporary database populated with the official sales dataset."""
    load_csv_data(csv_path=CSV_DATA_PATH, db_path=temp_db_path)
    return temp_db_path
