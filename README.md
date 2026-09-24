# Kindle Tasks

A minimalist, high-contrast local task management web application custom-tailored for electronic ink (E-Ink) displays, specifically optimized for the Kindle Scribe experimental browser.

---

## Objective

The primary objective of **Kindle Tasks** is to provide an effortless, distraction-free task management experience on Kindle devices within a local home or office network (LAN).

E-Ink screens present unique hardware constraints—such as slower refresh rates and grayscale rendering—while excelling at paper-like legibility and zero eye strain. Standard modern web applications with complex JavaScript frameworks, subtle gray tones, and animations perform poorly on these displays.

Kindle Tasks solves this by offering:
- **High-Contrast E-Ink Typography**: Crisp pure black and white styling, sharp borders, and legible typography tailored specifically for e-paper visibility.
- **Server-Side Rendering (SSR)**: Built with FastAPI and Jinja2 templates. Pages render instantly without relying on heavy client-side JavaScript execution.
- **Kindle-Friendly Interactions**: Generous touch targets, simplified form inputs, and fast page transitions suitable for the Kindle Scribe's touch response.
- **Local Network Privacy**: Tasks remain entirely local on your network, stored safely in an atomic JSON persistence file.

---

## Features

- **Pending & Completed Views**: Organize pending tasks by priority and due date, with a dedicated view for completed and archived items.
- **Priority Indicators**: Categorize tasks into High, Medium, and Low priorities with clear, bold indicators.
- **Due Date Reminders**: Visual cues for tasks due today, tomorrow, or overdue.
- **ClickUp Integration**: Real-time integration with ClickUp to view active Sprint tasks (automatically detected by dates) and Product Backlog, complete with task creation, Story Points assignment, and status transitions.
- **Automated Deployment**: Built-in deployment script (`deploy/sync_to_server.py`) to stop the remote daemon, pull updates, sync configurations, and restart the service on the LAN server.
- **Zero Configuration Launcher**: An automated `run.py` script that creates the virtual environment, installs dependencies, and serves the application.
- **Atomic Concurrency Protection**: File-locking persistence ensures data integrity during reads and writes.

---

## Quick Start

### Prerequisites

- **Python 3.10+** (tested with Python 3.11, 3.12, and 3.13)
- On Debian/Ubuntu/Linux Mint systems, ensure `python3-venv` is installed:
  ```bash
  sudo apt install -y python3-venv python3-pip
  ```

### Running the Server

Clone the repository:

```bash
git clone git@github.com:fidelm02/web_tasks_kindle.git
cd web_tasks_kindle
```

Run the controller script:

```bash
# Start in background (daemon mode, frees the terminal):
python3 kindle_web.py start

# Check status:
python3 kindle_web.py status

# Stop the server:
python3 kindle_web.py stop

# Run in foreground (shows live logs and tracebacks for debugging):
python3 kindle_web.py foreground
```

> **Note:** `python3 run.py` remains available as a wrapper for backwards compatibility.

### Accessing from your Kindle

1. Ensure your Kindle is connected to the same Wi-Fi network as your host machine.
2. Open the Kindle's experimental web browser (Settings → Web Browser / Experimental Browser).
3. Navigate to the URL printed in the terminal (e.g., `http://192.168.1.50:8080/`).
4. Bookmark the page on your Kindle for quick one-tap access.

---

## Tech Stack

- **Backend**: Python, [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/)
- **Templating**: [Jinja2](https://jinja.palletsprojects.com/)
- **Persistence**: Atomic file-locked JSON storage (`data/tasks_db.json`)
- **Styling**: Pure CSS (zero framework overhead, optimized for monochrome screens)
