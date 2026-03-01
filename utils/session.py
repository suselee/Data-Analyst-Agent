import hashlib
import os
import shutil

import streamlit as st

from config import CHART_DIR_ABS


def _clean_temp_charts():
    """Delete all files in temp_charts/ directory (keep the directory itself)."""
    if os.path.exists(CHART_DIR_ABS):
        shutil.rmtree(CHART_DIR_ABS, ignore_errors=True)


def _compute_config_hash() -> str:
    parts = [
        st.session_state.get("provider", ""),
        st.session_state.get("api_key", ""),
        st.session_state.get("model_id", ""),
        st.session_state.get("base_url", ""),
    ]
    return hashlib.md5("|".join(parts).encode()).hexdigest()


def init_session_state():
    defaults = {
        # LLM config
        "provider": "DeepSeek",
        "api_key": "",
        "model_id": "deepseek-chat",
        "base_url": "",
        # Agent
        "agent": None,
        "agent_config_hash": "",
        # Data
        "dataframes": {},
        "all_sheets": {},
        "uploaded_file_names": set(),
        # Chat
        "messages": [],
        # Charts & process
        "chart_files": [],
        "process_log": [],
        # Report generation
        "report_generating": False,
        "report_request": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    # Clean temp_charts/ once per session to avoid showing stale files
    if "_charts_cleaned" not in st.session_state:
        _clean_temp_charts()
        st.session_state["_charts_cleaned"] = True


def config_changed() -> bool:
    current_hash = _compute_config_hash()
    return current_hash != st.session_state.get("agent_config_hash", "")


def update_config_hash():
    st.session_state["agent_config_hash"] = _compute_config_hash()
