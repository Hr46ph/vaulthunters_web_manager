# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VaultHunters Web Manager is a Flask-based web application for managing VaultHunters Minecraft servers. It provides server control, log monitoring, configuration management, and backup downloads through a Bootstrap-based web interface.

## Architecture

Direct process management architecture:

- **Flask Application** (`app.py`): Main web server with routes for server control, log viewing, config editing, backup management, RCON console, and basic system monitoring
- **Configuration** (`config.py.example`): Configuration template with Java/JVM settings, server paths, web interface settings, and Minecraft connection details
- **Process Management** (`services/system_control.py`): Direct Java process launching with detached execution, monitoring, and control with psutil integration
- **Templates** (`templates/`): Jinja2 templates with logs page, radio button log type selector, and server status dashboard
- **Static Files** (`static/`): CSS and JavaScript for Bootstrap-based responsive UI with RCON functionality
- **Requirements** (`requirements.txt`): Python dependencies including Flask, mcstatus, mcrcon, and psutil

## Key Implementation Requirements

- **Server Control**: Process-independent Java management with Forge launcher support - server survives web app restarts
- **Integrated RCON Console**: Dashboard-embedded console with custom socket client and VaultHunters-specific commands
- **Smart Process Detection**: Accurate Java process identification (not bash wrappers) with PID display and dynamic MB/GB memory formatting
- **Real-time Log Monitoring**: Server-Sent Events (SSE) for instant log updates with `tail -F` log rotation support
- **Log Interface**: Unified log viewer with button selection (Latest, Debug, Latest Crash, System Journal), keyword search, filter and follow controls
- **Configuration Management**: Multi-category config editor with atomic file operations and automatic backups
- **Backup Management**: View and download backups from configured backup directory
- **Real-time Monitoring**: Accurate server status, player count and player names using mcstatus and process statistics
- **Security**: Custom CSRF protection, input validation, file access restrictions
- **User Context**: Run as minecraft user with direct process control (no systemd or root required)

## Dependencies

- Python 3.10+
- Flask web framework with Flask-WTF for security
- mcstatus library for Minecraft server integration
- mcrcon library for RCON console functionality
- psutil for process monitoring and management
- Bootstrap for frontend UI
- Java 17 (JDK strongly recommended) for (modded) Minecraft server execution

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
- RCON port and password: Automatically read from server.properties

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
- Server status dashboard with real-time updates every 5 seconds
- Real-time player status display

## Status Monitoring

The application provides real-time status information without historical data collection (no database required):

- **Server Status**: Running/stopped state via process detection
- **Resource Usage**: Live Java process CPU and memory usage for dashboard display
- **Player Information**: Current online player count and names via mcstatus
- **System Information**: Java version, kernel version, and basic system details

No metrics database or historical data retention is implemented. Status information is fetched only in real-time for dashboard updates.

