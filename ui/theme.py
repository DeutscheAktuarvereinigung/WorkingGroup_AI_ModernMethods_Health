import base64
from pathlib import Path

import streamlit as st

# DAV-Farbpalette
DAV_BLAU_DUNKEL = "#003056"
DAV_BLAU_AKZENT = "#0078C8"
DAV_GRUEN = "#78BE20"
DAV_ORANGE = "#E87722"
DAV_GRAU_DUNKEL = "#3C3C3C"
DAV_GRAU_HELL = "#F0F2F5"

PALETTE_GROSS = [
    "#0078C8",
    "#E87722",
    "#78BE20",
    "#003056",
    "#5CB8E6",
    "#F5A623",
    "#4A9E2F",
    "#8B572A",
    "#7B61A1",
    "#2AABB3",
    "#D0021B",
    "#3C7A3C",
    "#B8860B",
    "#4A90D9",
    "#C85000",
    "#5A7184",
    "#9B9B9B",
    "#006B54",
    "#8E44AD",
    "#2C3E50",
]

PLOTLY_LAYOUT = dict(
    font=dict(family="Source Sans 3, Source Sans Pro, Calibri, sans-serif", size=13, color=DAV_GRAU_DUNKEL),
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=40, r=20, t=50, b=40),
    hoverlabel=dict(bgcolor="white", font_size=12, bordercolor=DAV_BLAU_AKZENT),
    title_font=dict(color=DAV_BLAU_DUNKEL, size=15),
)


def lade_svg_als_data_uri(pfad: str) -> str:
    try:
        svg_bytes = Path(pfad).read_bytes()
        svg_b64 = base64.b64encode(svg_bytes).decode("ascii")
        return f"data:image/svg+xml;base64,{svg_b64}"
    except Exception:
        return "https://aktuar.de/_assets/87d17a42edc6aa4486ad37cc027da99c/Images/Design/logo.svg"


def get_logo_src(pfad: str = "dav_logo.svg") -> str:
    return lade_svg_als_data_uri(pfad)


def apply_theme() -> None:
    st.markdown(
        """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@300;400;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Source Sans 3', 'Source Sans Pro', Calibri, sans-serif !important;
    }

    :root {
        --primary-color: #0078C8 !important;
    }

    div[data-testid="stMetric"] {
        background: #FFFFFF;
        border-left: 4px solid #0078C8;
        border-top: none; border-right: 1px solid #E8ECF0; border-bottom: 1px solid #E8ECF0;
        border-radius: 4px;
        padding: 14px 16px;
        box-shadow: 0 1px 4px rgba(0,48,86,0.06);
    }
    div[data-testid="stMetric"] label {
        font-size: 0.72rem !important; color: #5A7184 !important;
        font-weight: 600 !important; text-transform: uppercase; letter-spacing: 0.8px;
        font-family: 'Source Sans 3', sans-serif !important;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        font-size: 1.45rem !important; font-weight: 700 !important; color: #003056 !important;
        font-family: 'Source Sans 3', sans-serif !important;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 0px;
        border-bottom: 2px solid #E8ECF0;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 24px; font-weight: 600; color: #5A7184;
        border-bottom: 3px solid transparent;
        font-family: 'Source Sans 3', sans-serif;
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        color: #003056 !important;
        border-bottom: 3px solid #0078C8 !important;
    }

    section[data-testid="stSidebar"] {
        background: #F0F2F5;
        border-right: 1px solid #E8ECF0;
    }
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2 {
        color: #003056 !important;
        font-family: 'Source Sans 3', sans-serif !important;
    }

    button[kind="primary"],
    button[kind="primaryFormSubmit"],
    .stButton > button[kind="primary"],
    .stFormSubmitButton > button,
    .stButton > button:focus,
    div[data-testid="stForm"] button[type="submit"],
    div[data-testid="stForm"] button {
        background-color: #0078C8 !important;
        color: white !important;
        border: none !important;
        border-color: #0078C8 !important;
        border-radius: 4px !important;
        font-weight: 600 !important;
        font-family: 'Source Sans 3', sans-serif !important;
    }
    button[kind="primary"]:hover,
    button[kind="primaryFormSubmit"]:hover,
    .stButton > button[kind="primary"]:hover,
    .stFormSubmitButton > button:hover,
    div[data-testid="stForm"] button:hover {
        background-color: #005FA0 !important;
        border-color: #005FA0 !important;
    }

    .stButton > button:not([kind="primary"]) {
        color: #003056 !important;
        border: 1px solid #0078C8 !important;
        font-family: 'Source Sans 3', sans-serif !important;
        font-weight: 600 !important;
    }

    .stDownloadButton > button {
        background-color: #FFFFFF !important;
        color: #003056 !important;
        border: 1px solid #0078C8 !important;
        border-radius: 4px !important;
        font-weight: 600 !important;
    }

    div[data-testid="stSlider"] [role="slider"] {
        background-color: #0078C8 !important;
    }

    span[data-baseweb="tag"] {
        background-color: #0078C8 !important;
        color: white !important;
        border-color: #0078C8 !important;
    }

    a {
        color: #0078C8 !important;
    }

    h1, h2, h3, h4 {
        color: #003056 !important;
        font-family: 'Source Sans 3', sans-serif !important;
    }

    div[data-testid="stAlert"] {
        border-left-color: #0078C8 !important;
    }

    hr {
        border-color: #E8ECF0 !important;
    }
</style>
""",
        unsafe_allow_html=True,
    )
