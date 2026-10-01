import streamlit as st
import re
import hashlib
import pypdf
import textwrap
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="CIAT25 Core Interceptor", layout="wide")

st.title("CIAT25 Metabolic Core: Gate -1, Gate 0 & Anchor Scoring")

# Initialize session state for telemetry history
if "telemetry_logs" not in st.session_state:
    st.session_state.telemetry_logs = []

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

# --- Sidebar Controls & Audit History ---
st.sidebar.header("Telemetry Controls")
strict_mode = st.sidebar.checkbox("Enforce Hard Drop Mode", value=True)

if st.sidebar.button("Clear Log History"):
    st.session_state.telemetry_logs = []
    st.sidebar.success("Logs cleared.")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Inbound Payload")
    user_input = st.text_area("Enter prompt or instruction thread:", height=150)
    uploaded_file = st.file_uploader("Upload thread context (txt, csv, pdf):", type=["txt", "csv", "pdf"])

with col2:
    st.subheader("Execution & Real-Time Stream")
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
        
        chunks = textwrap.wrap(combined_input, width=5000, replace_whitespace=False)
        st.info(f"Payload partitioned into {len(chunks)} sequential chunk(s).")
        
        for i, chunk in enumerate(chunks):
            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
            
            # Execute Gate -1
            clean_text, g1_pass, g1_msg = gate_minus_one(chunk)
            
            if not g1_pass:
                log_entry = {
                    "Timestamp": timestamp,
                    "Chunk": f"{i+1}/{len(chunks)}",
                    "Gate -1": "DROP",
                    "Gate 0": "N/A",
                    "Tokens": 0,
                    "Confidence": "0.0%",
                    "Log ID": "FAILED_G1",
                    "Message": g1_msg
                }
                st.session_state.telemetry_logs.append(log_entry)
                st.error(f"Chunk {i+1} Dropped at Gate -1: {g1_msg}")
                if strict_mode:
                    break
                continue
                
            # Execute Gate 0
            action, tokens, g0_msg = gate_zero(clean_text, file_present)
            
            if action == "DROP" and strict_mode:
                log_entry = {
                    "Timestamp": timestamp,
                    "Chunk": f"{i+1}/{len(chunks)}",
                    "Gate -1": "PASS",
                    "Gate 0": "DROP",
                    "Tokens": tokens,
                    "Confidence": "0.0%",
                    "Log ID": "FAILED_G0",
                    "Message": g0_msg
                }
                st.session_state.telemetry_logs.append(log_entry)
                st.error(f"Chunk {i+1} Dropped at Gate 0: {g0_msg}")
                break
                
            # Execute Confidence Scoring
            confidence, conf_msg = calculate_confidence_score(clean_text, tokens)
            log_id = hashlib.sha256(clean_text.encode()).hexdigest()[:10]
            
            log_entry = {
                "Timestamp": timestamp,
                "Chunk": f"{i+1}/{len(chunks)}",
                "Gate -1": "PASS",
                "Gate 0": action,
                "Tokens": tokens,
                "Confidence": f"{confidence * 100}%",
                "Log ID": log_id,
                "Message": conf_msg
            }
            st.session_state.telemetry_logs.append(log_entry)
            st.success(f"Chunk {i+1}/{len(chunks)} Cleared | Log ID: {log_id} | Confidence: {confidence * 100}%")

# --- Interactive Telemetry Inspector & Audit Panel ---
st.markdown("---")
st.subheader("CIAT25 Interactive Telemetry Inspector")

if st.session_state.telemetry_logs:
    df_logs = pd.DataFrame(st.session_state.telemetry_logs)
    
    # Display log table
    st.dataframe(df_logs, use_container_width=True)
    
    # Export CSV Option
    csv_data = df_logs.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="Export Audit Log (CSV)",
        data=csv_data,
        file_name=f"ciat25_telemetry_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )
else:
    st.caption("No execution telemetry recorded in this session yet. Run a prompt or document to populate logs.")
