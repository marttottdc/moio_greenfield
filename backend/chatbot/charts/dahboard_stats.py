from django.utils import timezone
from datetime import timedelta

import plotly.graph_objects as go
import pandas as pd
from chatbot.models.agent_session import AgentSession
from crm.models import Contact


def conversations_over_time(tenant, date_range=200):
    # Definir el rango de fechas
    start_date = timezone.now() - timedelta(days=date_range)
    end_date = timezone.now()

    # Obtener las sesiones filtradas por tenant y rango de fechas
    sessions = AgentSession.objects.filter(
        tenant=tenant,
        start__range=(start_date, end_date)
    )
    if len(sessions) == 0:
        return None

    data_sessions = [
        {'date': session.start.date(), 'active': 'Activas' if session.active else 'No Activas'}
        for session in sessions
    ]
    df_sessions = pd.DataFrame(data_sessions)
    conversation_counts = df_sessions.groupby(['date', 'active']).size().reset_index(name='count')

    # --- Contactos (Contact) ---
    contacts = Contact.objects.filter(
        source="chatbot",
        tenant=tenant,
        created__range=(start_date, end_date)
    )

    if contacts.exists():
        data_contacts = [{'date': contact.created.date()} for contact in contacts]
        df_contacts = pd.DataFrame(data_contacts)
        contact_counts = df_contacts['date'].value_counts().sort_index().reset_index()
        contact_counts.columns = ['date', 'count']
    else:
        # Si no hay contactos, crear un DataFrame vacío con las mismas fechas que las sesiones
        unique_dates = sorted(df_sessions['date'].unique())
        contact_counts = pd.DataFrame({'date': unique_dates, 'count': [0] * len(unique_dates)})

    # Crear el gráfico con Plotly (usamos graph_objects para combinar barras y línea)
    fig = go.Figure()

    # Definir colores personalizados para las barras
    colors = {
        'Activas': '#14bce5',  # Celeste
        'No Activas': '#35254b'  # Azul oscuro
    }

    # Añadir barras apiladas para conversaciones
    for active_status in ['Activas', 'No Activas']:
        df_subset = conversation_counts[conversation_counts['active'] == active_status]
        fig.add_trace(
            go.Bar(
                x=df_subset['date'],
                y=df_subset['count'],
                name=active_status,
                hovertemplate='%{y} ' + active_status,
                marker=dict(color=colors[active_status])  # Asignar color personalizado
            )
        )

    # Añadir línea para contactos
    fig.add_trace(
        go.Scatter(
            x=contact_counts['date'],
            y=contact_counts['count'],
            name='Contactos Creados (Chatbot)',
            mode='lines+markers',
            line=dict(color='green', width=1),
            hovertemplate='%{y} Contactos'
        )
    )

    # Personalizar el gráfico
    fig.update_layout(
        # ───────────── plot title ─────────────
        title=dict(
            text=(
                f'Conversaciones y Contactos por Día<br>'
                f'<span style="font-size:14px;">(Últimos {date_range} días) — {tenant.nombre}</span>'
            ),
            x=0.5,  # centered
            y=0.95,  # a bit below the top edge
            xanchor='center',
            yanchor='top',
            font=dict(
                family='Roboto, sans-serif',
                size=22,
                color='#2f3542',
                # you can add weight here if you want
            )
        ),

        # ───────────── axis titles ────────────
        xaxis=dict(
            title=dict(
                text='Fecha',
                font=dict(size=16, family='Roboto', color='#333')
            )
        ),
        yaxis=dict(
            title=dict(
                text='Cantidad',
                font=dict(size=16, family='Roboto', color='#333')
            )
        ),
        # ───────────── legend title / style ───
        legend=dict(
            title=dict(
                text='Categoría',
                font=dict(size=14, family='Roboto', color='#555')
            ),
            orientation='h',  # horizontal bar
            y=-0.2,  # push legend below plot
            x=0.5,
            xanchor='center'
        ),

        barmode='stack',
        hovermode='x unified',
        bargap=0.2,
        template='plotly_white',

        # ───────────── global font fallback ───
        font=dict(family='Roboto', size=12, color='#444')
    )
    # Convertir el gráfico a HTML
    graph_html = fig.to_html(full_html=False, include_plotlyjs=False)

    return graph_html
