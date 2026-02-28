import streamlit as st

from utils.session import init_session_state
from ui.sidebar import render_sidebar
from ui.main_area import render_main_area

st.set_page_config(
    page_title="数据分析 Agent",
    page_icon="📊",
    layout="wide",
)

init_session_state()
render_sidebar()
render_main_area()
