# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VaultHunter Web Manager is a Flask-based web application for managing VaultHunter Minecraft servers. It provides server control, log monitoring, configuration management, and backup downloads through a Bootstrap-based web interface.

## Current Status

**IMPLEMENTATION COMPLETE** - The VaultHunter Web Manager is fully implemented with all planned features plus additional enhancements:

- ✅ Complete Flask application with direct process management system
- ✅ Dashboard with accurate real-time player counts and process monitoring
- ✅ Full RCON console with secure modal authentication (threading issues resolved)
- ✅ Enhanced log monitoring with 3 separate content windows and crash report dropdown
- ✅ Multi-category configuration editor with atomic file operations
- ✅ Backup management system with download and inspection
- ✅ Dark mode support and responsive Bootstrap design
- ✅ Direct Minecraft server process control (no systemd dependency)

## Architecture (Implemented)

Direct process management architecture with enhanced features:

- **Flask Application** (`app.py`): Main web server with routes for server control, log viewing, config editing, backup management, and RCON console
- **Configuration** (`config.py.example`): Configuration template with Java/JVM settings, server paths, web interface settings, and Minecraft connection details
- **Process Management** (`services/system_control.py`): Direct Java process launching, monitoring, and control with psutil integration
- **Templates** (`templates/`): Jinja2 templates with enhanced logs page (3 content windows) and crash report dropdown selector
- **Static Files** (`static/`): CSS and JavaScript for Bootstrap-based responsive UI with RCON functionality
- **Requirements** (`requirements.txt`): Python dependencies including Flask, mcstatus, mcrcon, and psutil

## Key Implementation Requirements

- **Server Control**: Direct Java process management for VaultHunter server start/stop/restart with real-time monitoring
- **RCON Console**: Full server console access with secure modal authentication and threading compatibility
- **Log Monitoring**: Enhanced 3-window log viewer (latest/debug/crash) with individual controls and crash report dropdown
- **Configuration Management**: Multi-category config editor with atomic file operations and automatic backups
- **Backup Management**: List, download, and inspect backups from configured backup directory
- **Real-time Monitoring**: Accurate server status and player counts using mcstatus and process statistics
- **Security**: Session-based auth, CSRF protection, input validation, file access restrictions
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

- Minecraft server: `/home/minecraft/vaulthunter` (configurable)
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
- For production: systemd service `vaulthunter_web_manager.service` uses `./venv/bin/python app.py`
- Server control: Direct process management (no separate systemd service needed for Minecraft)

## Implementation Reference

See `IMPLEMENTATION_PLAN.md` for detailed development phases and technical considerations. 

**VERIFIED IMPLEMENTATION POINTS:**
- ✅ Direct Java process management - IMPLEMENTED in `services/system_control.py` with psutil integration
- ✅ Atomic file writes for config edits - IMPLEMENTED in `services/config_manager.py`
- ✅ CSRF protection and input validation - IMPLEMENTED with Flask-WTF across all routes
- ✅ AJAX for real-time server status updates - IMPLEMENTED in `static/js/app.js`
- ✅ Enhanced log viewing with 3-window interface - IMPLEMENTED in `services/log_service.py`
- ✅ RCON threading compatibility resolved - IMPLEMENTED with direct process management
- ✅ Production-ready security and error handling - IMPLEMENTED throughout all services

**STATUS:** 🎉 **PRODUCTION READY - ALL FEATURES VERIFIED FUNCTIONAL**