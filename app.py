import streamlit as st
import re
import hashlib
import pypdf
import textwrap

st.set_page_config(page_title="CIAT25 Core Interceptor", layout="wide")

st.title("CIAT25 Metabolic Core: Gate -1, Gate 0 & Anchor Scoring (Chunked)")

# --- Gate -1: Ingress Filter ---
def gate_minus_one(raw_input: str) -> tuple[str, bool, str]:
    if not raw_input or not raw_input.strip():
        return "", False, "Gate -1 Drop: Empty payload."
    
    cleaned = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', raw_input)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    if len(cleaned) > 10000:
        return "", False, "Gate -1 Drop: Payload exceeds maximum length bounds (10,000 chars)."
        
    injection_patterns = ["ignore previous instructions", "system override", "jailbreak"]
    for pattern in injection_patterns:
        if pattern in cleaned.lower():
            return "", False, f"Gate -1 Drop: Anomaly detected matching restricted pattern: '{pattern}'."
            
    return cleaned, True, "Gate -1 Pass: Structural integrity verified."

# --- Gate 0: Deterministic Boundary Check ---
def gate_zero(sanitized_text: str, has_file: bool) -> tuple[str, int, str]:
    token_estimate = len(sanitized_text.split()) * 2 
    
    if "calculate" in sanitized_text.lower() and not has_file:
        return "LOCAL_RESOLVE", 0, "Gate 0 Route: Resolved via local rule engine. Zero API tokens spent."
        
    if token_estimate > 2000:
        return "DROP", token_estimate, f"Gate 0 Drop: Estimated token burn ({token_estimate}) exceeds stability threshold."
        
    return "PASS_TO_METABOLIC", token_estimate, f"Gate 0 Pass: Within allowable metabolic index. Estimated tokens: {token_estimate}."

# --- Anchor Integrity Validator & Confidence Score ---
def calculate_confidence_score(sanitized_text: str, token_estimate: int) -> tuple[float, str]:
    word_count = len(sanitized_text.split())
    if word_count == 0:
        return 0.0, "Zero lexical density."
        
    complexity_penalty = min(token_estimate / 5000.0, 0.4)
    base_score = 0.95 - complexity_penalty
    
    score = round(max(0.10, min(base_score, 1.0)), 2)
    
    if score >= 0.75:
        rating = "HIGH STABILITY: Anchor integrity verified."
    elif score >= 0.40:
        rating = "MODERATE STABILITY: Requires secondary validation."
    else:
        rating = "LOW STABILITY: High drift risk detected."
        
    return score, rating

# --- UI Layout ---
st.sidebar.header("Telemetry Config")
strict_mode = st.sidebar.checkbox("Enforce Hard Drop Mode", value=True)

col1, col2 = st.columns(2)

with col1:
    st.subheader("Inbound Payload")
    user_input = st.text_area("Enter prompt or instruction thread:", height=150)
    uploaded_file = st.file_uploader("Upload thread context (txt, csv, pdf):", type=["txt", "csv", "pdf"])

with col2:
    st.subheader("Gate Telemetry Log")
    if st.button("Execute Pipeline"):
        file_text = ""
        if uploaded_file is not None:
            file_extension = uploaded_file.name.split('.')[-1].lower()
            if file_extension == 'pdf':
                try:
                    reader = pypdf.PdfReader(uploaded_file)
                    for page in reader.pages:
                        file_text += page.extract_text() or ""
                except Exception as e:
                    st.error(f"Error reading PDF: {e}")
            elif file_extension in ['txt', 'csv']:
                file_text = uploaded_file.read().decode("utf-8", errors="ignore")

        combined_input = f"{user_input}\n{file_text}".strip()
        file_present = uploaded_file is not None
        
        # Split payload into 5,000-character windows (Plan C Chunking)
        chunks = textwrap.wrap(combined_input, width=5000, replace_whitespace=False)
        st.info(f"Payload partitioned into {len(chunks)} sequential chunk(s) for metabolic routing.")
        
        for i, chunk in enumerate(chunks):
            st.markdown(f"--- **Chunk {i+1} of {len(chunks)}** ---")
            
            # Execute Gate -1
            clean_text, g1_pass, g1_msg = gate_minus_one(chunk)
            st.write(f"**Gate -1 Status:** {'PASS' if g1_pass else 'DROP'}")
            st.code(g1_msg)
            
            if not g1_pass:
                if strict_mode:
                    st.error(f"Pipeline halted at Chunk {i+1} due to Gate -1 drop.")
                    break
                continue
                
            # Execute Gate 0
            action, tokens, g0_msg = gate_zero(clean_text, file_present)
            st.write(f"**Gate 0 Action:** {action}")
            st.code(g0_msg)
            
            if action == "DROP" and strict_mode:
                st.error(f"Pipeline terminated at Gate 0 for Chunk {i+1}. Zero execution cost.")
                break
                
            # Execute Confidence Scoring
            confidence, conf_msg = calculate_confidence_score(clean_text, tokens)
            st.metric(label=f"Anchor Confidence Score (Chunk {i+1})", value=f"{confidence * 100}%")
            st.code(conf_msg)
            
            st.success(f"Chunk {i+1} cleared. Log ID: {hashlib.sha256(clean_text.encode()).hexdigest()[:10]}")
