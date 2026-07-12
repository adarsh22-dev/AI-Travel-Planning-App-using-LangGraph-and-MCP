import os, json, io
import streamlit as st
import folium
from streamlit_folium import st_folium
from datetime import datetime, timedelta
from langchain_core.messages import HumanMessage
from fpdf import FPDF
from main import app

st.set_page_config(page_title="AI Travel Planner", page_icon=":airplane:", layout="wide")

CACHE_DIR = os.path.join(os.path.dirname(__file__), ".travel_cache")
AUTOSAVE_FILE = os.path.join(CACHE_DIR, "autosave.json")

def autosave(data):
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        with open(AUTOSAVE_FILE, "w", encoding="utf-8") as f:
            json.dump({k:v for k,v in data.items() if not k.startswith("_")}, f, indent=2, default=str)
    except: pass

if "history" not in st.session_state: st.session_state.history = []
if "trip_history" not in st.session_state: st.session_state.trip_history = {}
if "theme_color" not in st.session_state: st.session_state.theme_color = "#22D3EE"
if "form_data" not in st.session_state: st.session_state.form_data = {}
if "wizard_step" not in st.session_state: st.session_state.wizard_step = 1
if "last_result" not in st.session_state: st.session_state.last_result = None
if "viewing_history" not in st.session_state: st.session_state.viewing_history = None

# ── Load autosave on first run ──
if "autosave_loaded" not in st.session_state:
    st.session_state.autosave_loaded = True
    try:
        if os.path.exists(AUTOSAVE_FILE):
            with open(AUTOSAVE_FILE, encoding="utf-8") as f:
                saved = json.load(f)
            if saved:
                st.session_state.form_data.update(saved)
    except: pass

CITIES = [
    "Mumbai (BOM)","Delhi (DEL)","Bangalore (BLR)","Chennai (MAA)",
    "Kolkata (CCU)","Hyderabad (HYD)","New York (JFK)","London (LHR)",
    "Dubai (DXB)","Singapore (SIN)","Bangkok (BKK)","Paris (CDG)",
    "Tokyo (NRT)","Rome (FCO)","Bali (DPS)","Sydney (SYD)",
]

CITY_COORDS = {
    "Mumbai (BOM)": [19.0760, 72.8777], "Delhi (DEL)": [28.6139, 77.2090],
    "Bangalore (BLR)": [12.9716, 77.5946], "Chennai (MAA)": [13.0827, 80.2707],
    "Kolkata (CCU)": [22.5726, 88.3639], "Hyderabad (HYD)": [17.3850, 78.4867],
    "New York (JFK)": [40.7128, -74.0060], "London (LHR)": [51.5074, -0.1278],
    "Dubai (DXB)": [25.2048, 55.2708], "Singapore (SIN)": [1.3521, 103.8198],
    "Bangkok (BKK)": [13.7563, 100.5018], "Paris (CDG)": [48.8566, 2.3522],
    "Tokyo (NRT)": [35.6762, 139.6503], "Rome (FCO)": [41.9028, 12.4964],
    "Bali (DPS)": [-8.3405, 115.0920], "Sydney (SYD)": [-33.8688, 151.2093],
}

THEME = st.session_state.theme_color

def markdown_to_pdf(title: str, body: str) -> bytes:
    try:
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_title(title[:128])
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, title[:128].encode("latin-1","replace").decode("latin-1"), ln=2)
        pdf.ln(3)
        pdf.set_font("Helvetica", "", 8)
        for line in (body or "").split("\n"):
            clean = line.strip()
            if not clean:
                pdf.ln(2)
            elif clean.startswith("###") or clean.startswith("##"):
                pdf.set_font("Helvetica", "B", 10)
                pdf.cell(0, 6, clean.lstrip("#").strip()[:120].encode("latin-1","replace").decode("latin-1"), ln=2)
                pdf.set_font("Helvetica", "", 8)
                pdf.ln(1)
            elif clean.startswith("**") and clean.endswith("**"):
                pdf.set_font("Helvetica", "B", 9)
                pdf.cell(0, 5, clean.strip("*")[:120].encode("latin-1","replace").decode("latin-1"), ln=2)
                pdf.set_font("Helvetica", "", 8)
            else:
                txt = clean.replace("**","").replace("*","").replace("`","").replace("_","")
                txt = txt[:200].encode("latin-1","replace").decode("latin-1")
                if len(txt) > 90:
                    pdf.multi_cell(0, 4, txt)
                else:
                    pdf.cell(0, 4.5, txt, ln=2)
        return bytes(pdf.output())
    except Exception:
        return b""

def darken(h, a=0.3):
    r, g, b = int(h[1:3],16), int(h[3:5],16), int(h[5:7],16)
    return f"#{max(0,int(r*(1-a))):02x}{max(0,int(g*(1-a))):02x}{max(0,int(b*(1-a))):02x}"
def lighten(h, a=0.3):
    r, g, b = int(h[1:3],16), int(h[3:5],16), int(h[5:7],16)
    return f"#{min(255,int(r+(255-r)*a)):02x}{min(255,int(g+(255-g)*a)):02x}{min(255,int(b+(255-b)*a)):02x}"

S = {
"plane":'<path d="M22 2L11 13"/><path d="M22 2L15 22L11 13L2 9L22 2Z"/>',
"brain":('<path d="M12 4a4 4 0 0 1 4 4c0 1.5-.8 2.8-2 3.5V14a2 2 0 0 1-2 2h0a2 2 0 0 1-2-2v-2.5'
 'c-1.2-.7-2-2-2-3.5a4 4 0 0 1 4-4Z"/><path d="M9 15v3a3 3 0 0 0 6 0v-3"/>'
 '<path d="M4.56 8.2a6 6 0 0 0 1.44 9.3"/><path d="M19.44 8.2a6 6 0 0 1-1.44 9.3"/>'),
"globe":'<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20Z"/>',
"hotel":('<path d="M3 21V7l9-4 9 4v14"/><path d="M7 21v-4h10v4"/>'
 '<path d="M9 9h1"/><path d="M14 9h1"/><path d="M9 13h1"/><path d="M14 13h1"/><path d="M9 17h6"/>'),
"calendar":('<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>'
 '<line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>'),
"link":('<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>'
 '<path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>'),
"database":('<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>'
 '<path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>'),
"search":'<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
"rocket":('<path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09Z"/>'
 '<path d="M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2Z"/>'
 '<path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/>'),
"user":'<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
"check":'<polyline points="20 6 9 17 4 12"/>',
"folder":'<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2Z"/>',
"download":('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
 '<polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>'),
"map":('<polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/>'
 '<line x1="8" y1="2" x2="8" y2="18"/><line x1="16" y1="6" x2="16" y2="22"/>'),
"star":'<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
"settings":('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83'
 'l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4'
 'a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1'
 'H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06'
 'A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51'
 'a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51'
 '1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z"/>'),
"layers":('<polygon points="12 2 22 8.5 12 15 2 8.5 12 2"/>'
 '<polyline points="2 15.5 12 22 22 15.5"/><polyline points="2 11.5 12 18 22 11.5"/>'),
"sun":('<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>'
 '<line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>'
 '<line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>'
 '<line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>'),
"flag_jp":'<rect x="2" y="5" width="20" height="14" rx="1" fill="#fff"/><circle cx="12" cy="12" r="4" fill="#bc002d"/>',
"flag_fr":'<rect x="2" y="5" width="20" height="14" rx="1" fill="#fff"/><rect x="2" y="5" width="6.67" height="14" fill="#002395"/><rect x="15.33" y="5" width="6.67" height="14" fill="#ed2939"/>',
"flag_th":'<rect x="2" y="5" width="20" height="14" rx="1" fill="#fff"/><rect x="2" y="5" width="20" height="3.5" fill="#ed1c24"/><rect x="2" y="15.5" width="20" height="3.5" fill="#ed1c24"/><rect x="2" y="9.25" width="20" height="5.5" fill="#241d4f"/>',
"flag_it":'<rect x="2" y="5" width="20" height="14" rx="1" fill="#fff"/><rect x="2" y="5" width="6.67" height="14" fill="#009246"/><rect x="15.33" y="5" width="6.67" height="14" fill="#ce2b37"/>',
"flag_ae":'<rect x="2" y="5" width="20" height="14" rx="1" fill="#fff"/><rect x="2" y="5" width="20" height="4.67" fill="#009900"/><rect x="2" y="14.33" width="20" height="4.67" fill="#000"/><rect x="2" y="5" width="4" height="14" fill="#ff0000"/>',
"loader":'<circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="3" stroke-dasharray="31.4 31.4" class="anim-spin"/><circle cx="12" cy="12" r="4" fill="currentColor" opacity="0.3"/>',
"arrow_right":'<line x1="5" y1="12" x2="19" y2="12"/><polyline points="14 7 19 12 14 17"/>',
"clock":'<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
"sparkles":('<path d="M12 2l1.5 4.5L18 8l-4.5 1.5L12 14l-1.5-4.5L6 8l4.5-1.5L12 2Z"/>'
 '<path d="M18 14l.75 2.25L21 17l-2.25.75L18 20l-.75-2.25L15 17l2.25-.75L18 14Z"/>'
 '<path d="M6 12l.75 2.25L9 15l-2.25.75L6 18l-.75-2.25L3 15l2.25-.75L6 12Z"/>'),
"palette":('<circle cx="12" cy="12" r="2"/><path d="M12 2a10 10 0 0 0-6.5 18.5 2 2 0 0 0 3-1.5v-.5a2 2 0 0 1 2-2H15'
 'a5 5 0 0 0 5-5A7 7 0 0 0 12 2Z"/><path d="M9 8h.01"/><path d="M15 8h.01"/>'
 '<path d="M7 12h.01"/><path d="M17 12h.01"/>'),
"cpu":('<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/>'
 '<line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/>'
 '<line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/>'
 '<line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/>'
 '<line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/>'),
"zap":'<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
"moon":'<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79Z"/>',
"compass":'<circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/>',
"heart":('<path d="M19 14c1.5-1.5 2.5-3.5 2.5-5.5a5.5 5.5 0 0 0-10-3.25 5.5 5.5 0 0 0-10 3.25'
 'c0 2 1 4 2.5 5.5L12 22l7-8Z"/>'),
"dollar":'<line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
"people":('<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
 '<path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>'),
"ticket":('<path d="M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z"/>'
 '<path d="M9 9h1"/><path d="M14 9h1"/><path d="M9 13h6"/>'),
"route":'<circle cx="6" cy="19" r="3"/><circle cx="18" cy="5" r="3"/><path d="M6 19L18 5"/><path d="M6 16V6"/><path d="M18 8v10"/>',
"building":('<rect x="4" y="2" width="16" height="20" rx="2" ry="2"/><path d="M9 22v-4h6v4"/>'
 '<line x1="8" y1="6" x2="10" y2="6"/><line x1="8" y1="10" x2="10" y2="10"/>'
 '<line x1="14" y1="6" x2="16" y2="6"/><line x1="14" y1="10" x2="16" y2="10"/>'),
}

def ICON(name, size=20, anim=None, color=None):
    p = S.get(name,"")
    a = f' class="{anim}"' if anim else ""
    c = f' stroke="{color}"' if color else ""
    f = ' fill="none"'
    if name.startswith("flag_"): f,c = "",""
    return f'<svg viewBox="0 0 24 24" width="{size}" height="{size}"{f} stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"{c}{a}>{p}</svg>'

ACCENT = THEME
_R, _G, _B = int(THEME[1:3],16), int(THEME[3:5],16), int(THEME[5:7],16)
ADIM = darken(THEME,0.4)
AGLOW = f"rgba({_R},{_G},{_B},0.3)"
ATINT = f"rgba({_R},{_G},{_B},0.08)"

THEME_PRESETS = {
    "Ocean": "#22D3EE", "Midnight": "#6366F1", "Emerald": "#10b981",
    "Amethyst": "#8b5cf6", "Ruby": "#ef4444", "Amber": "#f59e0b",
}

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
html,body,.stApp {{ font-family:'Inter',sans-serif; background:#080d14; scroll-behavior:smooth; }}
::-webkit-scrollbar {{ width:6px;height:6px; }}
::-webkit-scrollbar-track {{ background:#0a1520; }}
::-webkit-scrollbar-thumb {{ background:#1e3050;border-radius:3px; }}
::-webkit-scrollbar-thumb:hover {{ background:{ACCENT}; }}

/* ── Keyframes ── */
@keyframes spin{{to{{transform:rotate(360deg)}}}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:0.5}}}}
@keyframes dash{{to{{stroke-dashoffset:-100}}}}
@keyframes glow{{0%,100%{{filter:drop-shadow(0 0 4px {AGLOW})}}50%{{filter:drop-shadow(0 0 18px {AGLOW})}}}}
@keyframes slideUp{{from{{opacity:0;transform:translateY(24px)}}to{{opacity:1;transform:translateY(0)}}}}
@keyframes fadeIn{{from{{opacity:0}}to{{opacity:1}}}}
@keyframes nodePulse{{0%,100%{{r:14}}50%{{r:18}}}}
@keyframes breathe{{0%,100%{{box-shadow:0 0 8px {AGLOW}}}50%{{box-shadow:0 0 24px {AGLOW}}}}}
@keyframes shimmer{{0%{{background-position:-200% 0}}100%{{background-position:200% 0}}}}
@keyframes float{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-6px)}}}}
@keyframes scaleIn{{from{{transform:scale(0.95);opacity:0}}to{{transform:scale(1);opacity:1}}}}
@keyframes gradientShift{{0%{{background-position:0% 50%}}50%{{background-position:100% 50%}}100%{{background-position:0% 50%}}}}

.anim-spin{{animation:spin 1.5s linear infinite;transform-origin:center}}
.anim-pulse{{animation:pulse 1.4s ease-in-out infinite}}
.anim-glow{{animation:glow 2s ease-in-out infinite}}
.anim-dash{{stroke-dasharray:20 10;animation:dash 1.5s linear infinite}}
.anim-slide{{animation:slideUp 0.5s ease-out}}
.anim-fade{{animation:fadeIn 0.6s ease-out}}
.anim-float{{animation:float 3s ease-in-out infinite}}
.anim-scale{{animation:scaleIn 0.3s ease-out}}
.anim-shimmer{{background:linear-gradient(90deg,transparent 25%,rgba(255,255,255,0.05) 50%,transparent 75%);background-size:200% 100%;animation:shimmer 2s infinite}}

/* ── Glassmorphism ── */
.glass{{background:rgba(14,22,35,0.6);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border:1px solid rgba(30,48,68,0.5);border-radius:16px}}
.glass-hover{{transition:all 0.3s ease}}
.glass-hover:hover{{background:rgba(20,30,50,0.8);border-color:{ACCENT};box-shadow:0 8px 32px rgba(0,0,0,0.3)}}

/* ── Skeleton ── */
.skeleton{{background:linear-gradient(90deg,#0e1a2b 25%,#162438 50%,#0e1a2b 75%);background-size:200% 100%;animation:shimmer 1.8s infinite;border-radius:10px}}
.skel-card{{height:80px;margin-bottom:0.5rem}}
.skel-line{{height:14px;width:60%;margin-bottom:0.4rem}}
.skel-line.short{{width:35%}}
.skel-block{{height:40px;width:100%;margin-bottom:0.5rem}}

/* ── Sidebar ── */
section[data-testid="stSidebar"]{{background:linear-gradient(180deg,#090e18 0%,#0b1424 100%)!important;border-right:1px solid #141f30!important;padding-top:0.5rem!important}}
.sidebar-title{{color:#e8f4ff;font-size:1rem;font-weight:700;display:flex;align-items:center;gap:0.4rem;padding:0 0.5rem}}
.sidebar-sec{{color:#6a8aaa;font-size:0.65rem;font-weight:600;letter-spacing:0.12em;text-transform:uppercase;margin:1.2rem 0.5rem 0.4rem;display:flex;align-items:center;gap:0.35rem;padding:0 0.3rem}}
.sidebar-chip{{background:rgba(14,26,43,0.7);border:1px solid #1a2e44;border-radius:8px;padding:0.4rem 0.7rem;margin:0 0.5rem 0.35rem;font-size:0.82rem;color:#7aa8cc;display:flex;align-items:center;gap:0.4rem;transition:0.2s;backdrop-filter:blur(4px)}}
.sidebar-chip:hover{{border-color:{ACCENT};color:#c0e0ff;background:rgba(20,40,70,0.8)}}
.history-item{{background:rgba(14,26,43,0.5);border:1px solid #1a2e44;border-radius:8px;padding:0.4rem 0.6rem;margin:0 0.5rem 0.25rem;font-size:0.74rem;color:#7aa8cc;cursor:pointer;transition:all 0.2s;display:flex;align-items:center;gap:0.3rem;line-height:1.3;backdrop-filter:blur(4px)}}
.history-item:hover{{border-color:{ACCENT};color:#fff;background:rgba(17,30,50,0.9)}}
div.stButton > button[data-testid*="hist_"]{{background:rgba(14,26,43,0.5) !important;border:1px solid #1a2e44 !important;border-radius:8px !important;padding:0.4rem 0.6rem !important;margin:0 0.5rem 0.15rem !important;font-size:0.74rem !important;color:#7aa8cc !important;cursor:pointer !important;text-align:left !important;line-height:1.3 !important;font-family:'Inter',sans-serif !important;height:auto !important;min-height:unset !important;box-shadow:none !important}}
div.stButton > button[data-testid*="hist_"]:hover{{border-color:{ACCENT} !important;color:#fff !important;background:rgba(17,30,50,0.9) !important}}

/* ── Hero ── */
.hero-wrap{{position:relative;border-radius:20px;overflow:hidden;margin-bottom:1.5rem;height:210px;background:linear-gradient(135deg,#0a1628 0%,{darken(ACCENT,0.65)} 50%,#0a1628 100%);background-size:200% 200%;animation:gradientShift 8s ease infinite}}
.hero-bg{{width:100%;height:100%;object-fit:cover;display:block;filter:brightness(0.18)saturate(0.3);position:absolute;top:0;left:0}}
.hero-ct{{position:relative;z-index:2;height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:1.5rem;background:rgba(0,0,0,0.1);backdrop-filter:blur(2px)}}
.hero-title{{font-size:2.3rem;font-weight:800;color:#fff;margin:0 0 0.25rem;display:flex;align-items:center;gap:0.5rem}}
.hero-sub{{color:#94adc8;font-size:0.9rem;max-width:520px;line-height:1.5}}

/* ── Search Card ── */
.search-card{{background:rgba(14,22,35,0.7);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);border:1px solid rgba(30,48,68,0.4);border-radius:18px;padding:1.6rem;margin-bottom:1.5rem;transition:all 0.3s ease}}
.search-card:hover{{border-color:rgba(30,48,68,0.7)}}
.form-label{{color:{ACCENT}!important;font-size:0.68rem!important;font-weight:600!important;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:0.2rem;display:flex;align-items:center;gap:0.3rem}}

/* ── Destinations ── */
.quick-dest{{border-radius:14px;overflow:hidden;position:relative;height:80px;cursor:pointer;transition:all 0.35s cubic-bezier(0.4,0,0.2,1)}}
.quick-dest:hover{{transform:translateY(-4px) scale(1.02);box-shadow:0 12px 32px rgba(0,0,0,0.5)}}
.qd-label{{position:absolute;bottom:5px;left:0;right:0;text-align:center;color:#fff;font-size:0.76rem;font-weight:600;display:flex;align-items:center;justify-content:center;gap:3px;text-shadow:0 1px 4px rgba(0,0,0,0.6)}}

/* ── Buttons ── */
div[data-testid="stButton"]>button{{background:linear-gradient(135deg,{ACCENT} 0%,{darken(ACCENT,0.25)} 50%,{darken(ACCENT,0.5)} 100%)!important;color:#fff!important;border:none!important;border-radius:14px!important;padding:0.8rem 2rem!important;font-size:1rem!important;font-weight:700!important;letter-spacing:0.02em!important;box-shadow:0 4px 24px {AGLOW},0 4px 12px rgba(0,0,0,0.4)!important;transition:all 0.3s cubic-bezier(0.4,0,0.2,1)!important}}
div[data-testid="stButton"]>button:hover{{box-shadow:0 8px 40px {AGLOW},0 6px 18px rgba(0,0,0,0.5)!important;transform:translateY(-3px) scale(1.01)!important}}
div[data-testid="stButton"]>button:active{{transform:translateY(0) scale(0.98)!important}}

/* ── Status Widgets ── */
[data-testid="stStatusWidget"]{{background:rgba(14,26,46,0.7)!important;backdrop-filter:blur(8px)!important;border:1px solid rgba(30,48,80,0.4)!important;border-radius:14px!important;margin-bottom:0.6rem!important;transition:all 0.3s ease!important}}
[data-testid="stStatusWidget"]:hover{{border-color:{ACCENT}!important;box-shadow:0 4px 20px rgba(0,0,0,0.3)!important}}
[data-testid="stStatusWidget"]>div:first-child{{background:rgba(14,26,46,0.5)!important;border-radius:14px 14px 0 0!important}}
[data-testid="stStatusWidget"] details,[data-testid="stStatusWidget"] details>div,[data-testid="stStatusWidget"] [data-testid="stVerticalBlock"]{{background:rgba(10,21,32,0.7)!important;color:#fff!important;padding:0.2rem 0.5rem!important}}
[data-testid="stStatusWidget"] *{{color:#fff!important}}
[data-testid="stStatusWidget"] a,[data-testid="stStatusWidget"] svg{{color:{ACCENT}!important}}

/* ── Sections ── */
.sec-head{{display:flex;align-items:center;gap:0.5rem;margin:1.5rem 0 0.6rem;padding-bottom:0.5rem;border-bottom:1px solid rgba(26,42,62,0.6)}}
.sec-head span{{font-size:1.1rem;font-weight:700;color:#e0edf8}}

/* ── Metrics ── */
.metric-row{{display:flex;gap:0.8rem;margin:1rem 0;animation:scaleIn 0.3s ease-out}}
.metric-box{{flex:1;background:rgba(14,22,35,0.7);backdrop-filter:blur(8px);border:1px solid rgba(30,46,68,0.4);border-radius:14px;padding:0.7rem 0.9rem;text-align:center;transition:all 0.3s ease}}
.metric-box:hover{{border-color:{ACCENT};transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,0,0,0.3)}}
.metric-val{{font-size:1.6rem;font-weight:700;color:{ACCENT}}}
.metric-lbl{{font-size:0.65rem;color:#5a7a96;margin-top:0.1rem;text-transform:uppercase;letter-spacing:0.08em;display:flex;align-items:center;justify-content:center;gap:0.25rem}}

/* ── Final Card ── */
.final-card{{background:rgba(12,26,46,0.8);backdrop-filter:blur(12px);border:1px solid #1e3a5c;border-left:4px solid {ACCENT};border-radius:16px;padding:1.6rem;line-height:1.8;color:#cce0f5;font-size:0.92rem;animation:scaleIn 0.3s ease-out}}

/* ── Save Bar ── */
.save-bar{{background:rgba(14,22,35,0.7);backdrop-filter:blur(8px);border:1px solid rgba(30,46,68,0.4);border-radius:12px;padding:0.7rem 1rem;color:#8ab8d8;font-size:0.84rem;margin-top:0.4rem;display:flex;align-items:center;gap:0.5rem}}

/* ── Form Elements ── */
.stTextArea textarea,.stSelectbox div[data-baseweb="select"],.stNumberInput input,.stDateInput input,.stMultiSelect div[data-baseweb="select"]{{background:rgba(10,21,32,0.7)!important;border:1px solid rgba(30,46,68,0.5)!important;border-radius:12px!important;color:#e8f4ff!important;font-size:0.93rem!important;transition:all 0.2s ease!important}}
.stTextArea textarea:focus,.stSelectbox div[data-baseweb="select"]:focus,.stNumberInput input:focus,.stDateInput input:focus{{border-color:{ACCENT}!important;box-shadow:0 0 0 3px {AGLOW}!important}}
.stTextArea textarea::placeholder{{color:#4a6a85!important}}
.stRadio div[role="radiogroup"]{{gap:0.4rem!important}}
.stRadio div[role="radiogroup"] label{{background:rgba(14,26,43,0.6)!important;backdrop-filter:blur(4px)!important;border:1px solid rgba(30,46,68,0.4)!important;border-radius:10px!important;padding:0.3rem 0.9rem!important;color:#7aa8cc!important;font-size:0.82rem!important;font-weight:500!important;transition:all 0.2s!important}}
.stRadio div[role="radiogroup"] label:hover{{border-color:{ACCENT}!important;color:#c0e0ff!important}}
.stRadio div[role="radiogroup"] label[data-checked="true"]{{background:{AGLOW}!important;border-color:{ACCENT}!important;color:{ACCENT}!important;font-weight:600!important}}
.stColorPicker>div>{{gap:0.5rem!important}}
.stColorPicker>div>div:first-child{{border-radius:10px!important;overflow:hidden!important}}

/* ── Typography ── */
.stMarkdown p,.stMarkdown li,.stMarkdown td,.stMarkdown th{{color:#cce0f5!important}}
.stMarkdown h1,.stMarkdown h2,.stMarkdown h3{{color:#e8f4ff!important;font-weight:700!important}}
.stMarkdown code{{background:rgba(14,26,43,0.7)!important;color:{ACCENT}!important;padding:0.12em 0.35em;border-radius:4px}}
.stAlert{{background:rgba(14,26,43,0.7)!important;backdrop-filter:blur(8px)!important;border-radius:12px!important;border:1px solid rgba(30,46,68,0.4)!important}}
.stAlert p,.stAlert div{{color:#e0edf8!important}}

/* ── Download ── */
div[data-testid="stDownloadButton"]>button{{background:rgba(26,58,92,0.8)!important;backdrop-filter:blur(8px)!important;color:#e8f4ff!important;border:1px solid rgba(42,80,128,0.5)!important;border-radius:12px!important;transition:0.2s!important}}
div[data-testid="stDownloadButton"]>button:hover{{border-color:{ACCENT}!important;background:rgba(30,70,120,0.9)!important}}



/* ── Pipeline ── */
.pipeline-svg{{width:100%;max-width:700px;margin:0.5rem auto;display:block}}
.node-running{{animation:nodePulse 1.2s ease-in-out infinite;transform-origin:center}}
.edge-flow{{stroke:{ACCENT};stroke-width:2.5;stroke-dasharray:8 4;animation:dash 1s linear infinite}}
.edge-done{{stroke:{ADIM};stroke-width:2}}
.edge-pending{{stroke:#1e3050;stroke-width:2}}

/* ── Dashboard ── */
.dash-tabs{{margin-top:1rem}}
.dash-tabs button[data-baseweb="tab"]{{background:rgba(14,26,43,0.5)!important;border:1px solid #1e3050!important;border-radius:8px 8px 0 0!important;color:#7aa8cc!important;font-size:0.82rem!important;font-weight:500!important;padding:0.4rem 1rem!important;transition:all 0.2s!important}}
.dash-tabs button[aria-selected="true"]{{background:rgba(20,40,70,0.8)!important;border-color:{ACCENT}!important;color:{ACCENT}!important;font-weight:600!important;box-shadow:0 -2px 8px {AGLOW}!important}}
.dash-tabs [role="tabpanel"]{{background:rgba(14,22,35,0.5)!important;border:1px solid #1e3050!important;border-top:none!important;border-radius:0 0 12px 12px!important;padding:1rem!important}}
.result-card{{background:rgba(10,21,32,0.6);border:1px solid rgba(30,48,68,0.4);border-radius:12px;padding:1rem;margin-bottom:0.8rem;transition:all 0.2s;overflow-wrap:break-word;word-wrap:break-word;word-break:break-word}}
.result-card:hover{{border-color:{ACCENT};box-shadow:0 4px 16px rgba(0,0,0,0.3)}}
.result-card h4{{color:{ACCENT};font-size:0.85rem;font-weight:600;margin:0 0 0.4rem;display:flex;align-items:center;gap:0.3rem}}
.result-card p,.result-card li{{color:#b0cce8;font-size:0.85rem;line-height:1.6;margin:0.15rem 0}}
.result-card hr{{border:none;border-top:1px solid rgba(30,48,68,0.3);margin:0.5rem 0}}
.dash-stat{{flex:1;background:rgba(14,22,35,0.7);backdrop-filter:blur(8px);border:1px solid rgba(30,46,68,0.4);border-radius:12px;padding:0.6rem 0.8rem;text-align:center;transition:0.2s}}
.dash-stat:hover{{border-color:{ACCENT};transform:translateY(-2px)}}
.dash-stat-val{{font-size:1.3rem;font-weight:700;color:{ACCENT}}}
.dash-stat-lbl{{font-size:0.6rem;color:#5a7a96;text-transform:uppercase;letter-spacing:0.08em}}

/* ── Timeline ── */
.timeline{{position:relative;padding-left:1.8rem}}
.timeline::before{{content:'';position:absolute;left:8px;top:4px;bottom:4px;width:2px;background:linear-gradient(to bottom,{ACCENT},#1e3050);border-radius:1px}}
.tl-item{{position:relative;margin-bottom:1rem;padding-left:0.5rem;animation:slideUp 0.4s ease-out}}
.tl-item::before{{content:'';position:absolute;left:-1.45rem;top:0.35rem;width:10px;height:10px;border-radius:50%;background:{ACCENT};border:2px solid #0a1520;box-shadow:0 0 6px {AGLOW}}}
.tl-item h5{{color:#e0edf8;font-size:0.88rem;font-weight:600;margin:0 0 0.2rem}}
.tl-item p{{color:#8aaccc;font-size:0.8rem;margin:0;line-height:1.4}}

/* ── Primary Buttons ── */
button[kind="primary"]{{background:linear-gradient(135deg,{ACCENT} 0%,{darken(ACCENT,0.25)} 100%)!important;border-radius:12px!important}}
button[kind="secondary"]{{background:rgba(14,26,43,0.7)!important;backdrop-filter:blur(4px)!important;color:#a0c4e0!important;border:1px solid #1e3050!important;border-radius:12px!important}}
button[kind="secondary"]:hover{{border-color:{ACCENT}!important;color:#fff!important}}

/* ── Hide ── */
#MainMenu,footer,header{{visibility:hidden}}

/* ── Responsive ── */
@media(max-width:768px){{
.hero-title{{font-size:1.6rem}}
.hero-wrap{{height:160px}}
.metric-row,.ds_cols{{flex-wrap:wrap}}
.metric-box,.dash-stat{{min-width:45%}}
.quick-dest{{height:60px}}
.dash-stat{{margin-bottom:0.4rem}}
.search-card{{padding:1rem!important}}
div[data-testid="column"] button{{font-size:0.75rem!important;padding:0.4rem 0.6rem!important}}
.stDownloadButton,div[data-testid="stDownloadButton"]{{width:100%!important}}
}}
@media(max-width:480px){{
.hero-title{{font-size:1.2rem}}
.hero-wrap{{height:120px}}
.stSelectbox div[data-baseweb="select"]{{font-size:0.8rem!important}}
.stRadio div[role="radiogroup"] label{{font-size:0.7rem!important;padding:0.2rem 0.5rem!important}}
}}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)
st.markdown("""<script>
document.addEventListener('keydown',function(e){
  if(e.ctrlKey||e.metaKey){
    if(e.key==='Enter'){
      e.preventDefault();
      var btns=document.querySelectorAll('button[kind="primary"]');
      for(var b of btns){if(b.textContent.trim().includes('Plan')){b.click();break;}}
    }
    if(e.key==='s'){e.preventDefault();}
  }
  if(!e.ctrlKey&&!e.metaKey&&!e.altKey&&document.activeElement===document.body){
    var n=parseInt(e.key);
    if(n>=1&&n<=5){
      e.preventDefault();
      var icons=['Route','Calendar','People','Heart','Sparkles'];
      var spans=document.querySelectorAll('span');
      for(var s of spans){if(s.textContent===icons[n-1]){s.closest('button')&&s.closest('button').click();break;}}
    }
    if(e.key==='Escape'){
      var backs=document.querySelectorAll('button[kind="secondary"]');
      for(var b of backs){if(b.textContent.trim().includes('Back')){b.click();break;}}
    }
  }
});
</script>""", unsafe_allow_html=True)

AGENT_META = {
    "query_analyzer":("sparkles","Analyzing"),"parallel_agents":("layers","Agents"),
    "itinerary_agent":("calendar","Itinerary"),
}
AGENT_ORDER = list(AGENT_META.keys())

def SKELETON_CARDS():
    return "".join(
        f'<div class="skeleton skel-card" style="width:{70 + (i%3)*20}%;"></div>'
        f'<div class="skeleton skel-line{" short" if i%2==0 else ""}"></div>'
        for i in range(4)
    )

def pipeline_svg(completed=None, running=None):
    completed=completed or []; running=running or []
    nodes,edges="",""
    for i,n in enumerate(AGENT_ORDER):
        ik,l=AGENT_META[n]; x=60+i*130
        s="running" if n==running else "complete" if n in completed else "pending"
        c=ACCENT if s=="complete" else "#22D3EE" if s=="running" else "#1e3050"
        a="node-running" if s=="running" else ""
        nodes+=f'<g class="anim-fade"><circle cx="{x}" cy="35" r="18" fill="{c}" opacity="0.12"/><circle cx="{x}" cy="35" r="14" fill="#0e1a2e" stroke="{c}" stroke-width="2" class="{a}"/><foreignObject x="{x-10}" y="25" width="20" height="20"><div xmlns="http://www.w3.org/1999/xhtml" style="display:flex;align-items:center;justify-content:center;height:100%;">{ICON(ik,16,color=c)}</div></foreignObject><text x="{x}" y="66" text-anchor="middle" fill="#a0c4e0" font-size="9.5" font-weight="500">{l}</text></g>'
    for i in range(len(AGENT_ORDER)-1):
        x1,x2,y=60+i*130+14,60+(i+1)*130-14,35
        n1,n2=AGENT_ORDER[i],AGENT_ORDER[i+1]
        cl="edge-flow" if (n1 in completed and n2==running) else "edge-done" if (n1 in completed and n2 in completed) else "edge-pending"
        edges+=f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" class="{cl}"/>'
        mid=(x1+x2)/2
        edges+=f'<polygon points="{mid+4},{y} {mid-2},{y-4} {mid-2},{y+4}" fill="{ACCENT if "flow" in cl or "done" in cl else "#1e3050"}"/>'
    return f'<svg class="pipeline-svg" viewBox="0 0 700 80" xmlns="http://www.w3.org/2000/svg" style="width:100%;max-width:700px;margin:0.5rem auto;display:block;">{edges}{nodes}</svg>'

WIZARD_STEPS = [
    (1, "route", "Where"), (2, "calendar", "When"),
    (3, "people", "Who"), (4, "heart", "Preferences"), (5, "sparkles", "Review"),
]

def wizard_indicator(current):
    html = '<div style="display:flex;align-items:center;justify-content:center;gap:0;margin:1rem 0 1.5rem;flex-wrap:wrap;">'
    for i, (num, ik, label) in enumerate(WIZARD_STEPS):
        done = num < current
        active = num == current
        bg = ACCENT if done else (AGLOW if active else "#1e3050")
        bc = "#fff" if done else (ACCENT if active else "#4a6a85")
        html += (
            f'<div style="display:flex;align-items:center;{"flex:1;" if i < len(WIZARD_STEPS)-1 else ""}">'
            f'<div style="display:flex;flex-direction:column;align-items:center;gap:0.2rem;">'
            f'<div style="width:36px;height:36px;border-radius:50%;background:{bg};'
            f'border:2px solid {bc};display:flex;align-items:center;justify-content:center;'
            f'font-size:0.8rem;font-weight:700;color:#fff;transition:all 0.3s ease;'
            f'{"box-shadow:0 0 12px " + AGLOW + ";" if active else ""}">'
            f'{ICON(ik, 16, color="#fff") if done else (ICON(ik, 16, color=ACCENT) if active else str(num))}'
            f'</div>'
            f'<span style="font-size:0.65rem;color:{bc};font-weight:{600 if active else 400};'
            f'letter-spacing:0.05em;white-space:nowrap;">{label}</span>'
            f'</div>'
            f'{"<div style=\"flex:1;height:2px;background:" + (ACCENT if done else "#1e3050") + ";margin:0 0.5rem;margin-bottom:1rem;\"></div>" if i < len(WIZARD_STEPS)-1 else ""}'
            f'</div>'
        )
    html += "</div>"
    return html

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = (lat2 - lat1) * 3.14159 / 180
    dlon = (lon2 - lon1) * 3.14159 / 180
    a = (dlat/2)**2 + (dlon/2)**2
    return R * 2 * (a ** 0.5 if a <= 1 else 1.0)

@st.cache_data(ttl=3600, show_spinner=False)
def create_route_map(from_city, to_city):
    fc = CITY_COORDS.get(from_city)
    tc = CITY_COORDS.get(to_city)
    if not fc or not tc:
        return None, None
    mlat = (fc[0] + tc[0]) / 2
    mlon = (fc[1] + tc[1]) / 2
    m = folium.Map(location=[mlat, mlon], zoom_start=3,
                   tiles="cartodbdark_matter", control_scale=True,
                   attr="", zoom_control=False)
    folium.Marker(fc, popup=from_city, tooltip=from_city,
                  icon=folium.Icon(color="blue", icon="plane", prefix="fa")).add_to(m)
    folium.Marker(tc, popup=to_city, tooltip=to_city,
                  icon=folium.Icon(color="red", icon="map-marker", prefix="fa")).add_to(m)
    folium.PolyLine([fc, tc], color="#22D3EE", weight=2.5, opacity=0.7,
                    dash_array="8, 6").add_to(m)
    distance = haversine_km(fc[0], fc[1], tc[0], tc[1])
    folium.Marker(
        [mlat, mlon], popup=f"{distance:.0f} km",
        icon=folium.DivIcon(html=f'<div style="background:rgba(34,211,238,0.15);border:1px solid #22D3EE;color:#22D3EE;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;white-space:nowrap;">{distance:.0f} km | {(distance*0.621371):.0f} mi</div>')
    ).add_to(m)
    return m, distance

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"<div style='padding:0 0.5rem;'><div class='sidebar-title'>{ICON('globe',18)} AI Travel Planner</div></div>", unsafe_allow_html=True)
    st.markdown("---")

    st.markdown(f"<div class='sidebar-sec'>{ICON('palette',12)} Theme</div>", unsafe_allow_html=True)
    c1,c2=st.columns([1,2.5])
    with c1:
        nt=st.color_picker("C",THEME,label_visibility="collapsed",key="theme_picker")
    with c2:
        st.markdown(f"<div style='display:flex;align-items:center;gap:8px;height:36px;'><div style='width:26px;height:26px;border-radius:8px;background:{ACCENT};border:2px solid {lighten(ACCENT,0.2)};animation:breathe 2s ease-in-out infinite;'></div><span style='color:#a0c4e0;font-size:0.8rem;'>{ACCENT}</span></div>", unsafe_allow_html=True)
    if nt!=THEME: st.session_state.theme_color=nt; st.rerun()

    preset_keys = list(THEME_PRESETS.keys())
    current_preset = next((k for k,v in THEME_PRESETS.items() if v.upper()==THEME.upper()), "Custom")
    preset_sel = st.selectbox("Presets", ["Custom"]+preset_keys, index=0 if current_preset=="Custom" else preset_keys.index(current_preset)+1, label_visibility="collapsed", key="preset_sel")
    if preset_sel != "Custom" and THEME_PRESETS[preset_sel].upper() != THEME.upper():
        st.session_state.theme_color = THEME_PRESETS[preset_sel]; st.rerun()

    st.markdown(f"<div class='sidebar-sec'>{ICON('cpu',12)} Model</div>", unsafe_allow_html=True)
    model_name=st.selectbox("M",["llama-3.3-70b-versatile","llama-3.1-8b-instant","mixtral-8x7b-32768","gemma2-9b-it"],0,label_visibility="collapsed")

    st.markdown(f"<div class='sidebar-sec'>{ICON('layers',12)} Stack</div>", unsafe_allow_html=True)
    for i,l in [("link","LangGraph"),("brain","Groq · "+model_name.split("-")[0]),("database","PostgreSQL"),("search","Tavily"),("plane","AviationStack")]:
        st.markdown(f"<div class='sidebar-chip'>{ICON(i,13)} {l}</div>", unsafe_allow_html=True)

    st.markdown(f"<div class='sidebar-sec'>{ICON('clock',12)} History</div>", unsafe_allow_html=True)
    if st.session_state.history:
        for h in reversed(st.session_state.history[-5:]):
            if st.button(h, key=f"hist_{h}", use_container_width=True):
                st.session_state.viewing_history = h
                st.rerun()
    else:
        st.markdown("<div class='sidebar-chip' style='color:#4a6a85;'>No trips yet</div>", unsafe_allow_html=True)

    st.markdown("<div style='margin-top:1rem;padding:0.3rem 0.5rem;font-size:0.65rem;color:#4a6a85;display:flex;align-items:center;gap:0.3rem;'>" + ICON('database',10) + " Auto-saved</div>", unsafe_allow_html=True)

# ── Hero ──────────────────────────────────────────────────────────────────────
st.markdown(
f"""<div class="hero-wrap anim-fade">
<img class="hero-bg" src="https://images.unsplash.com/photo-1488646953014-85cb44e25828?w=1400&q=80" alt=""/>
<div class="hero-ct">
<div class="hero-title">{ICON('compass',26)} AI Travel Planner</div>
<div class="hero-sub">Tell us where you want to go — our AI agents build a complete trip with flights, hotels, weather &amp; itinerary.</div>
</div></div>""", unsafe_allow_html=True)

# ── Wizard ─────────────────────────────────────────────────────────────────────
step = st.session_state.wizard_step
st.markdown(wizard_indicator(step), unsafe_allow_html=True)

today = datetime.now().date()
fd = st.session_state.form_data

# ── Step 1: Where ──
if step == 1:
    st.markdown("<div class='search-card anim-scale'>", unsafe_allow_html=True)
    st.markdown(f"<div style='display:flex;align-items:center;gap:0.4rem;margin-bottom:0.8rem;'>{ICON('route',16,color=ACCENT)} <span style='color:#e0edf8;font-size:1rem;font-weight:700;'>Where to?</span></div>", unsafe_allow_html=True)
    trip_type = fd.get("trip_type", "Flights + Hotels")
    tt_opts = ["Flights + Hotels", "Flights Only", "Hotels Only", "Custom Itinerary"]
    trip_type = st.selectbox("Trip Type", tt_opts, index=tt_opts.index(trip_type) if trip_type in tt_opts else 0)
    r1 = st.columns([1, 1])
    with r1[0]:
        from_idx = next((i for i,c in enumerate(CITIES) if c == fd.get("from_city","")), 0)
        from_city = st.selectbox("From", CITIES, index=from_idx)
    with r1[1]:
        to_opts = [c for c in CITIES if c != from_city]
        to_idx = next((i for i,c in enumerate(to_opts) if c == fd.get("to_city","")), min(3, len(to_opts)-1))
        to_city = st.selectbox("To", to_opts, index=to_idx if to_idx < len(to_opts) else 0)
    route_map, distance = create_route_map(from_city, to_city)
    if route_map:
        _ = st_folium(route_map, width=None, height=220, returned_objects=[])
        if distance:
            st.markdown(f"<div style='text-align:center;margin-top:0.3rem;font-size:0.78rem;color:#94adc8;'>{distance:.0f} km ({distance*0.621371:.0f} mi) · {from_city.split('(')[0].strip()} → {to_city.split('(')[0].strip()}</div>", unsafe_allow_html=True)
    fd.update({"trip_type":trip_type,"from_city":from_city,"to_city":to_city}); autosave(fd)
    st.markdown("</div>", unsafe_allow_html=True)
    if st.button("Next →", key="wiz_next1", use_container_width=True, type="primary"):
        st.session_state.wizard_step = 2; st.rerun()

# ── Step 2: When ──
elif step == 2:
    st.markdown("<div class='search-card anim-scale'>", unsafe_allow_html=True)
    st.markdown(f"<div style='display:flex;align-items:center;gap:0.4rem;margin-bottom:0.8rem;'>{ICON('calendar',16,color=ACCENT)} <span style='color:#e0edf8;font-size:1rem;font-weight:700;'>When?</span></div>", unsafe_allow_html=True)
    dep_str = fd.get("dep_date","")
    ret_str = fd.get("ret_date","")
    try: dep_default = datetime.strptime(dep_str,"%Y-%m-%d").date() if dep_str else today+timedelta(days=14)
    except: dep_default = today+timedelta(days=14)
    try: ret_default = datetime.strptime(ret_str,"%Y-%m-%d").date() if ret_str else dep_default+timedelta(days=4)
    except: ret_default = dep_default+timedelta(days=4)
    r2 = st.columns([1, 1, 1])
    with r2[0]:
        dep_date = st.date_input("Departure", dep_default, min_value=today)
    with r2[1]:
        ret_date = st.date_input("Return", ret_default, min_value=dep_date)
    with r2[2]:
        dur = st.selectbox("Duration", ["flexible","3-5 days","5-7 days","7-10 days","10-14 days","14+ days"], index=["flexible","3-5 days","5-7 days","7-10 days","10-14 days","14+ days"].index(fd.get("duration","flexible")))
    nights = (ret_date - dep_date).days
    st.markdown(f"<div style='text-align:center;margin-top:0.5rem;padding:0.4rem;background:{ATINT};border-radius:10px;font-size:0.85rem;'>{ICON('moon',12)} <strong style='color:{ACCENT};'>{nights}</strong> night{'s' if nights!=1 else ''} trip</div>", unsafe_allow_html=True)
    fd.update({"dep_date":str(dep_date),"ret_date":str(ret_date),"duration":dur}); autosave(fd)
    st.markdown("</div>", unsafe_allow_html=True)
    c2a, c2b = st.columns([1, 1])
    with c2a:
        if st.button("← Back", key="wiz_back2", use_container_width=True):
            st.session_state.wizard_step = 1; st.rerun()
    with c2b:
        if st.button("Next →", key="wiz_next2", use_container_width=True, type="primary"):
            st.session_state.wizard_step = 3; st.rerun()

# ── Step 3: Who ──
elif step == 3:
    st.markdown("<div class='search-card anim-scale'>", unsafe_allow_html=True)
    st.markdown(f"<div style='display:flex;align-items:center;gap:0.4rem;margin-bottom:0.8rem;'>{ICON('people',16,color=ACCENT)} <span style='color:#e0edf8;font-size:1rem;font-weight:700;'>Who?</span></div>", unsafe_allow_html=True)
    r3 = st.columns([1, 1, 1])
    with r3[0]:
        adults = st.number_input("Adults", 1, 10, int(fd.get("adults",1)))
    with r3[1]:
        children = st.number_input("Children", 0, 10, int(fd.get("children",0)))
    with r3[2]:
        travel_class = st.selectbox("Class", ["Economy","Premium Economy","Business","First Class"], index=["Economy","Premium Economy","Business","First Class"].index(fd.get("travel_class","Economy")))
    st.markdown(f"<div style='margin-top:0.5rem;padding:0.6rem;background:{ATINT};border-radius:10px;font-size:0.85rem;'>{ICON('user',12)} <strong style='color:{ACCENT};'>{adults+children}</strong> traveler{'s' if adults+children!=1 else ''} · {travel_class}</div>", unsafe_allow_html=True)
    fd.update({"adults":adults,"children":children,"travel_class":travel_class}); autosave(fd)
    st.markdown("</div>", unsafe_allow_html=True)
    c3a, c3b = st.columns([1, 1])
    with c3a:
        if st.button("← Back", key="wiz_back3", use_container_width=True):
            st.session_state.wizard_step = 2; st.rerun()
    with c3b:
        if st.button("Next →", key="wiz_next3", use_container_width=True, type="primary"):
            st.session_state.wizard_step = 4; st.rerun()

# ── Step 4: Preferences ──
elif step == 4:
    st.markdown("<div class='search-card anim-scale'>", unsafe_allow_html=True)
    st.markdown(f"<div style='display:flex;align-items:center;gap:0.4rem;margin-bottom:0.8rem;'>{ICON('heart',16,color=ACCENT)} <span style='color:#e0edf8;font-size:1rem;font-weight:700;'>Preferences</span></div>", unsafe_allow_html=True)
    r4 = st.columns([1, 1])
    default_interests = fd.get("interests", ["Sightseeing","Food & Dining"])
    if isinstance(default_interests, str): default_interests = ["Sightseeing","Food & Dining"]
    with r4[0]:
        interests = st.multiselect("Interests", ["Sightseeing","Adventure","Food & Dining","Shopping","Beach & Relaxation","Culture & History","Nightlife","Nature & Wildlife"], default=default_interests)
    with r4[1]:
        budget = st.select_slider("Budget per person", options=["Budget","Moderate","Premium","Luxury"], value=fd.get("budget","Moderate"))
    pace = st.radio("Pace", ["Relaxed","Moderate","Packed"], horizontal=True, index=["Relaxed","Moderate","Packed"].index(fd.get("pace","Moderate")) if fd.get("pace") in ["Relaxed","Moderate","Packed"] else 1)
    fd.update({"interests":list(interests),"budget":budget,"pace":pace}); autosave(fd)
    st.markdown("</div>", unsafe_allow_html=True)
    c4a, c4b = st.columns([1, 1])
    with c4a:
        if st.button("← Back", key="wiz_back4", use_container_width=True):
            st.session_state.wizard_step = 3; st.rerun()
    with c4b:
        if st.button("Review →", key="wiz_next4", use_container_width=True, type="primary"):
            st.session_state.wizard_step = 5; st.rerun()

# ── Step 5: Review ──
elif step == 5:
    st.markdown("<div class='search-card anim-scale'>", unsafe_allow_html=True)
    st.markdown(f"<div style='display:flex;align-items:center;gap:0.4rem;margin-bottom:0.8rem;'>{ICON('sparkles',16,color=ACCENT)} <span style='color:#e0edf8;font-size:1rem;font-weight:700;'>Review Your Trip</span></div>", unsafe_allow_html=True)
    from_city = fd.get("from_city","Mumbai (BOM)")
    to_city = fd.get("to_city","Tokyo (NRT)")
    trip_type = fd.get("trip_type","Flights + Hotels")
    dep_str = fd.get("dep_date","")
    ret_str = fd.get("ret_date","")
    adults = int(fd.get("adults",1))
    children = int(fd.get("children",0))
    travel_class = fd.get("travel_class","Economy")
    interests = fd.get("interests",["Sightseeing"])
    budget = fd.get("budget","Moderate")
    pace = fd.get("pace","Moderate")
    dur = fd.get("duration","flexible")
    needs_flight = trip_type in ("Flights + Hotels", "Flights Only")
    needs_hotel = trip_type in ("Flights + Hotels", "Hotels Only")
    route_map, distance = create_route_map(from_city, to_city)
    if route_map:
        _ = st_folium(route_map, width=None, height=200, returned_objects=[])
        if distance:
            st.markdown(f"<div style='text-align:center;margin-top:0.3rem;font-size:0.78rem;color:#94adc8;'>{distance:.0f} km ({distance*0.621371:.0f} mi) · {from_city.split('(')[0].strip()} → {to_city.split('(')[0].strip()}</div>", unsafe_allow_html=True)
    labels = [
        ("ticket", "Trip Type", trip_type),
        ("route", "Route", f"{from_city.split('(')[0].strip()} → {to_city.split('(')[0].strip()}"),
        ("calendar", "Dates", f"{dep_str} → {ret_str}"),
        ("moon", "Duration", dur),
        ("user", "Travelers", f"{adults} adult{'s' if adults>1 else ''}{', '+str(children)+' child' if children else ''}"),
        ("building", "Class", travel_class),
        ("heart", "Interests", ", ".join(interests) if interests else "None"),
        ("star", "Budget", budget),
        ("sun", "Pace", pace),
    ]
    for ik, lb, val in labels:
        st.markdown(f"<div style='display:flex;align-items:center;gap:0.5rem;padding:0.3rem 0;border-bottom:1px solid rgba(30,48,68,0.3);'><span style='color:{ACCENT};'>{ICON(ik,12)}</span><span style='color:#6a8aaa;font-size:0.75rem;width:65px;'>{lb}</span><span style='color:#cce0f5;font-size:0.88rem;'>{val}</span></div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    c5a, c5b = st.columns([1, 1])
    with c5a:
        if st.button("← Edit", key="wiz_back5", use_container_width=True):
            st.session_state.wizard_step = 4; st.rerun()
    with c5b:
        generate = st.button("Plan My Trip", use_container_width=True, type="primary")

try:
    generate
except NameError:
    generate = False

# ── Previous result (persists across reruns) ──
if st.session_state.viewing_history:
    hk = st.session_state.viewing_history
    if hk in st.session_state.trip_history:
        st.session_state.last_result = st.session_state.trip_history[hk]
    st.session_state.viewing_history = None
lr = st.session_state.last_result
if lr and not generate:
    st.markdown("---")
    st.markdown(f"<div class='sec-head'>{ICON('layers',16)}<span>Trip Dashboard</span></div>", unsafe_allow_html=True)

    lr_flight = lr.get("flight",""); lr_hotel = lr.get("hotel",""); lr_weather = lr.get("weather",""); lr_itin = lr.get("itinerary","")
    def lr_cnt(txt, kw):
        if not txt: return 0
        return len([l for l in txt.split('\n') if l.strip()[:5].startswith(kw)])
    f_cnt = lr_cnt(lr_flight, ('* ','- ','✓','Flig','Airl','✈','Air ','Rout'))
    h_cnt = lr_cnt(lr_hotel, ('* ','- ','✓','Hote','🏨','⭐','Room','Stay'))
    w_cnt = lr_cnt(lr_weather, ('°','°C','Day','fore','Morn','Afft','Even'))
    i_cnt = lr_cnt(lr_itin, ('**Da','### ','Day ','- Da','★'))
    def lr_fmt(n):
        if n == 0: return ("✓", "1.1rem")
        return (str(n), "1.3rem" if n < 999 else "1rem")
    ds_cols = st.columns(4)
    for col, (ik, raw, lb) in zip(ds_cols, [("Plane",f_cnt,"Flights"),("Building",h_cnt,"Hotels"),("Sun",w_cnt,"Weather"),("Calendar",i_cnt,"Itinerary")]):
        v, fs = lr_fmt(raw)
        with col:
            st.markdown(f"<div class='dash-stat'><div class='dash-stat-val' style='font-size:{fs};'>{v}</div><div class='dash-stat-lbl'>{ICON(ik,10)} {lb}</div></div>", unsafe_allow_html=True)

    tab_pairs = [("Flight", lr_flight), ("Hotel", lr_hotel), ("Weather", lr_weather), ("Itinerary", lr_itin)]
    active_tabs = [(tl, c) for tl, c in tab_pairs if c]
    if not active_tabs:
        active_tabs = tab_pairs[:1]
    tabs = st.tabs([t[0] for t in active_tabs])
    for ti, (tl, c) in enumerate(active_tabs):
        with tabs[ti]:
            st.markdown(f"<div class='result-card anim-scale'>{c or '_No data_'}</div>", unsafe_allow_html=True)

    c_dl, c_json, c_pdf, c_in = st.columns([1, 1, 1, 2])
    with c_dl:
        st.download_button("Markdown", data=lr.get("fc",""), file_name=lr.get("fn","trip.md"), mime="text/markdown", use_container_width=True)
    with c_json:
        lr_fn = lr.get("fn","trip.md").replace(".md",".json")
        lr_jc = json.dumps({"destination": lr.get("to_city","?").split("(")[0].strip() if lr.get("to_city") else "?", "generated_at": datetime.now().isoformat(), "flight": lr.get("flight",""), "hotel": lr.get("hotel",""), "weather": lr.get("weather",""), "itinerary": lr.get("itinerary","")}, indent=2, default=str)
        st.download_button("JSON", data=lr_jc, file_name=lr_fn, mime="application/json", use_container_width=True)
    with c_pdf:
        try:
            lr_pdf = markdown_to_pdf(lr.get("fn","trip.md").replace(".md","").replace("_"," "), lr.get("fc",""))
            st.download_button("PDF", data=lr_pdf, file_name=lr.get("fn","trip.md").replace(".md",".pdf"), mime="application/pdf", use_container_width=True)
        except:
            st.button("PDF", disabled=True, use_container_width=True)
    with c_in:
        st.markdown(f"<div class='save-bar'>{ICON('folder',14)} <code>travel_plans/{lr.get('fn','')}</code></div>", unsafe_allow_html=True)
    st.markdown(
        f"""<div class="metric-row anim-slide">
        <div class="metric-box"><div class="metric-val">{lr.get('agents',0)}</div><div class="metric-lbl">{ICON('layers',11)} Agents</div></div>
        <div class="metric-box"><div class="metric-val">{lr.get('llm_calls',0)}</div><div class="metric-lbl">{ICON('brain',11)} LLM Calls</div></div>
        <div class="metric-box"><div class="metric-val">{lr.get('time',0):.1f}s</div><div class="metric-lbl">{ICON('clock',11)} Time</div></div>
        <div class="metric-box"><div class="metric-val">{ICON('check',16)}</div><div class="metric-lbl">{ICON('map',11)} {lr.get('to_city','?')[:3]}</div></div>
        </div>""", unsafe_allow_html=True)

if generate:
    to_city = fd.get("to_city","")
    if not to_city:
        st.warning("Please select a destination city.")
    else:
        from_city = fd.get("from_city","Mumbai (BOM)")
        trip_type = fd.get("trip_type","Flights + Hotels")
        dep_date = fd.get("dep_date","")
        ret_date = fd.get("ret_date","")
        adults = int(fd.get("adults",1))
        children = int(fd.get("children",0))
        travel_class = fd.get("travel_class","Economy")
        interests = fd.get("interests",["Sightseeing"])
        if isinstance(interests, str): interests = ["Sightseeing"]
        budget = fd.get("budget","Moderate")
        pace = fd.get("pace","Moderate")
        dur = fd.get("duration","flexible")
        needs_flight = trip_type in ("Flights + Hotels", "Flights Only")
        needs_hotel = trip_type in ("Flights + Hotels", "Hotels Only")

        user_query = f"Plan a {pace.lower()} {budget.lower()} trip to {to_city.split('(')[0].strip()} from {from_city.split('(')[0].strip()} for {adults} adult{'s' if adults>1 else ''}"
        if children: user_query += f" and {children} child{'ren' if children>1 else ''}"
        user_query += f" from {dep_date} to {ret_date}. Interests: {', '.join(interests) if isinstance(interests,list) else interests}."
        if needs_flight: user_query += " Include flights."
        if needs_hotel: user_query += " Include hotels."

        config = {"configurable": {"thread_id": f"{from_city[:3]}_{to_city[:3]}_{dep_date}"}}
        collected = {"flight_results":"","hotel_results":"","weather_results":"","itinerary":"","llm_calls":0,"agent_times":{},"query_analysis":{}}
        completed_agents, running_agent = [], None

        st.markdown("---")
        st.markdown(f"<div class='sec-head'>{ICON('layers',16)}<span>AI Agents Working</span></div>", unsafe_allow_html=True)

        pipe_placeholder = st.empty()
        pipe_placeholder.markdown(pipeline_svg([], None), unsafe_allow_html=True)

        initial_state = {
            "messages": [HumanMessage(content=user_query)],
            "user_query": user_query,
            "query_analysis": {}, "model_name": model_name,
            "flight_results": "", "hotel_results": "", "weather_results": "",
            "itinerary": "", "llm_calls": 0, "agent_times": {}, "active_agents": [],
        }

        skel_holder = st.empty()
        skel_holder.markdown(f"<div class='glass' style='padding:1rem;margin-bottom:0.6rem;'><div style='display:flex;align-items:center;gap:0.5rem;margin-bottom:0.5rem;color:#6a8aaa;font-size:0.8rem;'>{ICON('loader',14)} Agents initializing…</div>{SKELETON_CARDS()}</div>", unsafe_allow_html=True)

        try:
            for chunk in app.stream(initial_state, config=config, stream_mode="updates"):
                skel_holder.empty()
                for node_name, state_update in chunk.items():
                    running_agent = node_name
                    ik, lb = AGENT_META.get(node_name, ("settings",node_name))
                    pipe_placeholder.markdown(pipeline_svg(completed_agents, running_agent), unsafe_allow_html=True)

                    with st.status(lb, state="running", expanded=True):
                        res_placeholder = st.empty()
                        res_placeholder.markdown(f"<div style='padding:0.3rem 0;'>{SKELETON_CARDS()}</div>", unsafe_allow_html=True)
                        if node_name == "query_analyzer":
                            a = state_update.get("query_analysis",{})
                            collected["query_analysis"] = a
                            if a:
                                tags=[]
                                if a.get("destination"): tags.append(f"{ICON('map',10)} {a['destination']}")
                                if a.get("duration_days"): tags.append(f"{ICON('calendar',10)} {a['duration_days']}d")
                                if a.get("budget"): tags.append(f"{ICON('star',10)} {a['budget']}")
                                t=a.get("travelers",1)
                                tags.append(f"{ICON('user',10)} {t} traveler{'s' if t>1 else ''}")
                                res_placeholder.markdown("<div style='display:flex;flex-wrap:wrap;gap:0.5rem;padding:0.3rem 0;'>"+"".join(f"<span style='background:{AGLOW};border:1px solid {ACCENT};color:{ACCENT};padding:0.1rem 0.6rem;border-radius:12px;font-size:0.75rem;display:inline-flex;align-items:center;gap:0.2rem;'>{t}</span>" for t in tags)+"</div>",unsafe_allow_html=True)
                        elif node_name=="parallel_agents":
                            fr = state_update.get("flight_results","")
                            hr = state_update.get("hotel_results","")
                            wr = state_update.get("weather_results","")
                            collected.update({"flight_results":fr,"hotel_results":hr,"weather_results":wr})
                            parts = []
                            if fr: parts.append(f"<details open><summary style='color:{ACCENT};font-weight:600;cursor:pointer;font-size:0.82rem;margin-bottom:0.2rem;'>{ICON('plane',12)} Flight</summary><div style='padding:0.2rem 0 0.5rem;font-size:0.82rem;'>{fr}</div></details>")
                            if hr: parts.append(f"<details><summary style='color:{ACCENT};font-weight:600;cursor:pointer;font-size:0.82rem;margin-bottom:0.2rem;'>{ICON('building',12)} Hotel</summary><div style='padding:0.2rem 0 0.5rem;font-size:0.82rem;'>{hr}</div></details>")
                            if wr: parts.append(f"<details><summary style='color:{ACCENT};font-weight:600;cursor:pointer;font-size:0.82rem;margin-bottom:0.2rem;'>{ICON('sun',12)} Weather</summary><div style='padding:0.2rem 0 0.5rem;font-size:0.82rem;'>{wr}</div></details>")
                            res_placeholder.markdown("".join(parts) if parts else "_No data_", unsafe_allow_html=True)
                        elif node_name=="itinerary_agent":
                            collected["itinerary"]=state_update.get("itinerary","")
                            res_placeholder.markdown(collected["itinerary"] or "_No itinerary_")
                        collected["llm_calls"]=collected.get("llm_calls",0)+state_update.get("llm_calls",0)
                        new_times = state_update.get("agent_times",{})
                        if new_times:
                            collected["agent_times"]={**collected.get("agent_times",{}), **new_times}

                    if node_name not in completed_agents: completed_agents.append(node_name)
        except Exception as e:
            st.error(f"An error occurred during planning: {e}")

        pipe_placeholder.markdown(pipeline_svg(completed_agents, None), unsafe_allow_html=True)

        agents_run = len([a for a in completed_agents if a!="query_analyzer"])
        total_time = sum(collected.get("agent_times",{}).values())

        fr, hr, wr, itin = collected.get("flight_results",""), collected.get("hotel_results",""), collected.get("weather_results",""), collected.get("itinerary","")

        st.markdown(
f"""<div class="metric-row anim-slide" style="margin-bottom:1.2rem">
<div class="metric-box"><div class="metric-val">{agents_run}</div><div class="metric-lbl">{ICON('layers',11)} Agents</div></div>
<div class="metric-box"><div class="metric-val">{collected['llm_calls']}</div><div class="metric-lbl">{ICON('brain',11)} LLM Calls</div></div>
<div class="metric-box"><div class="metric-val">{total_time:.1f}s</div><div class="metric-lbl">{ICON('clock',11)} Time</div></div>
<div class="metric-box"><div class="metric-val">{ICON('check',16)}</div><div class="metric-lbl">{ICON('star',11)} Ready</div></div>
</div>""", unsafe_allow_html=True)

        st.markdown(f"<div class='sec-head'>{ICON('layers',16)}<span>Trip Dashboard</span></div>", unsafe_allow_html=True)

        # ── Quick stats row ──
        def item_count(txt, kw):
            if not txt: return 0
            return len([l for l in txt.split('\n') if l.strip()[:5].startswith(kw)])

        flight_count = item_count(fr, ('* ','- ','✓','Flig','Airl','✈','Air ','Rout')) if needs_flight else -1
        hotel_count = item_count(hr, ('* ','- ','✓','Hote','🏨','⭐','Room','Stay')) if needs_hotel else -1
        weather_count = item_count(wr, ('°','°C','Day','fore','Morn','Afft','Even')) if wr else 0
        itin_count = item_count(itin, ('**Da','### ','Day ','- Da','★')) if itin else 0

        def fmt_count(n, unit):
            if n == -1: return ("—", "0.9rem")
            if n == 0: return ("✓", "1.1rem")
            return (str(n), "1.3rem" if n < 999 else "1rem")

        ds_cols = st.columns(4)
        for col, (ik, raw, lb) in zip(ds_cols, [("Plane", flight_count, "Flights"), ("Building", hotel_count, "Hotels"), ("Sun", weather_count, "Weather"), ("Calendar", itin_count, "Itinerary")]):
            val, fs = fmt_count(raw, lb)
            with col:
                st.markdown(f"<div class='dash-stat'><div class='dash-stat-val' style='font-size:{fs};'>{val}</div><div class='dash-stat-lbl'>{ICON(ik,10)} {lb}</div></div>", unsafe_allow_html=True)

        # ── Tabbed results ──
        tab_labels = ["Flight", "Hotel", "Weather", "Itinerary"]
        if needs_flight == False and not fr: tab_labels[0] = None
        if needs_hotel == False and not hr: tab_labels[1] = None
        active_tabs = [t for t in tab_labels if t is not None]
        if active_tabs:
            tabs = st.tabs(active_tabs)
            for ti, tl in enumerate(active_tabs):
                with tabs[ti]:
                    if tl == "Flight":
                        st.markdown(f"<div class='result-card anim-scale'>{fr or '_No flight data available_'}</div>" if fr else "_No flight data_", unsafe_allow_html=True)
                    elif tl == "Hotel":
                        st.markdown(f"<div class='result-card anim-scale'>{hr or '_No hotel data available_'}</div>" if hr else "_No hotel data_", unsafe_allow_html=True)
                    elif tl == "Weather":
                        st.markdown(f"<div class='result-card anim-scale'>{wr or '_No weather data available_'}</div>" if wr else "_No weather data_", unsafe_allow_html=True)
                    elif tl == "Itinerary":
                        st.markdown(f"<div class='result-card anim-scale'>{itin or '_No itinerary_'}</div>" if itin else "_No itinerary_", unsafe_allow_html=True)

        # Save file
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fn = f"trip_{to_city[:3]}_{ts}.md"
        sd = os.path.join(os.path.dirname(__file__),"travel_plans")
        os.makedirs(sd, exist_ok=True)

        fc = f"""# {to_city.split('(')[0].strip()} Trip Plan
**From:** {from_city} → **To:** {to_city}
**Dates:** {dep_date} → {ret_date} | **Travelers:** {adults} adult{'s' if adults>1 else ''}{f', {children} child' if children else ''}
**Class:** {travel_class} | **Budget:** {budget} | **Pace:** {pace}
**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## Flight Information
{fr or 'Not requested'}

---

## Hotel Information
{hr or 'Not requested'}

---

## Weather Information
{wr or 'Not requested'}

---

## Itinerary
{itin or 'N/A'}

---

*LLM Calls: {collected['llm_calls']} | Agents: {agents_run} | Time: {total_time:.1f}s*
"""
        with open(os.path.join(sd,fn),"w",encoding="utf-8") as f: f.write(fc)

        short = f"{to_city.split('(')[0].strip()} · {dep_date}"
        if short not in st.session_state.history: st.session_state.history.append(short)
        st.session_state.trip_history[short] = {
            "itinerary": itin, "flight": fr, "hotel": hr, "weather": wr,
            "agents": agents_run, "llm_calls": collected["llm_calls"], "time": total_time,
            "to_city": to_city, "from_city": from_city, "fc": fc, "fn": fn,
        }

        dl_col, json_col, pdf_col, info_col = st.columns([1, 1, 1, 2])
        with dl_col:
            st.download_button("Markdown", data=fc, file_name=fn, mime="text/markdown", use_container_width=True)
        with json_col:
            fj = fn.replace(".md", ".json")
            jc = json.dumps({
                "destination": to_city.split("(")[0].strip(), "origin": from_city.split("(")[0].strip(),
                "dates": {"departure": dep_date, "return": ret_date},
                "travelers": {"adults": adults, "children": children},
                "class": travel_class, "budget": budget, "pace": pace,
                "interests": list(interests) if isinstance(interests, list) else [],
                "flight": fr, "hotel": hr, "weather": wr, "itinerary": itin,
                "generated_at": datetime.now().isoformat(),
            }, indent=2, default=str)
            st.download_button("JSON", data=jc, file_name=fj, mime="application/json", use_container_width=True)
        with pdf_col:
            try:
                pdf_data = markdown_to_pdf(fn.replace(".md","").replace("_"," "), fc)
                st.download_button("PDF", data=pdf_data, file_name=fn.replace(".md",".pdf"), mime="application/pdf", use_container_width=True)
            except Exception as e:
                st.button("PDF", disabled=True, use_container_width=True)
        with info_col: st.markdown(f"<div class='save-bar'>{ICON('folder',14)} Saved — <code>travel_plans/{fn}</code></div>", unsafe_allow_html=True)

        st.session_state.last_result = {
            "itinerary": itin, "flight": fr, "hotel": hr, "weather": wr,
            "agents": agents_run, "llm_calls": collected["llm_calls"], "time": total_time,
            "to_city": to_city, "from_city": from_city, "fc": fc, "fn": fn,
        }
