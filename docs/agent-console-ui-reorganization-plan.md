# Plan: Reorganización UI e integración del Agent Console

Objetivo: integrar el Agent Console con el resto de la plataforma (mismo shell, design system y patrones) y hacer el código mantenible sin cambiar la funcionalidad actual (agente = documento markdown, usuario = burbujas).

---

## Estado actual

- **Hecho:** mensajes del agente con markdown (documento), mensajes del usuario en burbujas.
- **Pendiente:** todo lo que se lista abajo.

El Agent Console hoy:
- Usa el layout general de la app (AppSidebar + main con `p-0` para full-bleed).
- Dentro de `main` renderiza su propia grid de 3 columnas: **sidebar izquierdo propio** (sessions, tenant, user) en oscuro (`bg-slate-700/95`), **chat central** (blanco), **panel derecho** “Agent Status” solo en `xl`.
- Todo vive en un solo archivo: `AgentConsoleApp.tsx` (~2.430 líneas, `@ts-nocheck`).

---

## Fase 1 – Refactor en componentes (sin cambiar layout ni comportamiento)

**Objetivo:** partir el monolito en componentes para poder mantener y reutilizar.

| Tarea | Descripción | Archivos |
|-------|-------------|----------|
| 1.1 | Extraer tipos compartidos (`SessionRow`, `UiMessage`, `RunStatus`, `ToolEvent`, `QueuedTurn`, `AgentConfig`, etc.) a un módulo de tipos (p. ej. `legacy-admin/vendor/types/agent-console.ts` o dentro de `AgentConsoleApp` en un `types.ts` colgado). | Nuevo `types.ts`; `AgentConsoleApp.tsx` importa tipos. |
| 1.2 | Extraer **SessionsSidebar**: lista de sesiones, búsqueda, botón New, footer tenant/workspace/user. Recibe props (sessions, config, sessionSearch, handlers) y el estado relevante se sigue manejando en el padre o en un hook. | Nuevo `SessionsSidebar.tsx`; `AgentConsoleApp` lo usa. |
| 1.3 | Extraer **ChatHeader**: título “Agent”, View Summary, Share, estado connected, menú móvil (hamburger). | Nuevo `ChatHeader.tsx`. |
| 1.4 | Extraer **ChatMessageList**: iteración sobre `messages`, render de user (burbuja) y assistant (MarkdownRenderer). Empty state y “Jump to latest”. | Nuevo `ChatMessageList.tsx`. |
| 1.5 | Extraer **ComposerFooter**: textarea, adjuntos, live run banner, queue panel, botones (attach, snapshot, abort, send), chips modelo/thinking/verbosity. | Nuevo `ComposerFooter.tsx`. |
| 1.6 | Extraer **AgentStatusPanel**: pestañas Status/Activity, Run card, Session/Queue/Tokens, Runtime (resourcesSummary), lista de toolEvents. | Nuevo `AgentStatusPanel.tsx`. |
| 1.7 | Opcional: extraer hook **useAgentConsoleWebSocket** (conexión, reconexión, envío de acciones, manejo de frames) para dejar `AgentConsoleApp` como orquestador de estado + layout. | Nuevo `useAgentConsoleWebSocket.ts`. |

**Criterio de éxito:** misma UI y comportamiento; `AgentConsoleApp.tsx` pasa a orquestar componentes y estado (~300–500 líneas).

---

## Fase 2 – Integración del sidebar con la plataforma

**Objetivo:** no tener dos sidebars distintos (AppSidebar + sidebar oscuro del Agent Console).

**Opción A – Sesiones dentro del AppSidebar (recomendada)**  
- En `/agent-console`, el **AppSidebar** sigue siendo el único sidebar.
- Añadir un **SidebarGroup** “Agent” (o “Sessions”) que solo se muestre cuando `location === "/agent-console"`: lista de sesiones, “New”, búsqueda (o enlace a una vista de sesiones).
- El **contenido principal** del Agent Console pasa a ser solo: **chat (header + mensajes + composer)** y **panel Agent Status** (derecha o drawer).
- Eliminar la columna izquierda propia (220px) y el drawer móvil duplicado del Agent Console; la navegación de sesiones vive en `AppSidebar` (o en un Sheet desde el header del chat si se prefiere no cargar el sidebar con muchas sesiones).

**Opción B – Mantener columna izquierda pero con estilo de la plataforma**  
- Mantener la grid de 3 columnas pero sustituir `bg-slate-700/95` por los tokens del design system (sidebar, background, border) para que visualmente coincida con `AppSidebar` (o con el tema claro del resto de la app).

**Archivos a tocar (Opción A):**  
- `App.tsx`: sin cambios de ruta; `/agent-console` sigue full-bleed si se desea.
- `app-sidebar.tsx`: condicional por ruta, mostrar grupo “Sessions” del Agent Console (y posiblemente navegación entre sesiones).
- `AgentConsoleApp.tsx` (o nuevo `AgentConsolePageLayout`): quitar primera columna y usar datos de sesión/lista que puedan venir de contexto o props si el sidebar está fuera.
- Posible **AgentConsoleContext** para compartir sesión activa, lista de sesiones y acciones entre AppSidebar y la zona de chat.

**Criterio de éxito:** un solo sidebar en la app; sesiones del Agent Console accesibles desde ahí o desde un único drawer/sheet.

---

## Fase 3 – Panel Agent Status en todas las pantallas

**Objetivo:** que “Agent Status” (Status + Activity) sea accesible en `lg` y móvil, no solo en `xl`.

| Tarea | Descripción |
|-------|-------------|
| 3.1 | En viewport `< xl`, no mostrar la columna derecha fija; en su lugar mostrar un botón en el header del chat (p. ej. “Status” o icono) que abra un **Sheet** (shadcn) lateral derecho con el mismo contenido que el panel actual (Status / Activity). |
| 3.2 | Opcional en móvil: mismo Sheet o un **Drawer** bottom para “Agent Status” con pestañas compactas. |

**Archivos:**  
- `AgentConsoleApp` o `ChatHeader` + `AgentStatusPanel`: lógica de “mostrar panel inline (xl) vs abrir Sheet (lg/mobile)”.
- `AgentStatusPanel`: aceptar prop `variant="inline" | "sheet"` para ajustar padding/tamaño si hace falta.

**Criterio de éxito:** cualquier breakpoint puede ver Run, Session/Queue/Tokens, Runtime y Activity.

---

## Fase 4 – Mejoras de sesiones y composer

**Sesiones**  
- Agrupar lista por tiempo: “Hoy”, “Esta semana”, “Anteriores” (usando `updatedAtMs`).
- Renombrar sesión: edición inline (doble clic en título) con guardado vía WebSocket (`chat_session_rename`).
- Badges claros para scope: “Shared” / “Private” (ya hay ícono; se puede añadir texto).

**Composer**  
- Compactar banner “Live run” y panel “Queue”: una sola línea o acordeón para no restar tanto espacio al textarea.
- Mantener snapshot; opcional: mover “Snapshot” a un botón del panel Agent Status (Status tab) para no duplicar conceptos.

**Archivos:**  
- `SessionsSidebar` (o el componente que renderice la lista de sesiones).
- `ComposerFooter` (o equivalente tras Fase 1).

---

## Fase 5 – Consistencia de diseño (shadcn + tema)

**Objetivo:** mismo lenguaje visual que el resto de la plataforma.

- Sustituir controles ad hoc por componentes shadcn: **Tabs** (Status/Activity), **Select** (workspace, modelo si aplica), **Button**, **Input**, **ScrollArea**.
- Revisar colores: evitar `slate-700/95` suelto; usar variables del tema (sidebar, background, card, border) o tokens existentes (`brand-*` ya usados).
- Asegurar que el panel de chat y el panel de status usen los mismos tokens que el resto de la app (p. ej. `card`, `muted`).

**Archivos:**  
- Todos los componentes extraídos del Agent Console; `AgentConsoleApp` o layout contenedor.

---

## Orden sugerido de ejecución

1. **Fase 1** primero: refactor en componentes. No cambia la experiencia; facilita todo lo demás.
2. **Fase 3** (Agent Status en Sheet/Drawer): mejora clara en usabilidad y es acotada.
3. **Fase 2** (integrar sidebar): decisión de producto (Opción A vs B); implementar cuando se decida.
4. **Fase 4** y **Fase 5** en paralelo o después: sesiones + composer más compacto, y luego pulir con shadcn/tema.

---

## Resumen por fases

| Fase | Qué se hace | Resultado |
|------|-------------|-----------|
| 1 | Refactor en componentes y tipos | Código mantenible, misma UI |
| 2 | Unificar sidebar (sesiones en AppSidebar o mismo estilo) | Una sola navegación lateral |
| 3 | Agent Status en Sheet/Drawer cuando no hay columna xl | Status visible en móvil/tablet |
| 4 | Sesiones agrupadas + inline rename; composer compacto | Mejor UX en sesiones y escritura |
| 5 | shadcn + tokens de tema en todo el Agent Console | Consistencia visual con la plataforma |
