# Arquitectura y Funcionamiento del Sistema

Bienvenido a la documentación técnica de **Kindle Tasks & Home Portal**. Este documento explica en detalle cómo está construida esta aplicación, qué tecnologías utiliza y por qué cada decisión de diseño fue tomada pensando en dispositivos de tinta electrónica (*E-Ink*), en especial el **Kindle Scribe**.

---

## 1. Visión General del Proyecto

El objetivo principal es disponer de un portal web local en casa (LAN) que sirva como panel central para el día a día. El sistema ofrece:

1. **Casa - Pendientes:** Un gestor de tareas domésticas con persistencia atómica en archivo local JSON.
2. **Fidel - ClickUp:** Una ventana de sincronización directa con el trabajo diario (Sprint actual y Product Backlog).
3. **Fidel - Lecturas:** Un lector inmersivo de artículos y documentos Markdown con tipografía de libro.
4. **Lau:** Sección preparada para albergar futuras herramientas y utilidades familiares.

---

## 2. Arquitectura de Software

La aplicación sigue el patrón de **Server-Side Rendering (SSR)** utilizando **Python 3** y **FastAPI**:

```text
[Kindle Scribe Browser]
        │
        ▼ (HTTP / LAN)
[FastAPI Server - Puerto 8080]
        ├─► app/storage.py  ──────► data/tasks_db.json (Lock atómico)
        ├─► app/clickup_service.py ─► ClickUp API v2 (Sprints & Backlog)
        └─► app/reader_service.py  ─► docs/*.md (Renderizado Markdown)
```

### ¿Por qué Server-Side Rendering (SSR)?
Los navegadores de tinta electrónica tienen procesadores ligeros pensados para renderizar texto y no para ejecutar pesados frameworks de JavaScript cliente (React, Vue, etc.). Con FastAPI y Jinja2, **el servidor genera el HTML completo y limpio**. El Kindle recibe la página lista para mostrar de inmediato sin pausas ni procesamiento extra.

---

## 3. Componentes Principales

### A. Controlador de Procesos (`kindle_web.py`)
Para no bloquear la terminal ni depender de herramientas externas complejas, se diseñó un controlador CLI nativo:
- **`start`**: Lanza el servidor en segundo plano como un demonio (*daemon*) desvinculado de la consola (`start_new_session=True`), guarda el PID en `.kindle_tasks.pid` y redirige la salida a `kindle_tasks.log`.
- **`stop`**: Envía una señal `SIGTERM` (y `SIGKILL` como respaldo) para un apagado seguro.
- **`status`**: Informa si el servidor está activo y en qué URL LAN se encuentra.
- **`foreground`**: Permite ejecutar el servidor en primer plano con todos los tracebacks y logs en vivo para depuración.

### B. Persistencia Atómica de Tareas (`app/storage.py`)
- Los datos residen en `data/tasks_db.json`.
- Para evitar que dos escrituras simultáneas corrompan el archivo, se utiliza un archivo de bloqueo (`.lock`) mediante la librería `filelock`.
- La escritura se realiza mediante un archivo temporal y reemplazo atómico (`os.replace`), garantizando integridad absoluta ante cortes de energía o cierres inesperados.

### C. Integración con ClickUp (`app/clickup_service.py`)
- Se conecta de forma directa a la API v2 de ClickUp sin librerías externas pesadas (usando la biblioteca estándar `urllib.request`).
- Permite consultar las tareas del **Sprint activo** y del **Product Backlog** asignadas al usuario.
- En la interfaz del Kindle, las descripciones se presentan dentro de elementos desplegables (`<details>`), permitiendo leer los detalles con un solo toque sin saturar la pantalla.

### D. Lector Markdown (`app/reader_service.py`)
- Detecta automáticamente cualquier archivo `.md` ubicado dentro de la carpeta `docs/`.
- Convierte títulos, subtítulos, listas, tablas y bloques de código a HTML semántico de alto contraste.

---

## 4. Reglas de Diseño para Tinta Electrónica (E-Ink UX)

El navegador del Kindle Scribe tiene características muy particulares que dictan el diseño visual:

1. **Monocromo y Alto Contraste:** Se evitan sombras sutiles o tonos de gris indistinguibles. Se utiliza blanco puro (`#FFFFFF`) y negro puro (`#000000`) con bordes sólidos de 2 a 3 píxeles.
2. **Cero Animaciones:** Las transiciones y animaciones provocan parpadeos molestos en pantallas e-paper. Se deshabilitan completamente con `transition: none !important; animation: none !important;`.
3. **Áreas Táctiles Generosas:** Todos los botones e interruptores tienen un mínimo de 52 píxeles de alto para poder accionarse cómodamente con el dedo o con el lápiz del Kindle Scribe.
4. **Tipografía de Lectura:** Se priorizan fuentes serif como **Bookerly** y **Georgia**, con interlineado holgado (1.5 - 1.6) para una experiencia idéntica a la de un libro impreso.

---

## 5. Seguridad y Privacidad

- Las credenciales privadas (tokens de ClickUp y contraseñas de aplicación) están excluidas del control de versiones mediante `.gitignore`.
- Las tareas y notas personales nunca salen de la red local (LAN).
