import streamlit as st
import re
import hashlib
import pypdf
import numpy as np
import pandas as pd
from datetime import datetime
from sentence_transformers import SentenceTransformer

st.set_page_config(page_title="CIAT25 Core Interceptor", layout="wide")

st.title("CIAT25 Metabolic Core: Gate -1, Gate 0 & Gate 1 Engine")

# Load SentenceTransformer model with Streamlit caching
@st.cache_resource
def load_embedding_model():
    return SentenceTransformer("all-MiniLM-L6-v2")

model = load_embedding_model()

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

# --- Gate 0: Trajectory Sensor (Semantic Cosine Similarity) ---
def gate_zero(query_text: str, anchor_embeddings: list[np.ndarray], threshold: float = 0.25) -> tuple[str, float, str]:
    if not anchor_embeddings:
        return "DROP", 0.0, "Gate 0 Drop: Active anchor corpus is empty."
    
    query_vector = model.encode(query_text, convert_to_numpy=True)
    
    scores = [
        np.dot(query_vector, a_vec) / (np.linalg.norm(query_vector) * np.linalg.norm(a_vec))
        for a_vec in anchor_embeddings
    ]
    best_score = float(max(scores)) if scores else 0.0
    
    if best_score < threshold:
        return "DROP", best_score, f"Gate 0 Drop: Trajectory similarity ({best_score:.4f}) below threshold ({threshold}). Zero LLM tokens consumed."
        
    return "PASS_TO_METABOLIC", best_score, f"Gate 0 Pass: Trajectory aligned. Max cosine similarity: {best_score:.4f}."

# --- Gate 1: Anchor Confidence Engine (Atomic Claims & Soft-Min) ---
class Gate1AnchorConfidenceEngine:
    def __init__(self, beta: float = 10.0, min_claim_threshold: float = 0.82):
        self.beta = beta  # Sharpness factor for Soft-Min pessimistic weighting
        self.min_claim_threshold = min_claim_threshold

    def _cosine_similarity(self, v1: np.ndarray, v2: np.ndarray) -> float:
        return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))

    def compute_anchor_confidence(
        self, 
        claim_embeddings: list[np.ndarray], 
        anchor_embeddings: list[np.ndarray]
    ) -> dict:
        if not claim_embeddings or not anchor_embeddings:
            return {"confidence_score": 0.0, "verdict": "ANCHOR_VOID", "reason": "EMPTY_INPUTS"}

        claim_scores = []
        for c_vec in claim_embeddings:
            best_match = max([self._cosine_similarity(c_vec, a_vec) for a_vec in anchor_embeddings])
            claim_scores.append(best_match)

        claim_scores_arr = np.array(claim_scores)

        # Pessimistic Soft-Min Aggregation to prevent dilution bias
        soft_min_score = - (1.0 / self.beta) * np.log(
            np.mean(np.exp(-self.beta * claim_scores_arr))
        )

        final_confidence = round(float(soft_min_score), 4)
        verdict = "PASS" if final_confidence >= self.min_claim_threshold else "ANCHOR_VOID"

        return {
            "confidence_score": final_confidence,
            "metrics": {
                "soft_min_cosine": round(float(soft_min_score), 4),
                "min_claim_score": round(float(np.min(claim_scores_arr)), 4),
                "max_claim_score": round(float(np.max(claim_scores_arr)), 4),
            },
            "verdict": verdict
        }

# --- Sidebar Controls & Audit History ---
st.sidebar.header("Telemetry Controls")
strict_mode = st.sidebar.checkbox("Enforce Hard Drop Mode", value=True)
g0_threshold = st.sidebar.slider("Gate 0 Similarity Threshold", min_value=0.05, max_value=0.60, value=0.25, step=0.05)
g1_threshold = st.sidebar.slider("Gate 1 Claim Threshold", min_value=0.50, max_value=0.95, value=0.82, step=0.01)

if st.sidebar.button("Clear Log History"):
    st.session_state.telemetry_logs = []
    st.sidebar.success("Logs cleared.")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Inbound Payload & Anchor Source")
    user_input = st.text_area("Enter query prompt or simulated output:", height=150)
    uploaded_file = st.file_uploader("Upload reference anchor document (txt, csv, pdf):", type=["txt", "csv", "pdf"])

with col2:
    st.subheader("Execution & Real-Time Stream")
    if st.button("Execute Pipeline"):
        anchor_texts = []
        if uploaded_file is not None:
            file_extension = uploaded_file.name.split('.')[-1].lower()
            file_text = ""
            if file_extension == 'pdf':
                try:
                    reader = pypdf.PdfReader(uploaded_file)
                    for page in reader.pages:
                        file_text += page.extract_text() or ""
                except Exception as e:
                    st.error(f"Error reading PDF: {e}")
            elif file_extension in ['txt', 'csv']:
                file_text = uploaded_file.read().decode("utf-8", errors="ignore")
            
            if file_text:
                anchor_texts = [chunk.strip() for chunk in file_text.split("\n\n") if chunk.strip()]
                if not anchor_texts:
                    anchor_texts = [file_text]
        
        if not anchor_texts:
            anchor_texts = [
                "CIAT25 governance architecture, AI pipeline validation, token telemetry, and gate protocols.",
                "Semantic cosine similarity, anchor chunks, trajectory sensor, and pre-generation filtering.",
                "PostgreSQL pgvector, vector embeddings, anomaly detection, AI debt, and beautiful lie mitigation."
            ]
        
        anchor_embeddings = [model.encode(chunk, convert_to_numpy=True) for chunk in anchor_texts]
        st.info(f"Loaded active anchor corpus with {len(anchor_embeddings)} reference chunk(s).")
        
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # 1. Execute Gate -1
        clean_text, g1_pass, g1_msg = gate_minus_one(user_input)
        
        if not g1_pass:
            log_entry = {
                "Timestamp": timestamp,
                "Gate -1": "DROP",
                "Gate 0": "N/A",
                "Gate 1 Verdict": "N/A",
                "Score": 0.0,
                "Message": g1_msg
            }
            st.session_state.telemetry_logs.append(log_entry)
            st.error(f"Payload Dropped at Gate -1: {g1_msg}")
        else:
            # 2. Execute Gate 0 Trajectory Sensor
            action, sim_score, g0_msg = gate_zero(clean_text, anchor_embeddings, threshold=g0_threshold)
            
            if action == "DROP" and strict_mode:
                log_entry = {
                    "Timestamp": timestamp,
                    "Gate -1": "PASS",
                    "Gate 0": "DROP",
                    "Gate 1 Verdict": "N/A",
                    "Score": round(sim_score, 4),
                    "Message": g0_msg
                }
                st.session_state.telemetry_logs.append(log_entry)
                st.error(f"Payload Dropped at Gate 0: {g0_msg}")
            else:
                # 3. Execute Gate 1 Anchor Confidence Engine
                claim_sentences = [s.strip() for s in clean_text.split('.') if s.strip()]
                if not claim_sentences:
                    claim_sentences = [clean_text]
                
                claim_embeddings = [model.encode(claim, convert_to_numpy=True) for claim in claim_sentences]
                
                g1_engine = Gate1AnchorConfidenceEngine(min_claim_threshold=g1_threshold)
                g1_result = g1_engine.compute_anchor_confidence(claim_embeddings, anchor_embeddings)
                
                log_id = hashlib.sha256(clean_text.encode()).hexdigest()[:10]
                log_entry = {
                    "Timestamp": timestamp,
                    "Gate -1": "PASS",
                    "Gate 0": action,
                    "Gate 1 Verdict": g1_result["verdict"],
                    "Score": g1_result["confidence_score"],
                    "Message": f"Log ID: {log_id} | Soft-Min: {g1_result['metrics']['soft_min_cosine']}"
                }
                st.session_state.telemetry_logs.append(log_entry)
                
                if g1_result["verdict"] == "PASS":
                    st.success(f"Pipeline Cleared | Log ID: {log_id} | Gate 1 Confidence: {g1_result['confidence_score']}")
                else:
                    st.error(f"Gate 1 Anchor Void Triggered | Log ID: {log_id} | Confidence: {g1_result['confidence_score']}")

# --- Interactive Telemetry Inspector & Audit Panel ---
st.markdown("---")
st.subheader("CIAT25 Interactive Telemetry Inspector")

if st.session_state.telemetry_logs:
    df_logs = pd.DataFrame(st.session_state.telemetry_logs)
    st.dataframe(df_logs, use_container_width=True)
    
    csv_data = df_logs.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="Export Audit Log (CSV)",
        data=csv_data,
        file_name=f"ciat25_telemetry_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )
else:
    st.caption("No execution telemetry recorded in this session yet. Run a prompt or document to populate logs.")
