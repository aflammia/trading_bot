"""
Chuky Bot - Professional Financial Theme.

Design system inspired by Bloomberg Terminal, TradingView, Interactive Brokers.
Dark mode with financial color conventions:
  - Green (#00C853): Gains / Long / Positive
  - Red (#EF5350): Losses / Short / Negative
  - Blue (#42A5F5): Neutral / Info
  - Gold (#FFD54F): Warnings / Highlights
  - White (#E0E0E0): Primary text
  - Gray (#9E9E9E): Secondary text

Typography: Inter (sans-serif), monospace for numbers.
Icons: Lucide Icons via CDN.
"""

# =============================================================================
# Brand & Color Palette
# =============================================================================
# -- Backgrounds --
BG_PRIMARY    = "#0D1117"
BG_SECONDARY  = "#161B22"
BG_TERTIARY   = "#1C2333"
BG_HEADER     = "#0D1117"
BORDER_COLOR  = "#30363D"

# -- Text --
TEXT_PRIMARY   = "#E6EDF3"
TEXT_SECONDARY = "#8B949E"
TEXT_MUTED     = "#6E7681"

# -- Financial Colors --
LONG_GREEN    = "#00C853"
SHORT_RED     = "#EF5350"
NEUTRAL_BLUE  = "#42A5F5"
ACCENT_GOLD   = "#FFD54F"
ACCENT_CYAN   = "#26C6DA"

# -- Brand --
BRAND_PRIMARY  = "#58A6FF"
BRAND_DARK     = "#1F6FEB"

# -- Status --
SUCCESS = LONG_GREEN
DANGER  = SHORT_RED
WARNING = ACCENT_GOLD
INFO    = NEUTRAL_BLUE

# Legacy aliases for backward compatibility
PURPLE       = BRAND_PRIMARY
PURPLE_DARK  = BRAND_DARK
PURPLE_LIGHT = "#A5D6FF"
NEON_GREEN   = LONG_GREEN
HOT_PINK     = SHORT_RED
ELECTRIC     = NEUTRAL_BLUE
DARK_BG      = BG_PRIMARY
CARD_BG      = BG_SECONDARY
HEADER_BG    = BG_HEADER
WHITE        = TEXT_PRIMARY
MID_GRAY     = TEXT_SECONDARY
VIOLET       = BRAND_PRIMARY

# =============================================================================
# Icon Map (text labels replacing emojis)
# =============================================================================
ICONS = {
    "overview":     "bar-chart-2",
    "backtest":     "flask-conical",
    "chart":        "candlestick-chart",
    "trades":       "list-ordered",
    "risk":         "shield-alert",
    "validation":   "check-circle-2",
    "config":       "settings-2",
    "ai":           "brain-circuit",
    "reports":      "file-text",
    "save":         "save",
    "download":     "download",
    "upload":       "upload",
    "run":          "play",
    "stop":         "square",
    "warning":      "alert-triangle",
    "success":      "check-circle",
    "error":        "x-circle",
    "info":         "info",
    "calendar":     "calendar",
    "clock":        "clock",
    "dollar":       "dollar-sign",
    "trending_up":  "trending-up",
    "trending_down": "trending-down",
    "activity":     "activity",
    "target":       "crosshair",
    "database":     "database",
    "refresh":      "refresh-cw",
    "filter":       "filter",
    "search":       "search",
    "expand":       "maximize-2",
    "layers":       "layers",
    "zap":          "zap",
}


# =============================================================================
# CSS - Professional Financial Dark Theme
# Bloomberg / TradingView / QuantConnect inspired.
# 8px grid spacing system throughout.
# =============================================================================
CUSTOM_CSS = '''
<style>
    /* ── Fonts ─────────────────────────────────────────────── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    /* ── Base ──────────────────────────────────────────────── */
    .stApp {
        background-color: #0D1117;
        color: #E6EDF3;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }
    .stApp p, .stApp li, .stApp label,
    .stApp .stMarkdown, .stApp .stText {
        color: #E6EDF3 !important;
        font-family: 'Inter', sans-serif;
    }

    /* ── Sidebar — ALL text pure white ─────────────────────── */
    section[data-testid="stSidebar"] {
        background-color: #0D1117;
        border-right: 1px solid #30363D;
    }
    section[data-testid="stSidebar"] .stMarkdown h1 {
        color: #58A6FF !important;
        text-align: center;
        font-weight: 700;
        letter-spacing: -0.5px;
        font-size: 1.4rem;
    }
    section[data-testid="stSidebar"] * {
        color: #FFFFFF !important;
    }
    section[data-testid="stSidebar"] .stMarkdown h1 {
        color: #58A6FF !important;
    }
    section[data-testid="stSidebar"] a {
        color: #FFFFFF !important;
        transition: color 0.2s ease;
    }
    section[data-testid="stSidebar"] a:hover {
        color: #58A6FF !important;
    }
    section[data-testid="stSidebar"] a[aria-selected="true"],
    section[data-testid="stSidebar"] a[aria-selected="true"] span {
        color: #58A6FF !important;
        font-weight: 600;
    }
    [data-testid="stSidebarNav"] a span {
        color: #FFFFFF !important;
        font-size: 0.9rem;
    }
    [data-testid="stSidebarNav"] a[aria-selected="true"] span {
        color: #58A6FF !important;
    }
    /* Sidebar captions / small text */
    section[data-testid="stSidebar"] .stCaption,
    section[data-testid="stSidebar"] small {
        color: rgba(255,255,255,0.7) !important;
    }

    /* ── Metric Cards ─────────────────────────────────────── */
    div[data-testid="stMetric"] {
        background-color: #161B22;
        border: 1px solid #30363D;
        border-radius: 8px;
        padding: 16px 20px;
    }
    div[data-testid="stMetric"] label {
        color: #8B949E !important;
        font-size: 12px;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #E6EDF3 !important;
        font-weight: 700;
        font-size: 20px;
        font-family: 'JetBrains Mono', monospace;
    }
    div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
        font-family: 'JetBrains Mono', monospace;
        font-size: 12px;
    }

    /* ── Typography ───────────────────────────────────────── */
    h1, h2, h3, h4, h5, h6 {
        color: #E6EDF3 !important;
        font-family: 'Inter', sans-serif;
        font-weight: 600;
        letter-spacing: -0.3px;
    }
    h1 {
        border-bottom: 2px solid #30363D;
        padding-bottom: 12px;
        margin-bottom: 24px;
        font-size: 1.5rem;
    }
    h2 { font-size: 1.2rem; margin-top: 8px; }
    h3 { font-size: 1.05rem; color: #8B949E !important; }

    /* ── Tabs — more breathing room ───────────────────────── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        background-color: #161B22;
        border-radius: 8px;
        padding: 6px;
        border: 1px solid #30363D;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: transparent;
        border-radius: 6px;
        color: #8B949E !important;
        border: none;
        font-weight: 500;
        font-size: 0.85rem;
        padding: 8px 16px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1C2333 !important;
        color: #E6EDF3 !important;
        border: 1px solid #30363D;
    }
    .stTabs [data-baseweb="tab-panel"] {
        padding-top: 16px;
    }

    /* ── Data Tables ──────────────────────────────────────── */
    .stDataFrame {
        border: 1px solid #30363D;
        border-radius: 8px;
    }
    thead th {
        color: #8B949E !important;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        font-weight: 600;
    }

    /* ===========================================================
       BUG FIX #1: ALL form input labels clearly visible
       Force labels on ALL widget types to be light text.
       Targets both legacy class selectors and modern data-testid.
       =========================================================== */
    /* Legacy class-based selectors */
    .stTextInput label, .stSelectbox label, .stMultiSelect label,
    .stNumberInput label, .stDateInput label, .stRadio label,
    .stCheckbox label, .stSlider label, .stFileUploader label,
    .stTextArea label, .stColorPicker label, .stTimeInput label {
        color: #E6EDF3 !important;
        font-size: 13px;
        font-weight: 500;
    }

    /* Modern Streamlit widget label selector */
    [data-testid="stWidgetLabel"],
    [data-testid="stWidgetLabel"] p,
    [data-testid="stWidgetLabel"] label,
    [data-testid="stWidgetLabel"] span {
        color: #E6EDF3 !important;
        font-size: 13px;
        font-weight: 500;
    }

    /* Labels inside expanders (the bug context) */
    [data-testid="stExpander"] label,
    [data-testid="stExpander"] [data-testid="stWidgetLabel"],
    [data-testid="stExpander"] [data-testid="stWidgetLabel"] p,
    [data-testid="stExpander"] .stSelectbox label,
    [data-testid="stExpander"] .stMultiSelect label,
    [data-testid="stExpander"] .stNumberInput label,
    [data-testid="stExpander"] .stDateInput label,
    [data-testid="stExpander"] .stSlider label {
        color: #E6EDF3 !important;
    }

    /* Caption text under labels  */
    .stApp [data-testid="stMarkdownContainer"] p {
        color: #E6EDF3 !important;
    }
    .stCaption, .stApp small {
        color: #8B949E !important;
    }

    /* ── Form Inputs ─────────────────────────────────────── */
    .stTextInput input, .stNumberInput input {
        color: #E6EDF3 !important;
        background-color: #161B22 !important;
        border: 1px solid #30363D !important;
        border-radius: 6px;
        font-family: 'JetBrains Mono', monospace;
    }
    .stTextInput input:focus, .stNumberInput input:focus {
        border-color: #58A6FF !important;
        box-shadow: 0 0 0 1px #58A6FF !important;
    }
    .stChatInput textarea, .stChatInput input,
    [data-testid="stChatInput"] textarea {
        color: #E6EDF3 !important;
        background-color: #161B22 !important;
        border: 1px solid #30363D !important;
    }
    .stDateInput input {
        color: #E6EDF3 !important;
        background-color: #161B22 !important;
        border: 1px solid #30363D !important;
    }

    /* ── Selectbox / Dropdown ────────────────────────────── */
    .stApp [data-baseweb="select"] {
        background-color: #161B22 !important;
    }
    .stApp [data-baseweb="select"] > div,
    .stApp [data-baseweb="select"] > div > div {
        background-color: #161B22 !important;
        color: #E6EDF3 !important;
        border-color: #30363D !important;
    }
    .stApp [data-baseweb="select"] span,
    .stApp [data-baseweb="select"] div {
        color: #E6EDF3 !important;
    }
    .stApp [data-baseweb="select"] input {
        color: #E6EDF3 !important;
    }
    .stApp [data-baseweb="select"] svg {
        fill: #8B949E !important;
    }
    /* Dropdown popover menu */
    .stApp [data-baseweb="popover"] {
        background-color: #161B22 !important;
        border: 1px solid #30363D !important;
        border-radius: 8px;
    }
    .stApp [data-baseweb="popover"] li,
    .stApp [data-baseweb="popover"] div,
    .stApp [data-baseweb="popover"] span {
        color: #E6EDF3 !important;
        background-color: #161B22 !important;
    }
    .stApp [data-baseweb="popover"] li:hover,
    .stApp [data-baseweb="popover"] li:hover div,
    .stApp [data-baseweb="popover"] li:hover span {
        background-color: #1C2333 !important;
    }
    .stApp [data-baseweb="menu"] {
        background-color: #161B22 !important;
    }
    .stApp [data-baseweb="menu"] li,
    .stApp [data-baseweb="menu"] div,
    .stApp [data-baseweb="menu"] span {
        color: #E6EDF3 !important;
    }
    .stApp [data-baseweb="menu"] li:hover {
        background-color: #1C2333 !important;
    }
    .stApp [data-baseweb="listbox"] {
        background-color: #161B22 !important;
    }
    .stApp [data-baseweb="listbox"] li,
    .stApp [data-baseweb="listbox"] span {
        color: #E6EDF3 !important;
    }
    .stApp [data-baseweb="listbox"] li:hover {
        background-color: #1C2333 !important;
    }
    .stApp [data-baseweb="tag"] {
        background-color: #1F6FEB !important;
        color: #FFFFFF !important;
    }
    .stApp [data-baseweb="tag"] span {
        color: #FFFFFF !important;
    }
    .stNumberInput div[data-baseweb="input"] {
        background-color: #161B22 !important;
        border-color: #30363D !important;
    }
    .stNumberInput div[data-baseweb="input"] input {
        color: #E6EDF3 !important;
    }
    .stSlider [data-testid="stThumbValue"] {
        color: #E6EDF3 !important;
        font-family: 'JetBrains Mono', monospace;
    }

    /* ── Code & JSON ─────────────────────────────────────── */
    [data-testid="stJson"], .stJson {
        background-color: #161B22 !important;
        border: 1px solid #30363D;
        border-radius: 8px;
    }
    [data-testid="stJson"] *, .stJson * {
        color: #00C853 !important;
        background-color: transparent !important;
        font-family: 'JetBrains Mono', monospace;
    }
    .stApp pre {
        background-color: #161B22 !important;
        color: #E6EDF3 !important;
        border: 1px solid #30363D;
        border-radius: 8px;
        font-family: 'JetBrains Mono', monospace;
    }
    .stApp code {
        color: #58A6FF !important;
        font-family: 'JetBrains Mono', monospace;
    }

    /* ── Expanders — Card-styled ──────────────────────────── */
    [data-testid="stExpander"] {
        background-color: #161B22;
        border: 1px solid #30363D;
        border-radius: 8px;
        margin-bottom: 16px;
    }
    [data-testid="stExpander"] details {
        border: none;
    }
    .streamlit-expanderHeader,
    [data-testid="stExpander"] summary {
        color: #E6EDF3 !important;
        font-weight: 600;
        font-size: 0.9rem;
        padding: 12px 16px;
    }
    [data-testid="stExpander"] summary span {
        color: #E6EDF3 !important;
    }
    [data-testid="stExpander"] [data-testid="stExpanderDetails"] {
        padding: 0 16px 16px 16px;
    }

    /* ── Buttons — proper spacing ─────────────────────────── */
    .stButton > button {
        background-color: #1F6FEB;
        color: white !important;
        border: none;
        border-radius: 6px;
        font-weight: 600;
        font-family: 'Inter', sans-serif;
        font-size: 0.85rem;
        padding: 10px 24px;
        min-height: 40px;
        transition: all 0.2s ease;
    }
    .stButton > button:hover {
        background-color: #58A6FF;
        color: white !important;
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(88,166,255,0.25);
    }
    .stButton > button:active {
        transform: translateY(0);
    }
    /* Secondary / download button */
    .stDownloadButton > button {
        color: #E6EDF3 !important;
        background-color: #161B22;
        border: 1px solid #30363D;
        padding: 10px 24px;
        min-height: 40px;
    }
    .stDownloadButton > button:hover {
        background-color: #1C2333;
        border-color: #58A6FF;
        color: #58A6FF !important;
    }
    /* Add spacing between buttons in a row */
    .stButton, .stDownloadButton {
        margin-bottom: 8px;
    }

    /* ===========================================================
       CARD SYSTEM — bordered containers for every section
       Apply via st.markdown wrapping or target native containers.
       =========================================================== */
    /* Manual card class */
    .chuky-card {
        background-color: #161B22;
        border: 1px solid #30363D;
        border-radius: 8px;
        padding: 20px;
        margin-bottom: 16px;
        border-left: 3px solid #58A6FF;
        box-shadow: 0 1px 3px rgba(0,0,0,0.3);
    }
    .chuky-card h4 {
        color: #E6EDF3 !important;
        margin-top: 0;
        font-weight: 600;
        font-size: 14px;
    }
    .chuky-card p { color: #8B949E !important; margin-bottom: 4px; }

    /* Section card — no left accent */
    .chuky-section {
        background-color: #161B22;
        border: 1px solid #30363D;
        border-radius: 8px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.3);
    }

    /* Auto-card: wrap Plotly charts in a card */
    [data-testid="stPlotlyChart"] {
        background-color: #161B22;
        border: 1px solid #30363D;
        border-radius: 8px;
        padding: 8px;
        margin-bottom: 16px;
    }

    /* Auto-card: wrap dataframes */
    [data-testid="stDataFrame"],
    .stDataFrame {
        background-color: #161B22;
        border: 1px solid #30363D;
        border-radius: 8px;
        padding: 4px;
        margin-bottom: 16px;
    }

    /* Auto-card: wrap metric rows — target the column container holding metrics */
    div[data-testid="stHorizontalBlock"]:has(div[data-testid="stMetric"]) {
        background-color: #161B22;
        border: 1px solid #30363D;
        border-radius: 8px;
        padding: 16px 12px;
        margin-bottom: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.3);
    }
    /* Prevent double-nesting bg on inner metrics when wrapped */
    div[data-testid="stHorizontalBlock"]:has(div[data-testid="stMetric"])
    div[data-testid="stMetric"] {
        border: none;
        box-shadow: none;
        background-color: transparent;
    }

    /* ── Badges ──────────────────────────────────────────── */
    .badge-go    { background:#00C853; color:white; padding:4px 12px; border-radius:4px; font-weight:700; font-size:12px; }
    .badge-nogo  { background:#EF5350; color:white; padding:4px 12px; border-radius:4px; font-weight:700; font-size:12px; }
    .badge-warn  { background:#FFB300; color:#0D1117; padding:4px 12px; border-radius:4px; font-weight:700; font-size:12px; }

    /* ── Chat ─────────────────────────────────────────────── */
    .stChatMessage {
        background-color: #161B22 !important;
        border: 1px solid #30363D;
        border-radius: 8px;
        margin-bottom: 8px;
    }
    .stChatMessage p, .stChatMessage span { color: #E6EDF3 !important; }

    /* ── Miscellaneous ────────────────────────────────────── */
    [data-testid="stTooltipIcon"] { color: #8B949E !important; }
    .js-plotly-plot .plotly text { fill: #E6EDF3 !important; }

    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: #0D1117; }
    ::-webkit-scrollbar-thumb { background: #30363D; border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: #484F58; }

    .stAlert {
        border-radius: 8px;
        border: 1px solid #30363D;
        margin-bottom: 16px;
    }
    hr {
        border-color: #30363D !important;
        margin: 24px 0 !important;
    }

    /* ── Column gaps for button spacing (BUG #2 fix) ────── */
    [data-testid="stHorizontalBlock"] > div {
        padding-right: 8px;
    }
    [data-testid="stHorizontalBlock"] > div:last-child {
        padding-right: 0;
    }

    /* ── File uploader ───────────────────────────────────── */
    [data-testid="stFileUploader"] {
        background-color: #161B22;
        border: 1px dashed #30363D;
        border-radius: 8px;
        padding: 16px;
    }
    [data-testid="stFileUploader"] label,
    [data-testid="stFileUploader"] span,
    [data-testid="stFileUploader"] p {
        color: #E6EDF3 !important;
    }

    /* ── Date picker calendar popup ──────────────────────── */
    /* The entire datepicker container and popover */
    [data-baseweb="datepicker"],
    [data-baseweb="datepicker"] > div,
    [data-baseweb="calendar"] {
        background-color: #161B22 !important;
    }
    /* Popover that wraps the calendar */
    [data-baseweb="popover"] [data-baseweb="datepicker"],
    [data-baseweb="popover"] [data-baseweb="calendar"],
    [data-baseweb="popover"] [data-baseweb="datepicker"] > div {
        background-color: #161B22 !important;
    }
    /* Month/year header row (navigation) */
    [data-baseweb="calendar"] [data-baseweb="calendar-header"],
    [data-baseweb="datepicker"] [data-baseweb="calendar-header"],
    [data-baseweb="calendar"] header,
    [data-baseweb="datepicker"] header {
        background-color: #161B22 !important;
    }
    /* Navigation arrows */
    [data-baseweb="calendar"] button,
    [data-baseweb="datepicker"] button {
        color: #E6EDF3 !important;
        background-color: transparent !important;
    }
    [data-baseweb="calendar"] button:hover,
    [data-baseweb="datepicker"] button:hover {
        background-color: #1C2333 !important;
    }
    /* All text inside calendar: month name, year, day-of-week abbreviations, day numbers */
    [data-baseweb="calendar"] *,
    [data-baseweb="datepicker"] * {
        color: #E6EDF3 !important;
        background-color: transparent !important;
    }
    /* Re-apply the container background since * transparent override */
    [data-baseweb="datepicker"],
    [data-baseweb="calendar"] {
        background-color: #161B22 !important;
    }
    /* Month/year grid wrapper */
    [data-baseweb="datepicker"] > div,
    [data-baseweb="datepicker"] > div > div,
    [data-baseweb="datepicker"] > div > div > div {
        background-color: #161B22 !important;
    }
    /* Day cells — default state */
    [data-baseweb="calendar"] td,
    [data-baseweb="calendar"] td > div {
        background-color: transparent !important;
        color: #E6EDF3 !important;
    }
    /* Day cells — hover */
    [data-baseweb="calendar"] td:hover,
    [data-baseweb="calendar"] td:hover > div {
        background-color: #1C2333 !important;
        border-radius: 6px;
    }
    /* Day cells — selected */
    [data-baseweb="calendar"] [aria-selected="true"],
    [data-baseweb="calendar"] [aria-selected="true"] > div {
        background-color: #1F6FEB !important;
        color: #FFFFFF !important;
        border-radius: 6px;
    }
    /* Day of week header row (Mo Tu We Th Fr Sa Su) */
    [data-baseweb="calendar"] th,
    [data-baseweb="calendar"] thead {
        color: #8B949E !important;
        background-color: #161B22 !important;
    }
    /* Month/Year quick-select dropdowns inside calendar */
    [data-baseweb="calendar"] select,
    [data-baseweb="datepicker"] select {
        background-color: #161B22 !important;
        color: #E6EDF3 !important;
        border: 1px solid #30363D !important;
    }
    /* Range highlight (if date range is used) */
    [data-baseweb="calendar"] [data-highlighted="true"],
    [data-baseweb="calendar"] [data-highlighted="true"] > div {
        background-color: rgba(31,111,235,0.25) !important;
    }

    /* ── GLOBAL: Force dark bg on ALL BaseWeb overlays / popovers ── */
    [data-baseweb="popover"] > div,
    [data-baseweb="popover"] > div > div {
        background-color: #161B22 !important;
        border: 1px solid #30363D !important;
        border-radius: 8px;
    }

    /* ── Multiselect dropdown body ────────────────────────── */
    [data-baseweb="popover"] ul,
    [data-baseweb="popover"] ul li {
        background-color: #161B22 !important;
        color: #E6EDF3 !important;
    }
    [data-baseweb="popover"] ul li:hover {
        background-color: #1C2333 !important;
    }

    /* ── Toast / notifications ───────────────────────────── */
    [data-baseweb="toast"],
    [data-baseweb="notification"] {
        background-color: #161B22 !important;
        color: #E6EDF3 !important;
        border: 1px solid #30363D !important;
    }

    /* ── Tooltip ─────────────────────────────────────────── */
    [data-baseweb="tooltip"],
    [data-baseweb="tooltip"] > div {
        background-color: #1C2333 !important;
        color: #E6EDF3 !important;
        border: 1px solid #30363D !important;
    }

    /* ── Dialog / Modal ──────────────────────────────────── */
    [data-baseweb="modal"] > div,
    [data-baseweb="dialog"] > div {
        background-color: #161B22 !important;
        color: #E6EDF3 !important;
    }

    /* ── Ensure no white bleeds from Streamlit containers ── */
    .stApp > header,
    .main .block-container {
        background-color: transparent !important;
    }
    [data-testid="stAppViewContainer"] {
        background-color: #0D1117 !important;
    }
    [data-testid="stHeader"] {
        background-color: rgba(13,17,23,0.95) !important;
    }
    [data-testid="stToolbar"] {
        background-color: transparent !important;
    }
    [data-testid="stBottomBlockContainer"] {
        background-color: #0D1117 !important;
    }
    /* Streamlit iframe / embedded elements */
    iframe {
        background-color: #0D1117 !important;
    }
</style>
'''


def inject_css():
    """Inject the professional financial theme CSS into the Streamlit app."""
    import streamlit as st
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# =============================================================================
# Plotly Layout Template - Financial Dark Theme
# =============================================================================
PLOTLY_LAYOUT = dict(
    paper_bgcolor="#0D1117",
    plot_bgcolor="#161B22",
    font=dict(
        color="#E6EDF3",
        family="Inter, -apple-system, BlinkMacSystemFont, sans-serif",
        size=12,
    ),
    xaxis=dict(
        gridcolor="#1C2333",
        zerolinecolor="#30363D",
        tickfont=dict(color="#8B949E", family="JetBrains Mono, monospace", size=10),
        linecolor="#30363D",
    ),
    yaxis=dict(
        gridcolor="#1C2333",
        zerolinecolor="#30363D",
        tickfont=dict(color="#8B949E", family="JetBrains Mono, monospace", size=10),
        linecolor="#30363D",
    ),
    legend=dict(
        bgcolor="rgba(22,27,34,0.95)",
        bordercolor="#30363D",
        font=dict(color="#E6EDF3", size=11),
    ),
    hoverlabel=dict(
        bgcolor="#1C2333",
        font_color="#E6EDF3",
        font_size=12,
        font_family="JetBrains Mono, monospace",
        bordercolor="#30363D",
    ),
    margin=dict(l=50, r=20, t=40, b=40),
    colorway=["#58A6FF", "#00C853", "#EF5350", "#FFD54F", "#26C6DA", "#AB47BC"],
)


def apply_plotly_theme(fig):
    """Apply the professional financial theme to a Plotly figure."""
    fig.update_layout(**PLOTLY_LAYOUT)
    return fig


def fmt_currency(value, prefix="$"):
    """Format number as financial currency."""
    if value >= 0:
        return f"{prefix}{value:,.2f}"
    return f"-{prefix}{abs(value):,.2f}"


def fmt_pct(value):
    """Format as percentage."""
    return f"{value:+.1f}%"


def fmt_pnl_color(value):
    """Return HTML-colored P&L string."""
    color = LONG_GREEN if value >= 0 else SHORT_RED
    return f"<span style='color:{color}; font-family:JetBrains Mono,monospace; font-weight:600'>{fmt_currency(value)}</span>"
