import streamlit as st
import pandas as pd
from datetime import date, timedelta

def render_weekly_calendar():
    st.markdown("""
        <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;'>
            <div>
                <h2 style='font-size: 1.6rem; font-weight: 900; margin: 0; color: #FFFFFF;'>📅 PLANO SEMANAL DE TREINO</h2>
                <p style='color: #64748B; font-size: 0.82rem; font-weight: 600; margin: 4px 0 0 0;'>Prescrição do Treinador vs. Capacidade Fisiológica</p>
            </div>
            <span class='live-badge'>SEMANA ATIVA</span>
        </div>
    """, unsafe_allow_html=True)

    # Identificar a Segunda-feira da semana atual
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday()) # Monday
    days_of_week = [start_of_week + timedelta(days=i) for i in range(7)]
    week_names = ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"]

    # Simulação de treinos vindos do Supabase (Substituir por consulta à tabela `planned_workouts`)
    # Na prática: raw_plans = store.fetch_planned_workouts(start_of_week, start_of_week + timedelta(days=6))
    mock_workouts = {
        0: {"sport": "🚴 Ciclismo", "title": "Rolo Z2 + Cadência", "dur": "60m", "tss": 45, "type": "Easy"},
        1: {"sport": "🏃 Corrida", "title": "Séries Limiar 4x1000m", "dur": "50m", "tss": 75, "type": "Hard"},
        2: {"sport": "🏊 Natação", "title": "Técnica + Vo2Max", "dur": "45m", "tss": 50, "type": "Moderate"},
        3: {"sport": "🏋️ Força", "title": "Full Body + Core", "dur": "60m", "tss": 40, "type": "Easy"},
        4: {"sport": "🚴 Ciclismo", "title": "Tempo Z3 Sustentado", "dur": "90m", "tss": 85, "type": "Hard"},
        5: {"sport": "🏃 Corrida", "title": "Longão Z2 Progressivo", "dur": "105m", "tss": 110, "type": "Long"},
        6: {"sport": "🧘 Descanso", "title": "Regenerativo & Mobilidade", "dur": "0m", "tss": 0, "type": "Rest"}
    }

    # Grid de 7 Colunas para os Dias da Semana
    cols = st.columns(7)

    for idx, (col, day_date) in enumerate(zip(cols, days_of_week)):
        is_today = (day_date == today)
        workout = mock_workouts.get(idx, None)
        
        # Cores e destaque para o dia atual e tipo de treino
        border_color = "rgba(16, 185, 129, 0.6)" if is_today else "rgba(255, 255, 255, 0.08)"
        bg_card = "rgba(16, 185, 129, 0.08)" if is_today else "rgba(16, 22, 34, 0.75)"
        
        with col:
            st.markdown(f"""
                <div style='
                    background: {bg_card};
                    border: 1px solid {border_color};
                    border-radius: 18px;
                    padding: 14px 10px;
                    text-align: center;
                    min-height: 220px;
                    box-shadow: 0 10px 25px rgba(0,0,0,0.5);
                    position: relative;
                '>
                    <p style='color: {"#10B981" if is_today else "#64748B"}; font-weight: 900; font-size: 0.75rem; margin: 0;'>
                        {week_names[idx]}
                    </p>
                    <h3 style='color: #FFFFFF; font-weight: 800; font-size: 1.1rem; margin: 2px 0 10px 0;'>
                        {day_date.strftime("%d/%m")}
                    </h3>
                    <hr style='border: 0; border-top: 1px solid rgba(255,255,255,0.08); margin: 8px 0;'>
            """, unsafe_allow_html=True)

            if workout and workout["tss"] > 0:
                st.markdown(f"""
                    <div style='text-align: left; background: rgba(0,0,0,0.3); padding: 8px; border-radius: 10px;'>
                        <p style='font-size: 0.75rem; font-weight: 800; color: #F8FAFC; margin: 0;'>{workout["sport"]}</p>
                        <p style='font-size: 0.7rem; color: #94A3B8; margin: 2px 0 6px 0; line-height: 1.1;'>{workout["title"]}</p>
                        <span style='background: rgba(255,255,255,0.1); color: #E2E8F0; font-size: 0.65rem; padding: 2px 6px; border-radius: 6px; font-weight: 700;'>
                            ⏱️ {workout["dur"]} | ⚡ {workout["tss"]} TSS
                        </span>
                    </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown("""
                    <div style='margin-top: 20px;'>
                        <p style='font-size: 1.2rem; margin: 0;'>🧘</p>
                        <p style='font-size: 0.7rem; color: #64748B; font-weight: 700;'>Descanso</p>
                    </div>
                """, unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")
    
    # Área para o Treinador Inserir / Editar Treino Rapidamente
    with st.expander("➕ Área do Treinador — Adicionar / Editar Treino Prescrito"):
        with st.form("form_add_workout"):
            c1, c2, c3 = st.columns(3)
            with c1:
                selected_date = st.date_input("Data do Treino", value=today)
                sport_type = st.selectbox("Modalidade", ["🚴 Ciclismo", "🏃 Corrida", "🏊 Natação", "🏋️ Força", "🧘 Mobilidade"])
            with c2:
                w_title = st.text_input("Título do Treino", placeholder="Ex: Séries de VO2Max 5x3min")
                w_dur = st.number_input("Duração Planeada (minutos)", value=60, step=5)
            with c3:
                w_tss = st.number_input("Carga Estimada (TSS)", value=50, step=5)
                w_notes = st.text_area("Instruções do Treinador", placeholder="Zonas de Frequência Cardíaca / Potência...")
            
            btn_save = st.form_submit_button("💾 Guardar Treino na Agenda", use_container_width=True)
            if btn_save:
                st.success(f"Treino de {sport_type} agendado com sucesso para {selected_date}!")
