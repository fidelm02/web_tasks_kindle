# AGENTS.md - Contexto y Guía Permanente para Asistentes AI

## 1. Visión del Proyecto (Kindle Tasks Pro & Home Portal)
Sistema integral de gestión de tareas, lectura en Kindle Scribe, seguimiento de salud/fitness y asistente de mensajería para Fidel y Lau.

## 2. Servicios Activos y Puertos (Servidor Local: 192.168.0.98)
- **Kindle Tasks (Original):** Puerto `8080` (`kindle_web.py`)
  - Interfaz pura para Kindle Scribe y Kindle Touch en escala de grises.
  - No modificar sin requerimiento explícito.
- **Portal Pro (Dashboard Moderno):** Puerto `8090` (`portal_web.py`)
  - Vistas: Tareas (Tabla, Kanban, Calendario/Time-Blocking, Gantt), Biblioteca Kindle, Salud & Fitness, y WhatsApp.
  - Webhook de WhatsApp: `POST /api/whatsapp/webhook`.
- **WhatsApp Bridge (Daemon Node.js Baileys 7):**
  - Ubicación: `whatsapp_bridge/`
  - Ejecutable: `whatsapp_web.py` -> `node bootstrap.cjs` -> `index.js`.
  - Grupo monitoreado: **"Chismoso"** (`120363428629349624@g.us`).
  - Teléfono autenticado: Fidel (`15142586034`).

## 3. Integración de WhatsApp y Capacidades de Gemini
- **Audio/Texto:** Capturado por Baileys y enviado en base64 al webhook del Portal.
- **Modelo:** `gemini-3.6-flash` (con fallbacks automáticos).
- **Acciones soportadas:**
  1. `task`: Crea tareas para Fidel (`data/tasks_fidel_db.json`) o Lau (`data/tasks_lau_db.json`).
  2. `email`: Redacta y envía correos vía Gmail SMTP (`GMAIL_SENDER_EMAIL` / `GMAIL_APP_PASSWORD`).
     - Contacto Lau / Laura / Lalis -> `lalisgallego@hotmail.com`.
     - Contacto Fidel -> `fidelm02@gmail.com`.
  3. `calendar_event`: Agenda citas con fecha/hora en las tareas y devuelve enlace directo de 1 clic a Google Calendar.
  4. `kindle_doc`: Genera archivos Markdown en `docs/` o `docs_lau/`.
  5. `health_log`: Registra peso corporal y hábitos en `data/health_data.json`.
  6. `chat_response`: Respuestas directas al grupo.
- **Reacciones:** 🎧 (audio) o ⏳ (texto) al recibir -> ✅ al concluir con éxito -> ❌ en error.

## 4. Perfil de Salud (Fidel)
- Altura: 165 cm | Peso actual: 93.0 kg.
- Meta Fase 1 (12 semanas): -8 kg (85.0 kg).
- Meta atlética final: 68.0 kg (base clínica OMS ~61.2 kg).
- Rutina: 4 días de gimnasio (Torso/Pierna con cuidado articular) + 60 min diarios de caminata LISS (Zona 2).

## 5. Solución de Problemas Frecuentes
- **Error `not-acceptable` en WhatsApp:** Baileys 6.x no soportaba LIDs en grupos; se resolvió migrando a `@whiskeysockets/baileys@7.0.0-rc14`.
- **Node 18 WebCrypto:** Requiere `bootstrap.cjs` para cargar `node:crypto.webcrypto` en `globalThis.crypto` antes de los módulos ESM.
- **Sincronización:** `python3 deploy/sync_to_server.py` sincroniza archivos confidenciales (`constants.py`, `health_data.json`) y reinicia servicios en el servidor.
