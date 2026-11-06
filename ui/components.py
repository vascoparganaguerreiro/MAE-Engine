# ui/components.py
import streamlit as st
from models.telemetry_schema import MetricValue

def render_metric_field(label: str, metric: MetricValue, allow_manual: bool = True):
    """Renders a single physiological metric with source attribution or a clear empty state."""
    with st.container(border=True):
        if metric.is_available:
            st.caption(f"**{label}**")
            st.markdown(f"### {metric.value} {metric.unit}")
            
            # Traceability & Coverage metadata
            ts_str = metric.timestamp.strftime("%d %b, %H:%M") if metric.timestamp else "N/A"
            st.caption(f"📍 **Source:** {metric.source} | 🕒 {ts_str}")
            if metric.baseline:
                st.caption(f"📊 **Baseline:** {metric.baseline} {metric.unit}")
        else:
            st.caption(f"**{label}**")
            st.warning("⚠️ Not recorded", icon="❌")
            if allow_manual:
                with st.popover(f"Import / Enter {label}"):
                    val = st.number_input(f"Enter {label} ({metric.unit})", key=f"manual_{label}")
                    if st.button("Save Entry", key=f"btn_{label}"):
                        # Update state and refresh
                        st.rerun()
