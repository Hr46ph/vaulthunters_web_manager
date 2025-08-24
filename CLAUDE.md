# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VaultHunters Web Manager is a Flask-based web application for managing VaultHunters Minecraft servers. It provides server control, log monitoring, configuration management, and backup downloads through a Bootstrap-based web interface.

## Architecture

Direct process management architecture:

- **Flask Application** (`app.py`): Main web server with routes for server control, log viewing, config editing, backup management, RCON console, and system monitoring
- **Configuration** (`config.py.example`): Configuration template with Java/JVM settings, server paths, web interface settings, and Minecraft connection details
- **Process Management** (`services/system_control.py`): Direct Java process launching with detached execution, monitoring, and control with psutil integration
- **Templates** (`templates/`): Jinja2 templates with logs page, crash report dropdown selector, and monitoring dashboard with Chart.js integration
- **Static Files** (`static/`): CSS and JavaScript for Bootstrap-based responsive UI with RCON functionality
- **Requirements** (`requirements.txt`): Python dependencies including Flask, mcstatus, mcrcon, and psutil

## Key Implementation Requirements

- **Server Control**: Process-independent Java management with Forge launcher support - server survives web app restarts
- **Integrated RCON Console**: Dashboard-embedded console with custom socket client and VaultHunters-specific commands
- **Smart Process Detection**: Accurate Java process identification (not bash wrappers) with PID display and dynamic MB/GB memory formatting
- **Real-time Log Monitoring**: Server-Sent Events (SSE) for instant log updates with `tail -F` log rotation support
- **Log Interface**: 2-window log viewer (latest + debug/crash toggle) with follow controls
- **Configuration Management**: Multi-category config editor with atomic file operations and automatic backups
- **Backup Management**: List, download, and inspect backups from configured backup directory
- **Real-time Monitoring**: Accurate server status and player counts using mcstatus and process statistics
- **Real-time Status**: Live server status, Java process CPU and memory usage for dashboard display
- **Security**: Custom CSRF protection, input validation, file access restrictions
- **User Context**: Run as minecraft user with direct process control (no systemd or root required)

## Dependencies

- Python 3.7+
- Flask web framework with Flask-WTF for security
- mcstatus library for Minecraft server integration
- mcrcon library for RCON console functionality
- psutil for process monitoring and management
- Bootstrap for frontend UI
- Java 8+ for Minecraft server execution

## Virtual Environment Setup

The application runs in a Python virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuration Paths

- Minecraft server: `/home/minecraft/vaulthunters` (configurable)
- Backups: `/home/minecraft/backups` (configurable)
- Java executable: `java` (configurable with full path support)
- Server jar: `forge-1.18.2-40.2.21-universal.jar` (configurable)
- Web interface: `0.0.0.0:8080` (configurable)
- Virtual environment: `./venv/` (project root)
- Minecraft server host/ports: `localhost:25565` (configurable)
- RCON port: Automatically read from server.properties

## Development Commands

- `source venv/bin/activate` - Activate virtual environment
- `python app.py` - Run development server (in venv)
- `pip install -r requirements.txt` - Install dependencies (in venv)
- `deactivate` - Exit virtual environment
- For production: systemd service `vaulthunters_web_manager.service` uses `./venv/bin/python app.py`
- Server control: Direct process management (no separate systemd service needed for Minecraft)

## Implementation Status

**All features are implemented and functional:**
- Direct Java process management in `services/system_control.py` with psutil integration
- Atomic file writes for config edits in `services/config_manager.py`
- CSRF protection and input validation with Flask-WTF across all routes
- AJAX for real-time server status updates in `static/js/app.js`
- Log viewing with real-time streaming in `services/log_service.py`
- RCON custom socket client avoiding signal issues
- Server status dashboard with real-time updates every 5-10 seconds
- Player tracking with login/logout session management
- Production-ready security and error handling throughout all services

## Status Monitoring

The application provides real-time status information without historical data collection:

- **Server Status**: Running/stopped state via process detection
- **Resource Usage**: Live Java process CPU and memory usage for dashboard display
- **Player Information**: Current online player count and names via mcstatus
- **System Information**: Java version, kernel version, and basic system details

No metrics database or historical data retention is implemented. Status information is fetched in real-time for dashboard updates.