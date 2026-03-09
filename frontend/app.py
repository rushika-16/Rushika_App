import streamlit as st
import streamlit.components.v1 as components
import requests
import re
from datetime import datetime
import html
import json

try:
    from streamlit_confetti import confetti
except Exception:
    confetti = None

BACKEND_URL = "http://127.0.0.1:8000"

# ---------------------------
# SESSION STATE INIT
# ---------------------------
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Welcome! I'm your Credit Assistant. Let's get your pre-qualified offer in under 2 minutes. What is your full name?"}]

if "step" not in st.session_state:
    st.session_state.step = "name"

if "user_data" not in st.session_state:
    st.session_state.user_data = {
        "name": None, "mobile": None, "email": None, 
        "address": None, "dob": None, "income": None, "ssn": None, "ssn_masked": None, "credit_score": None,
        "employment_type": None
    }

if st.session_state.step == "credit_score":
    st.session_state.step = "ssn"

if "offer" not in st.session_state:
    st.session_state.offer = None

if "application_id" not in st.session_state:
    st.session_state.application_id = None

if "explanation_data" not in st.session_state:
    st.session_state.explanation_data = None

if "explanation_query" not in st.session_state:
    st.session_state.explanation_query = "Explain this decision based on approved policy criteria."

if "income_invalid_attempts" not in st.session_state:
    st.session_state.income_invalid_attempts = 0

if "show_ssn_input" not in st.session_state:
    st.session_state.show_ssn_input = False

if "ssn_input_value" not in st.session_state:
    st.session_state.ssn_input_value = ""

if "clear_ssn_input_on_next_render" not in st.session_state:
    st.session_state.clear_ssn_input_on_next_render = False

INELIGIBLE_PROFESSION_MESSAGE = (
    "Thank you for sharing your details. At the moment, our credit card program is available only for salaried and "
    "self-employed individuals. We truly appreciate your interest and hope to serve you in the future."
)

# ---------------------------
# VALIDATION FUNCTIONS
# ---------------------------
INVALID_NAME_PHRASES = {
    "hi",
    "hello",
    "hey",
    "yo",
    "sup",
    "whats up",
    "what s up",
    "hi dear",
    "hey dear",
    "hello dear",
    "hi whats up",
    "hi what s up",
}

NAME_DISALLOWED_TOKENS = {
    "hi", "hello", "hey", "yo", "sup", "whats", "what", "up",
    "dear", "bro", "buddy", "dude", "sir", "madam",
    "you", "your", "me", "my", "mine", "i", "am", "im", "got",
    "test", "random", "name", "guest", "none", "okay", "ok",
}

NAME_PREFIX_PATTERN = re.compile(r"^(my name is|i am|i'm|this is)\s+", re.IGNORECASE)


def normalize_name_candidate(value: str) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip())
    text = NAME_PREFIX_PATTERN.sub("", text).strip()
    return text


def is_invalid_name_input(value: str) -> bool:
    normalized_value = normalize_name_candidate(value)
    normalized = re.sub(r"[^a-zA-Z ]", " ", normalized_value.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()

    if not normalized:
        return True

    if normalized in INVALID_NAME_PHRASES:
        return True

    tokens = normalized.split()
    if len(tokens) < 2 or len(tokens) > 4:
        return True

    if any(len(token) < 2 for token in tokens):
        return True

    if any(token in NAME_DISALLOWED_TOKENS for token in tokens):
        return True

    return False


def validate_name(value):
    cleaned = normalize_name_candidate(value)
    if not re.fullmatch(r"[A-Za-z ]{2,}", cleaned):
        return False
    if is_invalid_name_input(cleaned):
        return False
    return True


def validate_mobile(value): return value.isdigit() and len(value) == 10
def validate_email(value): return re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", value)
def validate_address(value): return len(value.strip()) >= 8
def validate_dob(value):
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except: return False


def parse_income(value):
    cleaned = value.replace(",", "").strip()
    if not re.fullmatch(r"\d+(\.\d+)?", cleaned):
        return None

    parsed = float(cleaned)
    if parsed <= 0:
        return None
    return parsed


def normalize_ssn(value: str) -> str:
    return re.sub(r"\D", "", (value or "").strip())


def mask_ssn(value: str) -> str:
    normalized = normalize_ssn(value)
    if len(normalized) != 9:
        return "***-**-***"
    return f"***-**-{normalized[-3:]}"


def validate_ssn(value: str) -> bool:
    cleaned = (value or "").strip()
    return bool(re.fullmatch(r"\d{9}", cleaned) or re.fullmatch(r"\d{3}-\d{2}-\d{4}", cleaned))


def map_profession(value: str) -> str:
    lowered = (value or "").strip().lower()

    salaried_keywords = {
        "salaried", "salary", "salryed", "employee", "job", "private job", "government job", "govt job", "service",
    }
    self_employed_keywords = {
        "self-employed", "self employed", "business", "business owner", "entrepreneur", "freelancer", "consultant", "shop owner",
    }
    retired_keywords = {"retired", "retiree"}
    student_keywords = {"student"}
    homemaker_keywords = {"homemaker", "housewife", "house maker", "stay at home"}

    if lowered in salaried_keywords:
        return "Salaried"
    if lowered in self_employed_keywords:
        return "Self-employed"
    if lowered in retired_keywords:
        return "Retired"
    if lowered in student_keywords:
        return "Student"
    if lowered in homemaker_keywords:
        return "Homemaker"
    return "Unknown"


def celebrate_success():
    if confetti:
        try:
            confetti("🎉")
            return
        except TypeError:
            try:
                confetti(emojis="🎉")
                return
            except Exception:
                pass
        except Exception:
            pass
    st.balloons()


def reset_demo_state():
    st.session_state.clear()
    st.rerun()


def auto_scroll_to_latest_message(trigger_token: str):
    components.html(
        """
        <script>
            (() => {
                const rerenderToken = __RERENDER_TOKEN__;

                const scrollToLatest = () => {
                    try {
                        const streamlitDoc = window.parent.document;
                        const mainContainer = streamlitDoc.querySelector('.main');
                        const anchor = streamlitDoc.getElementById('chat-bottom-anchor');

                        if (anchor) {
                            anchor.scrollIntoView({ behavior: 'auto', block: 'center' });
                        }

                        if (mainContainer) {
                            mainContainer.scrollTop = mainContainer.scrollHeight;
                        }

                        if (streamlitDoc.body) {
                            window.parent.scrollTo(0, streamlitDoc.body.scrollHeight);
                        }
                    } catch (error) {
                        // no-op
                    }
                };

                scrollToLatest();
                [60, 140, 260, 420, 700, 1100, 1700, 2400, 3200, 4200, 5600].forEach((delayMs) => {
                    setTimeout(scrollToLatest, delayMs);
                });

                let retries = 0;
                const retryInterval = setInterval(() => {
                    scrollToLatest();
                    retries += 1;
                    if (retries >= 28) {
                        clearInterval(retryInterval);
                    }
                }, 140);

                try {
                    const streamlitDoc = window.parent.document;
                    const mainContainer = streamlitDoc.querySelector('.main') || streamlitDoc.body;
                    const observer = new MutationObserver(() => {
                        scrollToLatest();
                    });
                    observer.observe(mainContainer, { childList: true, subtree: true, attributes: true });
                    setTimeout(() => observer.disconnect(), 6500);
                } catch (observerError) {
                    // no-op
                }

                void rerenderToken;
            })();
        </script>
        """.replace("__RERENDER_TOKEN__", json.dumps(str(trigger_token))),
        height=0,
    )


def render_card_preview(customer_name: str, card_type: str):
    normalized_tier = (card_type or "Standard").strip().lower()
    tier_label = (card_type or "Standard").title()

    theme_map = {
        "elite": {
            "background": "linear-gradient(145deg, #020617 0%, #111827 42%, #030712 100%)",
            "accent": "#e2e8f0",
            "glow": "rgba(148, 163, 184, 0.38)",
            "number": "#f8fafc",
            "logo": "#e2e8f0",
        },
        "premium": {
            "background": "linear-gradient(145deg, #1e3a8a 2%, #1d4ed8 38%, #0f172a 100%)",
            "accent": "#fcd34d",
            "glow": "rgba(147, 197, 253, 0.42)",
            "number": "#e0f2fe",
            "logo": "#f8fafc",
        },
        "standard": {
            "background": "linear-gradient(145deg, #111827 2%, #374151 45%, #1f2937 100%)",
            "accent": "#d1d5db",
            "glow": "rgba(156, 163, 175, 0.35)",
            "number": "#f3f4f6",
            "logo": "#e5e7eb",
        },
    }

    selected_theme = theme_map.get(normalized_tier, theme_map["standard"])
    safe_name = html.escape((customer_name or "Card Holder").strip() or "Card Holder")
    safe_tier = html.escape(tier_label)

    st.markdown(
        f"""
        <div style="
            max-width: 460px;
            border-radius: 18px;
            padding: 1.2rem 1.3rem;
            background: {selected_theme['background']};
            border: 1px solid rgba(255,255,255,0.18);
            box-shadow: 0 16px 28px rgba(2, 6, 23, 0.45);
            color: #f8fafc;
            margin-bottom: 0.5rem;
            position: relative;
            overflow: hidden;
        ">
            <div style="
                position:absolute;
                inset:0;
                background:
                    radial-gradient(circle at 18% 14%, {selected_theme['glow']} 0%, transparent 48%),
                    radial-gradient(circle at 82% 88%, rgba(255,255,255,0.07) 0%, transparent 46%),
                    linear-gradient(130deg, transparent 0%, rgba(255,255,255,0.08) 35%, transparent 64%);
                pointer-events:none;
            "></div>
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 1.2rem;">
                <div style="font-size: 0.88rem; letter-spacing: 0.12em; color: {selected_theme['accent']}; font-weight: 800;">{safe_tier}</div>
                <div style="font-size: 1.45rem; font-weight: 800; letter-spacing: 0.04em; color: {selected_theme['logo']};">VISA</div>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:flex-end; margin-bottom: 0.95rem;">
                <div style="
                    width: 56px;
                    height: 40px;
                    border-radius: 8px;
                    background:
                        linear-gradient(90deg, rgba(15,23,42,0.25) 0 22%, transparent 22% 27%, rgba(15,23,42,0.25) 27% 49%, transparent 49% 54%, rgba(15,23,42,0.25) 54% 100%),
                        linear-gradient(145deg, #f3f4f6, #9ca3af);
                    border: 1px solid rgba(15,23,42,0.42);
                "></div>
                <div style="font-size: 1.3rem; color: rgba(255,255,255,0.7);">◉◉◉</div>
            </div>
            <div style="font-family: 'Courier New', monospace; font-size: 1.03rem; letter-spacing: 0.13em; color: {selected_theme['number']}; margin-bottom: 0.9rem;">
                4820 •••• •••• 1079
            </div>
            <div style="display:flex; justify-content:space-between; align-items:flex-end; gap: 0.8rem;">
                <div>
                    <div style="font-size: 0.65rem; color: rgba(226,232,240,0.78); letter-spacing: 0.08em; margin-bottom: 0.18rem;">CARD HOLDER</div>
                    <div style="font-size: 1.05rem; font-weight: 700; text-transform: uppercase;">{safe_name}</div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size: 0.62rem; color: rgba(226,232,240,0.78); letter-spacing: 0.08em; margin-bottom: 0.18rem;">VALID THRU</div>
                    <div style="font-size: 0.9rem; font-weight: 700;">12/31</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ---------------------------
# AI EXPLANATION
# ---------------------------
def generate_ai_explanation(application_id, query_text):
    try:
        response = requests.post(
            f"{BACKEND_URL}/explain-decision",
            params={"application_id": application_id, "user_query": query_text},
            timeout=30,
        )
        if response.ok:
            return response.json()
        return {"explanation_text": "Information not available in approved credit policy.", "retrieved_chunks": [], "similarity_scores": []}
    except Exception:
        return {"explanation_text": "Information not available in approved credit policy.", "retrieved_chunks": [], "similarity_scores": []}


def fetch_credit_score_by_ssn(ssn: str) -> dict:
    try:
        response = requests.post(
            f"{BACKEND_URL}/lookup-credit-score",
            json={"ssn": ssn},
            timeout=30,
        )
        if response.ok:
            payload = response.json()
            return {
                "ok": True,
                "credit_score": int(payload.get("credit_score", 600)),
                "record_found": bool(payload.get("record_found", False)),
                "ssn_masked": payload.get("ssn_masked", mask_ssn(ssn)),
                "message": payload.get("message", ""),
            }
        return {
            "ok": False,
            "credit_score": 600,
            "record_found": False,
            "ssn_masked": mask_ssn(ssn),
            "message": "No Record Found",
        }
    except Exception:
        return {
            "ok": False,
            "credit_score": 600,
            "record_found": False,
            "ssn_masked": mask_ssn(ssn),
            "message": "No Record Found",
        }

# ---------------------------
# CHAT UI
# ---------------------------
st.set_page_config(page_title="AI Credit Assistant", page_icon="🤖")

st.markdown(
    """
    <style>
        .stApp {
            background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 48%, #ffffff 100%);
            --text-color: #0f172a;
            --secondary-text-color: #475569;
        }
        [data-testid="stHeader"] {
            background: transparent;
        }
        .block-container {
            max-width: 900px;
            padding-top: 2rem;
        }
        .hero-card {
            background: linear-gradient(120deg, #ffffff, #f8fafc);
            border: 1px solid #d6e0ec;
            border-radius: 16px;
            padding: 1.1rem 1.2rem;
            margin-bottom: 1rem;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
        }
        .hero-title {
            color: #0f172a;
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 0.25rem;
        }
        .hero-sub {
            color: #475569;
            font-size: 0.98rem;
        }
        [data-testid="stChatMessage"] {
            border: 1px solid #dbe4ef;
            border-radius: 14px;
            background: #ffffff;
            padding: 0.2rem 0.2rem;
        }
        [data-testid="stChatMessage"] * {
            color: #0f172a !important;
        }
        [data-testid="stChatInput"] {
            border-top: 0;
            background: transparent;
        }
        .stChatFloatingInputContainer {
            background: transparent !important;
        }
        .stChatFloatingInputContainer::before {
            background: transparent !important;
        }
        [data-testid="stChatInput"] > div {
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
        }
        [data-testid="stChatInput"] [data-baseweb="textarea"] {
            background: #ffffff !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 999px !important;
            box-shadow: none !important;
        }
        [data-testid="stChatInput"] textarea {
            border-radius: 12px !important;
            border: 1px solid #cbd5e1 !important;
            background: #ffffff !important;
            color: #0f172a !important;
            caret-color: #0f172a !important;
        }
        [data-testid="stChatInput"] button {
            background: #ffffff !important;
            color: #64748b !important;
            border: 0 !important;
            box-shadow: none !important;
        }
        [data-testid="stChatInput"] textarea::placeholder {
            color: #64748b !important;
            opacity: 1 !important;
        }
        [data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #dbe4ef;
            padding: 0.75rem;
            border-radius: 12px;
        }
        [data-testid="stMetric"] * {
            color: #0f172a !important;
        }
        [data-testid="stMetricLabel"] {
            color: #475569 !important;
        }
        [data-testid="stMetricValue"] {
            color: #0f172a !important;
        }
        [data-testid="stExpander"] {
            border: 1px solid #dbe4ef !important;
            border-radius: 12px !important;
            background: #ffffff;
        }
        [data-testid="stExpanderDetails"] p,
        [data-testid="stExpanderDetails"] li,
        [data-testid="stExpanderDetails"] label,
        [data-testid="stExpanderDetails"] span {
            color: #1e293b !important;
        }
        [data-testid="stCaptionContainer"] p,
        .stCaption {
            color: #64748b !important;
        }
        .stApp [data-testid="stMarkdownContainer"] p,
        .stApp [data-testid="stMarkdownContainer"] li {
            color: #1e293b;
        }
        [data-testid="stSelectbox"] label {
            color: #334155 !important;
        }
        [data-testid="stSelectbox"] [data-baseweb="select"] > div {
            background: #ffffff !important;
            border: 1px solid #cbd5e1 !important;
            color: #0f172a !important;
            box-shadow: none !important;
        }
        [data-testid="stSelectbox"] [data-baseweb="select"] * {
            color: #0f172a !important;
        }
        [data-testid="stSelectbox"] svg {
            fill: #64748b !important;
        }
        div[role="listbox"] {
            background: #ffffff !important;
            border: 1px solid #cbd5e1 !important;
        }
        div[role="option"] {
            background: #ffffff !important;
            color: #0f172a !important;
        }
        div[role="option"]:hover {
            background: #eff6ff !important;
        }
        div[role="option"][aria-selected="true"] {
            background: #e2e8f0 !important;
            color: #0f172a !important;
        }
        [data-testid="stButton"] button {
            background: #ffffff !important;
            color: #0f172a !important;
            border: 1px solid #cbd5e1 !important;
            box-shadow: none !important;
        }
        [data-testid="stButton"] button:hover {
            background: #eff6ff !important;
            color: #1d4ed8 !important;
            border-color: #93c5fd !important;
        }
        [data-testid="stButton"] button:focus,
        [data-testid="stButton"] button:focus-visible {
            outline: none !important;
            border-color: #60a5fa !important;
            box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2) !important;
        }
        .status-pill {
            display: inline-block;
            padding: 0.35rem 0.7rem;
            border-radius: 999px;
            font-size: 0.82rem;
            font-weight: 600;
            margin-right: 0.5rem;
            margin-bottom: 0.5rem;
        }
        .pill-blue { background: rgba(37, 99, 235, 0.1); color: #1d4ed8; border: 1px solid rgba(37, 99, 235, 0.3); }
        .pill-violet { background: rgba(124, 58, 237, 0.1); color: #6d28d9; border: 1px solid rgba(124, 58, 237, 0.28); }
        .pill-emerald { background: rgba(5, 150, 105, 0.1); color: #047857; border: 1px solid rgba(5, 150, 105, 0.28); }
    </style>
    """,
    unsafe_allow_html=True,
)

header_left, header_right = st.columns([4, 1])
with header_left:
    st.caption("Fast, secure, and transparent pre-qualification experience.")
with header_right:
    if st.button("🔄 Reset Demo", use_container_width=True):
        reset_demo_state()

st.markdown(
    """
    <div class="hero-card">
        <div class="hero-title">🤖 AI Credit Card Assistant</div>
        <div class="hero-sub">Get your pre-qualified credit card offer in under 2 minutes with a smooth, chat-first journey.</div>
    </div>
    <span class="status-pill pill-blue">⚡ Quick 2-Min Application</span>
    <span class="status-pill pill-violet">🎯 Personalized Card Match</span>
    <span class="status-pill pill-emerald">✅ Instant Pre-Qualification</span>
    """,
    unsafe_allow_html=True,
)

# Display conversation
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Don't show input if we already have an offer
if not st.session_state.offer:
    step = st.session_state.step
    data = st.session_state.user_data

    if step == "employment_type":
        profession_options = [
            "Select profession",
            "Salaried",
            "Self-employed",
            "Retired",
            "Student",
            "Homemaker",
            "Others",
        ]
        selected_profession = st.selectbox(
            "Could you please confirm your profession?",
            profession_options,
            key="profession_select",
        )

        if st.button("Continue", key="profession_continue"):
            if selected_profession == "Select profession":
                st.warning("Please select one of the available options so we can proceed.")
            else:
                st.session_state.messages.append({"role": "user", "content": selected_profession})

                if selected_profession == "Others":
                    st.session_state.step = "profession_other"
                    st.session_state.messages.append(
                        {"role": "assistant", "content": "Could you please specify your profession?"}
                    )
                else:
                    data["employment_type"] = selected_profession
                    st.session_state.step = "processing"
                    if selected_profession in ["Retired", "Student", "Homemaker"]:
                        st.session_state.messages.append(
                            {"role": "assistant", "content": INELIGIBLE_PROFESSION_MESSAGE}
                        )
                    else:
                        st.session_state.messages.append(
                            {"role": "assistant", "content": "Thank you. Let me quickly evaluate your eligibility."}
                        )
                st.rerun()

    elif step == "profession_other":
        other_profession = st.text_input("Could you please specify your profession?", key="profession_other_input")
        if st.button("Submit Profession", key="profession_other_submit"):
            profession_text = other_profession.strip()
            if not profession_text:
                st.warning("Please share your profession so we can proceed.")
            else:
                st.session_state.messages.append({"role": "user", "content": profession_text})
                mapped_profession = map_profession(profession_text)

                if mapped_profession == "Unknown":
                    st.session_state.step = "employment_type"
                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": "Just to confirm, are you salaried, self-employed, or in another profession? Please select one of the available options so we can proceed.",
                        }
                    )
                else:
                    data["employment_type"] = mapped_profession
                    st.session_state.step = "processing"
                    if mapped_profession in ["Retired", "Student", "Homemaker"]:
                        st.session_state.messages.append(
                            {"role": "assistant", "content": INELIGIBLE_PROFESSION_MESSAGE}
                        )
                    else:
                        st.session_state.messages.append(
                            {"role": "assistant", "content": "Thank you. Let me quickly evaluate your eligibility."}
                        )
                st.rerun()

    elif step == "ssn":
        if st.session_state.clear_ssn_input_on_next_render:
            st.session_state.ssn_input_value = ""
            st.session_state.clear_ssn_input_on_next_render = False

        input_col, toggle_col = st.columns([5, 1])
        with input_col:
            ssn_input = st.text_input(
                "Please enter your 9-digit SSN (XXX-XX-XXXX or 9 digits).",
                key="ssn_input_value",
                type="default" if st.session_state.show_ssn_input else "password",
                placeholder="XXX-XX-XXXX",
            )
        with toggle_col:
            toggle_label = "🙈" if st.session_state.show_ssn_input else "👁️"
            if st.button(toggle_label, key="ssn_eye_toggle", use_container_width=True):
                st.session_state.show_ssn_input = not st.session_state.show_ssn_input
                st.rerun()

        if st.button("Fetch Credit Score", key="ssn_fetch_button"):
            if not validate_ssn(ssn_input):
                st.warning("Please enter a valid SSN in XXX-XX-XXXX format or as 9 digits.")
            else:
                normalized_ssn = normalize_ssn(ssn_input)
                masked_ssn = mask_ssn(normalized_ssn)

                data["ssn"] = normalized_ssn
                data["ssn_masked"] = masked_ssn
                st.session_state.messages.append({"role": "user", "content": masked_ssn})

                with st.spinner("Fetching credit report..."):
                    lookup_result = fetch_credit_score_by_ssn(normalized_ssn)

                if lookup_result.get("ok"):
                    data["credit_score"] = int(lookup_result.get("credit_score", 600))
                    st.session_state.step = "employment_type"
                    st.session_state.clear_ssn_input_on_next_render = True
                    st.session_state.show_ssn_input = False

                    visible_ssn = lookup_result.get("ssn_masked", masked_ssn)
                    if lookup_result.get("record_found"):
                        reply = (
                            f"Credit report fetched for SSN {visible_ssn}. "
                            f"Your bureau score is {data['credit_score']}. "
                            "Could you please confirm your profession?"
                        )
                    else:
                        reply = (
                            f"No credit record found for SSN {visible_ssn}. "
                            f"Using fallback score {data['credit_score']} for pre-qualification. "
                            "Could you please confirm your profession?"
                        )
                else:
                    reply = "Unable to fetch your credit report right now. Please try your SSN again."

                st.session_state.messages.append({"role": "assistant", "content": reply})
                st.rerun()

    elif step == "processing":
        st.caption("Processing your application. Please wait...")

    else:
        user_input = st.chat_input("Type your response...")

        if user_input:
            st.session_state.messages.append({"role": "user", "content": user_input})
            reply = None

            if step == "name":
                if validate_name(user_input):
                    data["name"] = normalize_name_candidate(user_input)
                    st.session_state.step = "mobile"
                    reply = f"Thanks {data['name']}! Now, enter your 10-digit mobile number."
                else:
                    reply = "Manager mode on 😄 Nice opener, but I need your proper full name to start the application (for example: Rushika Jain)."

            elif step == "mobile":
                if validate_mobile(user_input):
                    data["mobile"] = user_input
                    st.session_state.step = "email"
                    reply = "Great. What is your email address?"
                else:
                    reply = "Mobile number must be exactly 10 digits."

            elif step == "email":
                if validate_email(user_input):
                    data["email"] = user_input
                    st.session_state.step = "address"
                    reply = "Please share your current residential address."
                else:
                    reply = "Please enter a valid email."

            elif step == "address":
                if validate_address(user_input):
                    data["address"] = user_input.strip()
                    st.session_state.step = "dob"
                    reply = "Please enter your Date of Birth (YYYY-MM-DD)."
                else:
                    reply = "Please enter a complete address (at least 8 characters)."

            elif step == "dob":
                if validate_dob(user_input):
                    normalized_dob = datetime.strptime(user_input.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
                    data["dob"] = normalized_dob
                    st.session_state.step = "income"
                    st.session_state.income_invalid_attempts = 0
                    reply = "What is your monthly income?"
                else:
                    reply = "Use format YYYY-MM-DD (e.g. 1998-05-12)."

            elif step == "income":
                parsed_income = parse_income(user_input)
                if parsed_income is not None:
                    data["income"] = parsed_income
                    st.session_state.step = "ssn"
                    st.session_state.income_invalid_attempts = 0
                    reply = "Almost done! Please enter your 9-digit SSN (XXX-XX-XXXX or 9 digits)."
                else:
                    st.session_state.income_invalid_attempts += 1
                    if st.session_state.income_invalid_attempts == 1:
                        reply = "That’s great to hear 😊 However, to proceed with your application, we’ll need your exact monthly income in numbers. Could you please share the amount?"
                    else:
                        reply = "Please enter your monthly income in numbers (for example: 75000)."

            if reply:
                st.session_state.messages.append({"role": "assistant", "content": reply})
                st.rerun()

# ---------------------------
# ELIGIBILITY PROCESSING
# ---------------------------
if st.session_state.step == "processing" and not st.session_state.offer:
    with st.spinner("Connecting to underwriting server..."):
        try:
            user_data = st.session_state.user_data

            if user_data.get("employment_type") in ["Retired", "Student", "Homemaker"]:
                st.session_state.offer = {
                    "status": "rejected",
                    "reason": INELIGIBLE_PROFESSION_MESSAGE,
                    "decision_explanation": INELIGIBLE_PROFESSION_MESSAGE,
                }
                st.session_state.explanation_data = None
                st.rerun()

            # 1. Start App
            start_resp = requests.post(f"{BACKEND_URL}/start", params={
                "name": user_data["name"], "mobile": user_data["mobile"], "email": user_data["email"]
            }, timeout=30)

            if not start_resp.ok:
                backend_detail = ""
                try:
                    payload = start_resp.json()
                    backend_detail = payload.get("detail") if isinstance(payload, dict) else ""
                except Exception:
                    backend_detail = ""
                if backend_detail:
                    st.error(f"Could not start application: {backend_detail}")
                else:
                    st.error("Could not start application. Please try again.")
                st.stop()

            st.session_state.application_id = start_resp.json().get("application_id")

            if not st.session_state.application_id:
                st.error("Application ID was not returned by backend.")
                st.stop()

            # 2. Submit Details
            submit_resp = requests.post(f"{BACKEND_URL}/submit-details", params={
                "application_id": st.session_state.application_id,
                "dob": user_data["dob"],
                "monthly_income": user_data["income"],
                "credit_score": user_data["credit_score"],
                "employment_type": user_data["employment_type"],
                "ssn_masked": user_data.get("ssn_masked", "")
            }, timeout=30)

            if not submit_resp.ok:
                if user_data.get("employment_type") in ["Retired", "Student", "Homemaker"]:
                    st.session_state.offer = {
                        "status": "rejected",
                        "reason": INELIGIBLE_PROFESSION_MESSAGE,
                        "decision_explanation": INELIGIBLE_PROFESSION_MESSAGE,
                    }
                    st.session_state.explanation_data = None
                    st.rerun()

                backend_detail = ""
                try:
                    payload = submit_resp.json()
                    backend_detail = payload.get("detail") if isinstance(payload, dict) else ""
                except Exception:
                    backend_detail = ""

                if backend_detail:
                    st.error(f"Could not submit details: {backend_detail}")
                else:
                    st.error("Could not submit details. Please check backend and retry.")
                st.stop()

            st.session_state.offer = submit_resp.json()
            st.session_state.explanation_data = None
            st.rerun()
        except Exception:
            st.error("Backend Connection Error. Is your Uvicorn server running?")

# ---------------------------
# PREMIUM UI DECISION
# ---------------------------
if st.session_state.offer:
    offer = st.session_state.offer

    if offer.get("status") == "eligible":
        st.info("This is a pre-qualified offer. Final approval is subject to identity and income verification.")
        st.balloons()
        with st.container(border=True):
            st.success(f"### 🎉 Great news, {st.session_state.user_data['name']}!")
            col1, col2 = st.columns([1.55, 1])
            with col1:
                render_card_preview(
                    customer_name=st.session_state.user_data.get("name", "Card Holder"),
                    card_type=offer.get("card_type", "Standard"),
                )
            with col2:
                col2.metric("Pre-qualified Tier", offer.get("card_type"))
                col2.metric("Credit Limit", f"${offer.get('credit_limit', 0):,.0f}")
            st.caption("Status: Pre-qualified · Final review pending identity and income verification")

            with st.expander("✨ View AI Eligibility Analysis", expanded=False):
                st.caption("This system does not provide financial advisory services.")
                query_text = st.text_input(
                    "Ask a policy-grounded question (optional)",
                    value=st.session_state.explanation_query,
                    key="explanation_query_input",
                )
                st.session_state.explanation_query = query_text

                if st.session_state.explanation_data is None or st.button("Regenerate grounded explanation"):
                    st.session_state.explanation_data = generate_ai_explanation(
                        st.session_state.application_id,
                        st.session_state.explanation_query,
                    )

                st.info(st.session_state.explanation_data.get("explanation_text", "No explanation available."))

                if st.session_state.explanation_data.get("retrieved_chunks"):
                    with st.expander("Retrieval audit trace", expanded=False):
                        chunks = st.session_state.explanation_data.get("retrieved_chunks", [])
                        scores = st.session_state.explanation_data.get("similarity_scores", [])
                        for index, chunk in enumerate(chunks):
                            score = scores[index] if index < len(scores) else "N/A"
                            st.write(f"Chunk {index + 1} (score={score}): {chunk}")

            if st.button("Confirm and Accept Card"):
                celebrate_success()
                st.success(f"✅ Application `{st.session_state.application_id}` pending final review!")
                st.info("Congratulations! Your digital card request is being processed.")
                st.markdown(
                    """
                    <div style="
                        background: #eef6ff;
                        border: 1px solid #bfdbfe;
                        color: #1e3a8a;
                        padding: 0.9rem 1rem;
                        border-radius: 0.6rem;
                        margin-top: 0.35rem;
                        line-height: 1.5;
                    ">
                        <strong>Next Step:</strong> A SMS and EMail link will be shared for providing your documents for verification.<br/>
                        Final approval is subject to credit team approval post document verification.<br/><br/>
                        <strong>Documents needed:</strong><br/>
                        1. ID proof<br/>
                        2. Income proof<br/>
                        3. Address proof
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                
    else:
        st.error("### ⚠️ Application Update")
        reason_text = html.escape(str(offer.get("decision_explanation", "Does not meet minimum requirements.")))
        st.markdown(
            f"""
            <div style="
                background: #fff8db;
                border: 1px solid #fde68a;
                color: #7c2d12;
                padding: 0.85rem 1rem;
                border-radius: 0.6rem;
                font-weight: 600;
                margin-bottom: 0.35rem;
            ">
                ⚠️ <strong>Reason:</strong> {reason_text}
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.expander("✨ View AI Eligibility Analysis", expanded=False):
            st.caption("This system does not provide financial advisory services.")
            if st.session_state.explanation_data is None:
                st.session_state.explanation_data = generate_ai_explanation(
                    st.session_state.application_id,
                    "Explain the rejection reason and compliant improvement suggestions.",
                )
            st.info(st.session_state.explanation_data.get("explanation_text", "No explanation available."))

        if st.button("Start Over"):
            st.session_state.clear()
            st.rerun()

bottom_anchor = st.empty()
bottom_anchor.markdown("<div id='chat-bottom-anchor' style='height:1px;'></div>", unsafe_allow_html=True)

if "_scroll_cycle" not in st.session_state:
    st.session_state._scroll_cycle = 0
st.session_state._scroll_cycle += 1

auto_scroll_to_latest_message(
    f"{len(st.session_state.messages)}-{st.session_state.step}-{1 if st.session_state.offer else 0}-{st.session_state._scroll_cycle}"
)
