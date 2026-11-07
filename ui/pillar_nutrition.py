from __future__ import annotations

from html import escape
import streamlit as st
import data_store as store
from models.telemetry_schema import MetricValue
from ui.components import render_metric_field


def render_nutrition_habits_layer(lang: str = "EN"):
    is_pt = (lang == "PT")
    
    st.markdown("---")
    st.markdown("## Fuel, Hydrate & Recover (Cross-Pillar Layer)" if not is_pt else "## Nutrição, Hidratação & Hábitos (Camada Transversal)")
    st.caption("Contextual Workout Fueling · Protein Distribution · Hydration Strategy · Scientific Supplement Library" if not is_pt else "Nutrição Contextual · Distribuição Proteica · Estratégia de Hidratação · Biblioteca de Suplementos")

    prof = store.get_setting("profile", {}) or {}
    user_weight = float(prof.get("weight_kg") or prof.get("weight") or 0.0)
    target_kcal = prof.get("target_calories")
    target_protein = prof.get("target_protein_g")
    
    if not target_protein and user_weight > 0:
        target_protein = round(user_weight * 2.0)

    # A. INTRA & POST-WORKOUT FUELING
    st.markdown("### A. Fueling Around Exercise" if not is_pt else "### A. Nutrição e Abastecimento no Treino")
    
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Daily Energy Target" if not is_pt else "Energia Diária Target", f"{int(target_kcal)} kcal" if target_kcal else "—", "Set in Profile" if (not is_pt and target_kcal) else "Not Configured")
    f2.metric("Daily Protein Target" if not is_pt else "Proteína Diária Target", f"{int(target_protein)} g" if target_protein else "—", f"{(target_protein / user_weight):.1f} g/kg" if (target_protein and user_weight > 0) else "Not Configured")
    f3.metric("Workout Carbohydrates" if not is_pt else "Carboidratos Treino", "30–60 g/h", "1–2.5h sessions" if not is_pt else "Sessões 1–2.5h")
    f4.metric("Post-Workout Protocol" if not is_pt else "Estratégia Pós-Treino", "35g Protein + 70g Carb" if not is_pt else "35g Proteína + 70g Carb")

    st.caption(
        "💡 **APEX Guidance:** Carbohydrate intake during exercise is adjusted to duration and intensity. "
        "Short sessions (<60 min) require no elaborate protocol; long endurance workouts (>2.5h) may benefit from up to 60–90 g/h with gut training."
        if not is_pt else
        "💡 **Orientações APEX:** A ingestão de carboidratos durante o treino é ajustada à duração e intensidade. "
        "Sessões curtas (<60 min) não necessitam de protocolo complexo; treinos longos de resistência (>2.5h) podem beneficiar de até 60–90 g/h mediante gut-adaptation."
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # B. HYDRATION & SWEAT RATE
    st.markdown("### B. Hydration & Sweat Rate Test" if not is_pt else "### B. Hidratação & Teste de Taxa de Sudação")
    
    saved_sweat = store.get_setting("sweat_test", {}) or {}
    recorded_sweat_rate = saved_sweat.get("sweat_rate")

    h1, h2 = st.columns(2)
    with h1:
        sweat_display = f"{recorded_sweat_rate:.2f} L / hour" if recorded_sweat_rate else "—"
        sweat_desc = "Based on pre/post workout body mass change and ambient temp." if (not is_pt and recorded_sweat_rate) else "No test logged. Run sweat rate calculator to populate." if not is_pt else "Baseado na variação de peso corporal pré/pós-treino." if recorded_sweat_rate else "Sem teste registado. Executa a calculadora ao lado."
        st.markdown(
            f"""
            <div style="background:#131a27; border:1px solid #263244; padding:16px; border-radius:12px;">
                <span style="color:#94a3b8; font-size:0.85rem; font-weight:600;">{'ESTIMATED SWEAT RATE' if not is_pt else 'TAXA DE SUDAÇÃO ESTIMADA'}</span><br>
                <span style="font-size:1.8rem; font-weight:800; color:#38bdf8;">{sweat_display}</span><br>
                <span style="font-size:0.82rem; color:#cbd5e1;">{sweat_desc}</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    with h2:
        with st.form("sweat_test_form"):
            st.markdown("##### Sweat Rate Calculator" if not is_pt else "##### Calculadora de Taxa de Sudação")
            c_sw1, c_sw2 = st.columns(2)
            pre_w = c_sw1.number_input("Pre-Workout Weight (kg)" if not is_pt else "Peso Pré-Treino (kg)", min_value=0.0, max_value=200.0, value=0.0)
            post_w = c_sw2.number_input("Post-Workout Weight (kg)" if not is_pt else "Peso Pós-Treino (kg)", min_value=0.0, max_value=200.0, value=0.0)
            fluid_intake = st.number_input("Fluid Intake During Workout (L)" if not is_pt else "Líquidos Ingeridos (L)", min_value=0.0, max_value=10.0, value=0.0)
            duration_h = st.number_input("Workout Duration (hours)" if not is_pt else "Duração do Treino (horas)", min_value=0.0, max_value=24.0, value=0.0)
            
            if st.form_submit_button("Calculate Actual Sweat Rate" if not is_pt else "Calcular Taxa Real de Sudação", use_container_width=True):
                if duration_h > 0 and pre_w > 0 and post_w > 0:
                    sweat_rate = ((pre_w - post_w) + fluid_intake) / duration_h
                    store.save_setting("sweat_test", {"sweat_rate": sweat_rate, "pre_w": pre_w, "post_w": post_w, "duration_h": duration_h})
                    st.success(f"Your estimated sweat rate is **{sweat_rate:.2f} L/h**." if not is_pt else f"A tua taxa de sudação estimada é de **{sweat_rate:.2f} L/h**.")
                    st.rerun()
                else:
                    st.error("Please enter valid weight and duration inputs." if not is_pt else "Por favor introduz valores válidos de peso e duração.")

    st.markdown("<br>", unsafe_allow_html=True)

    # C. SUPPLEMENT EVIDENCE LIBRARY
    st.markdown("### C. Supplement Evidence Library (AIS / IOC Framework)" if not is_pt else "### C. Biblioteca de Suplementos (AIS / IOC Framework)")
    st.caption("APEX is an educational platform. We do not issue automated supplement prescriptions." if not is_pt else "O APEX é um sistema de informação e literacia biológica. Não prescrevemos suplementos de forma automática.")

    with st.expander("📚 Browse Evidence-Based Supplement Library" if not is_pt else "📚 Consultar Biblioteca de Suplementos", expanded=False):
        st.markdown(
            """
            #### Tier A — Strong Evidence for Specific Athletic Contexts
            * **Creatine Monohydrate:** Supported for strength, neuromuscular power, and lean mass. Typical dose: 3–5g/day.
            * **Caffeine:** Established ergogenic aid for focus and endurance (3–6 mg/kg 40–60 min pre-workout).
            * **Dietary Nitrates (Beetroot Juice):** Submaximal aerobic efficiency in endurance.
            * **Protein Powder (Whey / Isolate):** Convenient way to meet daily protein targets.
            * **Electrolytes (Sodium):** Fluid retention in long sessions or high sweat rates.

            #### Tier B / C — Conditional or Specific Evidence
            * **Collagen / Vitamin C:** Emerging support for tendon health when paired with mechanical load.
            * **Omega-3:** Cardiovascular & metabolic support; does not replace diet quality.
            * **Vitamin D3, Zinc, Iron:** Relevant primarily upon clinical deficiency via blood biomarkers.
            """
            if not is_pt else
            """
            #### Nível A — Forte Evidência Científica para Contextos Específicos
            * **Creatina Monohidratada:** Suporte em força, potência neuromuscular e massa magra (3–5g/dia).
            * **Cafeína:** Ergogénico estabelecido para atenção e performance (3–6 mg/kg).
            * **Nitratos Alimentares:** Eficiência aeróbica em endurance submáxima.
            * **Proteína em Pó:** Veículo prático para atingir metas proteicas.
            * **Electrólitos (Sódio):** Reposição hídrica em sessões longas.
            """
        )
