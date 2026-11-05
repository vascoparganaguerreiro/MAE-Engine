from __future__ import annotations

from html import escape
import streamlit as st
import data_store as store


def render_nutrition_habits_layer():
    st.markdown("---")
    st.markdown("## Fuel, Hydrate & Recover (Camada Transversal)")
    st.caption("Nutrição Contextual de Treino · Distribuição Proteica · Estratégia de Hidratação · Biblioteca Científica de Suplementos")

    # =========================================================================
    # A. INTRA & POST-WORKOUT FUELING
    # =========================================================================
    st.markdown("### A. Fueling Around Exercise")
    
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Energia Diária Target", "2,650 kcal")
    f2.metric("Proteína Diária Target", "165 g", "2.0 g/kg")
    f3.metric("Carboidratos Treino", "30–60 g/h", "Sessões 1–2.5h")
    f4.metric("Estratégia Pós-Treino", "35g Proteína + 70g Carb")

    st.caption(
        "💡 **Orientações APEX:** A ingestão de carboidratos durante o treino é ajustada à duração e intensidade. "
        "Sessões curtas (<60 min) não necessitam de protocolo complexo; treinos longos de resistência (>2.5h) podem beneficiar de até 60–90 g/h mediante treino gut-adaptation."
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # =========================================================================
    # B. HYDRATION & SWEAT RATE
    # =========================================================================
    st.markdown("### B. Hydration & Sweat Rate Test")
    
    h1, h2 = st.columns(2)
    with h1:
        st.markdown(
            """
            <div style="background:#131a27; border:1px solid #263244; padding:16px; border-radius:12px;">
                <span style="color:#94a3b8; font-size:0.85rem; font-weight:600;">ESTIMATIVA DE TAXA DE SUDAÇÃO</span><br>
                <span style="font-size:1.8rem; font-weight:800; color:#38bdf8;">1.15 L / hora</span><br>
                <span style="font-size:0.82rem; color:#cbd5e1;">Baseado na variação de peso corporal pré/pós-treino e temperatura local.</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    with h2:
        with st.form("sweat_test_form"):
            st.markdown("##### Calculadora de Taxa de Sudação Diária")
            c_sw1, c_sw2 = st.columns(2)
            pre_w = c_sw1.number_input("Peso Pré-Treino (kg)", value=75.0)
            post_w = c_sw2.number_input("Peso Pós-Treino (kg)", value=74.1)
            fluid_intake = st.number_input("Líquidos Ingeridos durante treino (L)", value=0.5)
            duration_h = st.number_input("Duração do Treino (horas)", value=1.5)
            
            if st.form_submit_button("Calcular Taxa Real de Sudação", use_container_width=True):
                sweat_rate = ((pre_w - post_w) + fluid_intake) / duration_h if duration_h > 0 else 0
                st.success(f"A tua taxa de sudação estimada é de **{sweat_rate:.2f} L/h**.")

    st.markdown("<br>", unsafe_allow_html=True)

    # =========================================================================
    # C. SUPPLEMENT EVIDENCE LIBRARY (AIS / IOC FRAMEWORK)
    # =========================================================================
    st.markdown("### C. Supplement Evidence Library (AIS / IOC Framework)")
    st.caption("O APEX é um sistema de informação e literacia biológica. Não prescrevemos suplementos de forma automática.")

    with st.expander("📚 Consultar Biblioteca de Suplementos e Níveis de Evidência", expanded=False):
        st.markdown(
            """
            #### Nível A — Forte Evidência Científica para Contextos Específicos
            * **Creatina Monohidratada:** Suporte comprovado em força, potência neuromuscular e massa magra. Dosagem típica: 3–5g/dia.
            * **Cafeína:** Ergogénico estabelecido para atenção e performance de endurance ($3\text{--}6\text{ mg/kg}$ toma 40–60 min antes).
            * **Nitratos Alimentares (Sumo de Beterraba):** Eficiência aeróbica em endurance submáxima.
            * **Proteína em Pó (Whey / Isolada):** Veículo prático para atingir metas proteicas diárias.
            * **Electrólitos (Sódio):** Reposição hídrica em sessões longas ou de elevada taxa de sudação.

            #### Nível B / C — Evidência Condicional ou Específica
            * **Colagénio / Vitamina C:** Evidência emergente para saúde tendinosa quando associado a carga mecânica.
            * **Ómega-3:** Apoio metabólico e cardiovascular; não substitui o perfil dietético global.
            * **Vitamina D3, Zinco, Ferro:** Relevantes apenas mediante identificação clínica de défice em exames de sangue.
            
            ⚠️ *Consulta sempre um profissional de saúde/medicina desportiva antes de iniciar qualquer protocolo.*
            """
        )
