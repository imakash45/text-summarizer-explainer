# ============================================================
# app.py
# Multilingual Text Summarizer & Explainer — Groq-powered
#
# Summarize tab : compress text, preserve central theme
# Explain tab    : expand text, strictly grounded in the source
#                  (no general knowledge added — avoids hallucination)
#
# No manual length targeting — the AI judges appropriate length
# for each piece of text on its own.
# ============================================================

import os
import re

import streamlit as st
from dotenv import load_dotenv
from groq import Groq, RateLimitError, APIError

load_dotenv()

st.set_page_config(page_title="Text Summarizer & Explainer", page_icon="📝", layout="wide")

GROQ_MODEL      = "llama-3.1-8b-instant"
MAX_INPUT_WORDS = 2200   # keeps requests safely under the free-tier TPM limit

# ── Dark theme ─────────────────────────────────────────────────────────────────

st.markdown("""
    <style>
        .stApp { background-color: #0d0f1a; }
        h1, h2, h3, h4, p, span, label, li { color: #e5e5e5; }
        .stTextArea textarea {
            background-color: #14172a;
            color: #e5e5e5;
            border: 1px solid #2a2e45;
        }
        .stTextArea textarea::placeholder {
            color: #7a7f9e;
            opacity: 1;
        }
        .stButton>button {
            background-color: #7c6af7;
            color: white;
            border: none;
            font-weight: 600;
        }
        .stButton>button:hover { background-color: #00d4ff; color: #0d0f1a; }
        .result-card {
            background-color: #14172a;
            border: 1px solid #2a2e45;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 16px;
        }
        .theme-box {
            background: linear-gradient(135deg, #7c6af7 0%, #00d4ff 100%);
            padding: 16px 20px;
            border-radius: 10px;
            color: #0d0f1a;
            font-weight: 600;
            font-size: 1.1em;
        }
        div[data-baseweb="tab-list"],
        div[role="tablist"] {
            justify-content: center !important;
            display: flex !important;
            width: 100% !important;
        }
        .stTabs {
            display: flex;
            justify-content: center;
        }
    </style>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def count_words(text: str) -> int:
    return len(text.split())


def count_chars(text: str) -> int:
    return len(text)


def call_groq(system_prompt: str, user_prompt: str, max_tokens: int):
    """Single Groq call. Returns (text, error) — error is None on success."""
    api_key = os.environ.get("GROQ_API_KEY") or st.secrets.get("GROQ_API_KEY")
    if not api_key:
        return None, "GROQ_API_KEY not found. Check your .env file or Streamlit secrets."

    client = Groq(api_key=api_key)
    try:
        response = client.chat.completions.create(
            model    = GROQ_MODEL,
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            max_tokens  = max_tokens,
            temperature = 0.3,
        )
        return response.choices[0].message.content.strip(), None
    except RateLimitError:
        return None, "Rate limit reached — please wait a moment and try again."
    except APIError as e:
        return None, f"API error: {e}"
    except Exception as e:
        return None, f"Unexpected error: {e}"


def parse_theme_and_summary(raw: str) -> dict:
    """
    Parse THEME + SUMMARY out of a Groq response.

    Does NOT rely solely on a literal "SUMMARY:" label being present —
    the model doesn't always include it consistently. Instead: extract
    THEME's content up to the first paragraph break, then treat
    everything after that break as the summary.
    """
    cleaned = re.sub(r"[#*]+\s*(THEME|SUMMARY)\s*:\s*[#*]*", r"\1:", raw, flags=re.IGNORECASE)

    theme_match = re.search(r"THEME:\s*(.*?)(?:\n\s*\n|\n\s*SUMMARY:|\Z)", cleaned, re.DOTALL | re.IGNORECASE)
    theme = theme_match.group(1).strip() if theme_match else ""

    if theme_match:
        remainder = cleaned[theme_match.end():].strip()
    else:
        remainder = cleaned.strip()

    remainder = re.sub(r"^SUMMARY:\s*", "", remainder, flags=re.IGNORECASE)

    if "THEME:" in remainder.upper():
        remainder = re.split(r"THEME:", remainder, flags=re.IGNORECASE)[0].strip()

    summary = remainder.strip()

    if not theme and not summary:
        summary = raw
    elif not summary:
        summary = theme
        theme   = ""

    return {"theme": theme or "Not identified", "summary": summary}


# ── Summarize tab ──────────────────────────────────────────────────────────────

def render_summarize_tab():
    text_input = st.text_area("Paste your text here", height=220, key="sum_text",
                                placeholder="Paste an article, essay, or any text in any language...")

    original_words = count_words(text_input)

    col_left, col_center, col_right = st.columns([1, 1, 1])
    with col_center:
        generate = st.button("✨ Summarize", type="primary", key="sum_btn", use_container_width=True)

    if generate:
        if original_words < 20:
            st.warning("Please paste at least ~20 words for a meaningful summary.")
            return

        words = text_input.split()
        clipped_input = " ".join(words[:MAX_INPUT_WORDS]) if len(words) > MAX_INPUT_WORDS else text_input

        length_instruction = (
            "Use your own judgment to determine the ideal concise length for this specific "
            "text — capture the essential points without unnecessary length. It must be "
            f"clearly shorter than the original ({original_words} words)."
        )

        system_prompt = (
            "You are an expert multilingual summarizer. You identify the TRUE "
            "CENTRAL THEME of a text and produce a summary that preserves that "
            "theme without losing the main argument or purpose. You respond in "
            "the SAME LANGUAGE as the input text."
        )
        user_prompt = f"""Analyze the following text and respond in EXACTLY this format:

THEME: <one sentence capturing the central theme — the main argument or purpose>
SUMMARY: <the summary itself>

Rules for the SUMMARY:
- {length_instruction}
- Mention each key concept ONLY ONCE — do not restate the same point in different words.
- Combine related ideas into single sentences rather than explaining each separately.
- Remove supporting examples and minor details — keep only essential claims.
- Write as ONE natural, flowing paragraph. No sub-headings, no bullet points.
- Respond in the same language as the text below.

Text to analyze:
{clipped_input}"""

        with st.spinner("Summarizing..."):
            raw, error = call_groq(system_prompt, user_prompt, max_tokens=700)

        if error:
            st.error(error)
            return

        result  = parse_theme_and_summary(raw)
        summary = result["summary"]

        st.divider()
        st.markdown(f'<div class="theme-box">🎯 Central Theme<br>{result["theme"]}</div>', unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="result-card">', unsafe_allow_html=True)
        st.markdown("**Summary**")
        st.write(summary)
        st.markdown('</div>', unsafe_allow_html=True)
        st.caption(f"Original: {original_words} words · {count_chars(text_input)} characters  →  "
                    f"Summary: {count_words(summary)} words · {count_chars(summary)} characters")


# ── Explain tab ────────────────────────────────────────────────────────────────

def render_explain_tab():
    text_input = st.text_area("Paste text to explain", height=220, key="exp_text",
                                placeholder="Paste a concept, term, or brief passage to get an expanded explanation...")

    original_words = count_words(text_input)

    col_left, col_center, col_right = st.columns([1, 1, 1])
    with col_center:
        generate = st.button("💡 Explain", type="primary", key="exp_btn", use_container_width=True)

    if generate:
        if original_words < 3:
            st.warning("Please paste some text to explain.")
            return

        length_instruction = "Use your own judgment for the ideal length to fully explain the content clearly."

        system_prompt = (
            "You are an expert explainer. Your job is to expand and clarify text "
            "by elaborating ONLY on what is stated or directly implied in the "
            "source text. You NEVER add general knowledge, facts, or claims that "
            "are not present in or directly inferable from the source text — "
            "if you are unsure whether something is supported by the source, "
            "leave it out. You respond in the SAME LANGUAGE as the input text."
        )
        user_prompt = f"""Expand and explain the following text in more detail, based STRICTLY on what it contains.

Rules:
- {length_instruction}
- Only elaborate on ideas, terms, or claims already present in the text below.
- Do NOT add outside facts, dates, statistics, or claims not stated in the source.
- Clarify and unpack existing points — do not introduce new ones.
- Write as clear, natural prose.
- Respond in the same language as the text below.

Text to explain:
{text_input}"""

        with st.spinner("Explaining..."):
            raw, error = call_groq(system_prompt, user_prompt, max_tokens=900)

        if error:
            st.error(error)
            return

        explanation = raw

        st.divider()
        st.markdown('<div class="result-card">', unsafe_allow_html=True)
        st.markdown("**Explanation**")
        st.write(explanation)
        st.markdown('</div>', unsafe_allow_html=True)
        st.caption(f"Original: {original_words} words · {count_chars(text_input)} characters  →  "
                    f"Explanation: {count_words(explanation)} words · {count_chars(explanation)} characters")


# ── Main ───────────────────────────────────────────────────────────────────────

st.title("📝 Text Summarizer & Explainer")
st.caption("Multilingual — works in any language, responds in the same language as your input.")

tab_summarize, tab_explain = st.tabs(["📉 Summarize", "📈 Explain"])

with tab_summarize:
    render_summarize_tab()

with tab_explain:
    render_explain_tab()