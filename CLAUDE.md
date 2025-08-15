# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VaultHunter Web Manager is a Flask-based web application for managing VaultHunter Minecraft servers. It provides server control, log monitoring, configuration management, and backup downloads through a Bootstrap-based web interface.

## Current Status

**IMPLEMENTATION COMPLETE** - The VaultHunter Web Manager is fully implemented with all planned features plus additional enhancements:

- ✅ Complete Flask application with all backend services
- ✅ Dashboard with accurate real-time player counts (10-second updates)
- ✅ Full RCON console with secure modal authentication
- ✅ Advanced log monitoring with auto-refresh
- ✅ Multi-category configuration editor 
- ✅ Backup management system
- ✅ Dark mode support and responsive design
- ✅ Enhanced with mcstatus library for reliable Minecraft server integration

## Architecture (Implemented)

Based on the README.md specifications:

- **Flask Application** (`app.py`): Main web server with routes for server control, log viewing, config editing, backup management, and RCON console
- **Configuration** (`config.py.example`): Configuration template - copy to `config.py` and customize server paths, systemd service name, web interface settings, Minecraft server connection details
- **Templates** (`templates/`): Jinja2 templates for dashboard, console, logs, config editor, and backup manager
- **Static Files** (`static/`): CSS and JavaScript for Bootstrap-based responsive UI with console functionality
- **Requirements** (`requirements.txt`): Python dependencies including Flask and mcstatus for Minecraft server integration

## Key Implementation Requirements

- **Server Control**: Interface with systemd service for VaultHunter server start/stop/restart with accurate player counts
- **RCON Console**: Full server console access with secure modal authentication for command execution
- **Log Monitoring**: Read and display server logs, crash reports, debug logs with auto-refresh
- **Configuration Management**: Edit server.properties and other config files through web interface
- **Backup Management**: List, download backups from configured backup directory
- **Real-time Monitoring**: Accurate server status and player counts using Minecraft query protocol
- **Security**: Session-based auth, input validation, file access restrictions, secure RCON authentication
- **User Context**: Run as minecraft user (no root required)

## Dependencies

- Python 3.7+
- Flask web framework
- mcstatus library for Minecraft server integration
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
- Minecraft server host/ports: `localhost:25565` (configurable)
- RCON port: `25575` (configurable, password via secure modal)

## Development Commands

- `source venv/bin/activate` - Activate virtual environment
- `python app.py` - Run development server (in venv)
- `pip install -r requirements.txt` - Install dependencies (in venv)
- `deactivate` - Exit virtual environment
- For production: systemd service `vaulthunter_web_manager.service` uses `./venv/bin/python app.py`

## Implementation Reference

See `IMPLEMENTATION_PLAN.md` for detailed development phases and technical considerations. 

**VERIFIED IMPLEMENTATION POINTS:**
- ✅ Subprocess module for systemd service control - IMPLEMENTED in `services/system_control.py`
- ✅ Atomic file writes for config edits - IMPLEMENTED in `services/config_manager.py`
- ✅ CSRF protection and input validation - IMPLEMENTED with Flask-WTF across all routes
- ✅ AJAX for real-time server status updates - IMPLEMENTED in `static/js/app.js`
- ✅ Log viewing with auto-refresh - IMPLEMENTED in `services/log_service.py`
- ✅ Production-ready security and error handling - IMPLEMENTED throughout all services

**STATUS:** 🎉 **PRODUCTION READY - ALL FEATURES VERIFIED FUNCTIONAL**