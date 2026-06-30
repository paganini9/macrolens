"""Streamlit 진입점 (Phase 0 스텁). 07 프론트 Agent 가 IA·카드·SSE 소비로 확장."""
import os
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8200")

st.set_page_config(page_title="MacroLens", layout="wide")
st.title("MacroLens — 거시 전이 브리핑")
st.caption(f"backend: {BACKEND_URL} · Phase 0 스텁 (07 Agent 가 구현)")
