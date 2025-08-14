# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VaultHunter Web Manager is a Flask-based web application for managing VaultHunter Minecraft servers. It provides server control, log monitoring, configuration management, and backup downloads through a Bootstrap-based web interface.

## Current Status

This repository currently contains only the README.md file with project specifications. The actual Flask application code, templates, static files, and configuration files need to be implemented.

## Architecture (Planned)

Based on the README.md specifications:

- **Flask Application** (`app.py`): Main web server with routes for server control, log viewing, config editing, and backup management
- **Configuration** (`config.py`): Server paths, systemd service name, web interface settings
- **Templates** (`templates/`): Jinja2 templates for dashboard, logs, config editor, and backup manager
- **Static Files** (`static/`): CSS and JavaScript for Bootstrap-based responsive UI
- **Requirements** (`requirements.txt`): Python dependencies including Flask

## Key Implementation Requirements

- **Server Control**: Interface with systemd service for VaultHunter server start/stop/restart
- **Log Monitoring**: Read and display server logs, crash reports, debug logs with auto-refresh
- **Configuration Management**: Edit server.properties and other config files through web interface
- **Backup Management**: List, download backups from configured backup directory
- **Security**: Session-based auth, input validation, file access restrictions
- **User Context**: Run as minecraft user (no root required)

## Dependencies

- Python 3.7+
- Flask web framework
- Bootstrap for frontend UI
- systemd for service management (Linux/Unix)

## Virtual Environment Setup

The application runs in a Python virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuration Paths

- Minecraft server: `/home/minecraft/vaulthunter` (configurable)
- Backups: `/home/minecraft/backups` (configurable)
- Systemd service: `vaulthunter` (configurable)
- Web interface: `0.0.0.0:8080` (configurable)
- Virtual environment: `./venv/` (project root)

## Development Commands

- `source venv/bin/activate` - Activate virtual environment
- `python app.py` - Run development server (in venv)
- `pip install -r requirements.txt` - Install dependencies (in venv)
- `deactivate` - Exit virtual environment
- For production: systemd service `vaulthunter_web_manager.service` uses `./venv/bin/python app.py`

## Implementation Reference

See `IMPLEMENTATION_PLAN.md` for detailed development phases and technical considerations. Key implementation points:

- Use subprocess module for systemd service control
- Implement proper file locking for config edits
- Add CSRF protection and input validation
- Use AJAX for real-time server status updates
- Implement log tailing for real-time log viewing