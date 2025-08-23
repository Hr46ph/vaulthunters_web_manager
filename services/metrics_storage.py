#!/usr/bin/env python3

import os
import sqlite3
import threading
import time
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from flask import current_app, has_app_context
import psutil

# Removed watchdog dependencies - using simple polling instead

class MetricsStorage:
    """SQLite-based metrics storage service"""
    
    def __init__(self, app=None):
        self.app = app
        self.db_path = None
        self.collection_thread = None
        self.stop_collection = False
        self._lock = threading.Lock()
        self._logger = logging.getLogger(__name__)
        
        # Player name cache for normalization (still used by startup log parser)
        self.player_name_cache = {}
        
        if app is not None:
            self.init_app(app)
    
    def _log_info(self, message: str):
        """Safely log info messages, using Flask logger if available, otherwise standard logging"""
        if has_app_context():
            current_app.logger.info(message)
        else:
            self._logger.info(message)
    
    def _log_warning(self, message: str):
        """Safely log warning messages"""
        if has_app_context():
            current_app.logger.warning(message)
        else:
            self._logger.warning(message)
    
    def _log_error(self, message: str):
        """Safely log error messages"""
        if has_app_context():
            current_app.logger.error(message)
        else:
            self._logger.error(message)
    
    def init_app(self, app):
        """Initialize the metrics storage with Flask app"""
        self.app = app
        self.db_path = app.config.get('METRICS_DATABASE_PATH', 'data/metrics.db')
        
        # Ensure data directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        # Initialize database
        self._init_database()
        
        # Run smart startup reconciliation to sync missed activity
        self._startup_reconciliation()
        
        # Start collection thread if enabled
        if app.config.get('METRICS_ENABLED', True):
            self.start_collection()
    
    def _init_database(self):
        """Initialize SQLite database with required tables"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create metrics table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    metric_type TEXT NOT NULL,
                    value REAL,
                    metadata TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create index for faster queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_metrics_timestamp_type 
                ON metrics(timestamp, metric_type)
            ''')
            
            # Create configuration table for storing runtime settings
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS metrics_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create players table for login/logout tracking
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS players (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    login_time DATETIME NOT NULL,
                    logout_time DATETIME NULL,
                    is_online BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create indexes for faster player queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_players_username 
                ON players(username)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_players_online 
                ON players(is_online)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_players_login_time 
                ON players(login_time)
            ''')
            
            # Drop legacy death tracking table if it exists (death tracking removed)
            cursor.execute('DROP TABLE IF EXISTS player_deaths')
            
            # Create app state table for tracking shutdown times and reconciliation
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS app_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            self._log_info(f'Initialized metrics database at {self.db_path}')
            
            # Note: Simple log position tracking initialized in init_app()
    
    def _startup_reconciliation(self):
        """Smart startup reconciliation to sync missed activity without duplicates"""
        try:
            self._log_info('Starting up - reconciling player sessions from downtime...')
            
            # Step 1: Close any stale online sessions first
            stale_count = self._close_stale_online_sessions()
            self._log_info(f'Closed {stale_count} stale online sessions')
            
            # Step 2: Parse logs for missed activity, but exclude currently online players
            # (real-time tracker will handle currently online players)
            from scripts.log_parser import PlayerLogParser
            
            # Get server path from TOML config
            from config import load_toml_config
            config = load_toml_config()
            server_path = config['server']['minecraft_server_path']
            log_dir = os.path.join(server_path, 'logs')
            
            if not os.path.exists(log_dir):
                self._log_warning(f'Log directory not found: {log_dir}')
                return
            
            # Get current online players to exclude from log parsing
            current_players = self._get_current_online_players()
            current_usernames = {p.get('name', '') for p in current_players} if current_players else set()
            
            parser = PlayerLogParser(self.db_path)
            results = parser.parse_all_logs_exclude_current(log_dir, exclude_players=current_usernames)
            
            self._log_info(f'Startup reconciliation complete: {results["sessions_imported"]} sessions imported, {results["sessions_skipped"]} skipped, {len(current_usernames)} current players excluded')
            
        except Exception as e:
            self._log_error(f'Startup reconciliation failed: {e}')
            # Don't fail startup if reconciliation fails
    
    def _close_stale_online_sessions(self):
        """Close sessions that are marked online but player is no longer on server"""
        try:
            # Get current online players from server
            current_players = self._get_current_online_players()
            current_usernames = {p.get('name', '') for p in current_players} if current_players else set()
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Find sessions marked as online
                cursor.execute('SELECT id, username FROM players WHERE is_online = 1')
                online_sessions = cursor.fetchall()
                
                closed_count = 0
                current_time = datetime.now()
                
                for session_id, username in online_sessions:
                    if username not in current_usernames:
                        # Player not actually online - close stale session
                        cursor.execute('''
                            UPDATE players 
                            SET is_online = 0, logout_time = ? 
                            WHERE id = ?
                        ''', (current_time, session_id))
                        closed_count += 1
                        self._log_info(f'Closed stale session for {username}')
                
                conn.commit()
                return closed_count
                
        except Exception as e:
            self._log_error(f'Failed to close stale sessions: {e}')
            return 0
    
    def _normalize_player_name(self, display_name: str) -> str:
        """Normalize player names to handle achievement titles (cached version)"""
        if display_name in self.player_name_cache:
            return self.player_name_cache[display_name]
        
        # Simple normalization - remove common title patterns
        # "Slayer MadSavage69 of the Ancients" -> "MadSavage69"
        title_patterns = [
            r'^[A-Za-z\s]+ ([A-Za-z0-9_]+) of the .+$',  # "Title Name of the Something"
            r'^[A-Za-z\s]+ ([A-Za-z0-9_]+)$',            # "Title Name"
        ]
        
        for pattern in title_patterns:
            match = re.match(pattern, display_name)
            if match:
                base_name = match.group(1)
                self.player_name_cache[display_name] = base_name
                return base_name
        
        # If no pattern matches, assume it's already a base name
        self.player_name_cache[display_name] = display_name
        return display_name
    
    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse Minecraft log timestamp format"""
        try:
            # Full format: 22Aug2025 00:16:55.377
            if len(timestamp_str) > 10 and any(month in timestamp_str for month in ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']):
                return datetime.strptime(timestamp_str, '%d%b%Y %H:%M:%S.%f')
            # Short format: 15:09:47 - use today's date
            elif ':' in timestamp_str and len(timestamp_str) <= 8:
                time_part = datetime.strptime(timestamp_str, '%H:%M:%S').time()
                return datetime.combine(datetime.now().date(), time_part)
            else:
                self._log_warning(f"Unknown timestamp format: '{timestamp_str}'")
                return datetime.now()
        except ValueError as e:
            self._log_warning(f"Failed to parse timestamp '{timestamp_str}': {e}")
            return datetime.now()
    
    def _collect_player_status_via_mcstatus(self):
        """Collect current player status using mcstatus and update database"""
        try:
            from mcstatus import JavaServer
            
            server_host = self.app.config.get('MINECRAFT_SERVER_HOST', 'localhost')
            server_port = self.app.config.get('MINECRAFT_SERVER_PORT', 25565)
            
            server = JavaServer(server_host, server_port)
            query_result = server.query()
            
            # Get current online players
            current_players = query_result.players.names or []
            
            # Normalize player names to match database format
            normalized_players = [self._normalize_player_name(name) for name in current_players]
            
            # Update player status in database
            self.update_player_status(normalized_players)
            
            return {
                'success': True,
                'player_count': query_result.players.online,
                'max_players': query_result.players.max,
                'players': current_players
            }
            
        except Exception as e:
            self._log_warning(f'Failed to collect player status via mcstatus: {e}')
            return {
                'success': False,
                'error': str(e),
                'player_count': 0,
                'max_players': 20,
                'players': []
            }
    
    # Removed death tracking - only tracking login/logout sessions now
    
    def store_metric(self, metric_type: str, value: float, metadata: Optional[Dict] = None):
        """Store a single metric in the database"""
        timestamp = datetime.now()
        metadata_json = json.dumps(metadata) if metadata else None
        
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO metrics (timestamp, metric_type, value, metadata)
                        VALUES (?, ?, ?, ?)
                    ''', (timestamp, metric_type, value, metadata_json))
                    conn.commit()
            except Exception as e:
                self._log_error(f'Failed to store metric {metric_type}: {e}')
    
    def get_metrics(self, metric_type: str, hours: int = 1) -> List[Dict]:
        """Retrieve metrics of a specific type within the specified time range"""
        start_time = datetime.now() - timedelta(hours=hours)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT timestamp, value, metadata
                    FROM metrics
                    WHERE metric_type = ? AND timestamp >= ?
                    ORDER BY timestamp ASC
                ''', (metric_type, start_time))
                
                results = []
                for row in cursor.fetchall():
                    timestamp_str, value, metadata_json = row
                    metadata = json.loads(metadata_json) if metadata_json else {}
                    results.append({
                        'timestamp': timestamp_str,
                        'value': value,
                        'metadata': metadata
                    })
                
                return results
        except Exception as e:
            self._log_error(f'Failed to retrieve metrics {metric_type}: {e}')
            return []
    
    def get_bulk_metrics(self, hours: int = 1) -> Dict[str, List[Dict]]:
        """Retrieve all metrics within the specified time range with metric-specific 300-sample optimization"""
        start_time = datetime.now() - timedelta(hours=hours)
        
        # Metric collection intervals (from _collection_worker hardcoded values)
        METRIC_INTERVALS = {
            # TPS/Lag metrics: 3-second collection (includes all server_tps_* dimension metrics)
            'tps_lag_metrics': ['server_tps', 'server_tick_time'],
            # CPU/Temperature metrics: 5-second collection  
            'cpu_temp_metrics': ['system_cpu_percent', 'system_load_1min', 'system_load_5min', 'system_load_15min', 
                               'temperature_cpu_celsius', 'temperature_gpu_celsius', 'temperature_nvme_celsius'],
            # Memory/Player metrics: 10-second collection
            'memory_player_metrics': ['system_memory_used_mb', 'system_memory_percent', 'system_swap_used_mb', 
                                    'java_memory_mb', 'java_cpu_percent', 'player_count']
        }
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get all metric types in the time range
                cursor.execute('''
                    SELECT DISTINCT metric_type FROM metrics 
                    WHERE timestamp >= ?
                ''', (start_time,))
                
                available_metrics = [row[0] for row in cursor.fetchall()]
                results = {}
                
                for metric_type in available_metrics:
                    # Determine collection interval for this metric type
                    collection_interval = self._get_metric_collection_interval(metric_type, METRIC_INTERVALS)
                    
                    # Calculate sampling strategy for 300-sample target
                    sampling_strategy = self._calculate_sampling_strategy(hours, collection_interval)
                    
                    if sampling_strategy['skip_rows'] <= 1:
                        # No sampling needed - return all data (include metadata for dimension TPS metrics)
                        if metric_type.startswith('server_tps_'):
                            cursor.execute('''
                                SELECT timestamp, value, metadata FROM metrics
                                WHERE metric_type = ? AND timestamp >= ?
                                ORDER BY timestamp ASC
                            ''', (metric_type, start_time))
                        else:
                            cursor.execute('''
                                SELECT timestamp, value FROM metrics
                                WHERE metric_type = ? AND timestamp >= ?
                                ORDER BY timestamp ASC
                            ''', (metric_type, start_time))
                    else:
                        # Apply row-based sampling to get ~300 samples (include metadata for dimension TPS metrics)
                        if metric_type.startswith('server_tps_'):
                            cursor.execute('''
                                SELECT timestamp, value, metadata FROM (
                                    SELECT timestamp, value, metadata,
                                           ROW_NUMBER() OVER (ORDER BY timestamp ASC) as row_num
                                    FROM metrics
                                    WHERE metric_type = ? AND timestamp >= ?
                                ) WHERE (row_num - 1) % ? = 0
                                ORDER BY timestamp ASC
                            ''', (metric_type, start_time, sampling_strategy['skip_rows']))
                        else:
                            cursor.execute('''
                                SELECT timestamp, value FROM (
                                    SELECT timestamp, value, 
                                           ROW_NUMBER() OVER (ORDER BY timestamp ASC) as row_num
                                    FROM metrics
                                    WHERE metric_type = ? AND timestamp >= ?
                                ) WHERE (row_num - 1) % ? = 0
                                ORDER BY timestamp ASC
                            ''', (metric_type, start_time, sampling_strategy['skip_rows']))
                    
                    # Store results for this metric type
                    results[metric_type] = []
                    for row in cursor.fetchall():
                        if metric_type.startswith('server_tps_') and len(row) == 3:
                            # Include metadata for dimension TPS metrics
                            timestamp_str, value, metadata_str = row
                            try:
                                import json
                                metadata = json.loads(metadata_str) if metadata_str else {}
                            except:
                                metadata = {}
                            results[metric_type].append({
                                'timestamp': timestamp_str,
                                'value': round(value, 2) if value is not None else None,
                                'metadata': metadata
                            })
                        else:
                            # Standard metrics without metadata
                            timestamp_str, value = row
                            results[metric_type].append({
                                'timestamp': timestamp_str,
                                'value': round(value, 2) if value is not None else None
                            })
                
                return results
        except Exception as e:
            self._log_error(f'Failed to retrieve bulk metrics: {e}')
            return {}
    
    def _get_metric_collection_interval(self, metric_type: str, metric_intervals: Dict) -> int:
        """Determine collection interval for a metric type"""
        # Special handling for dynamic dimension TPS metrics (server_tps_*)
        if metric_type.startswith('server_tps_'):
            return 3  # All dimension TPS metrics: 3 seconds
            
        for interval_type, metrics in metric_intervals.items():
            if metric_type in metrics or any(metric_type.startswith(m) for m in metrics):
                if interval_type == 'tps_lag_metrics':
                    return 3  # TPS/Lag: 3 seconds
                elif interval_type == 'cpu_temp_metrics':
                    return 5  # CPU/Temperature: 5 seconds 
                elif interval_type == 'memory_player_metrics':
                    return 10  # Memory/Player: 10 seconds
        
        # Default to 10 seconds for unknown metrics
        return 10
    
    def _calculate_sampling_strategy(self, hours: int, collection_interval: int) -> Dict:
        """Calculate sampling strategy to achieve ~300 samples per metric"""
        # Calculate expected raw data points
        total_seconds = hours * 3600
        expected_points = total_seconds // collection_interval
        
        # Target 300 samples maximum
        if expected_points <= 300:
            return {'skip_rows': 1, 'expected_samples': expected_points}
        else:
            # Calculate skip_rows to get as close to 300 as possible
            skip_rows = max(1, round(expected_points / 300))
            expected_samples = expected_points // skip_rows
            return {'skip_rows': skip_rows, 'expected_samples': expected_samples}
    
    def get_latest_metric(self, metric_type: str) -> Optional[Dict]:
        """Get the most recent metric of a specific type"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT timestamp, value, metadata
                    FROM metrics
                    WHERE metric_type = ?
                    ORDER BY timestamp DESC
                    LIMIT 1
                ''', (metric_type,))
                
                row = cursor.fetchone()
                if row:
                    timestamp_str, value, metadata_json = row
                    metadata = json.loads(metadata_json) if metadata_json else {}
                    return {
                        'timestamp': timestamp_str,
                        'value': value,
                        'metadata': metadata
                    }
                return None
        except Exception as e:
            self._log_error(f'Failed to get latest metric {metric_type}: {e}')
            return None
    
    def cleanup_old_metrics(self):
        """Remove metrics older than 3 days (hardcoded retention)"""
        retention_days = 3  # Hardcoded 3-day retention for server management tool
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        DELETE FROM metrics WHERE timestamp < ?
                    ''', (cutoff_date,))
                    deleted_count = cursor.rowcount
                    conn.commit()
                    
                    if deleted_count > 0:
                        self._log_info(f'Cleaned up {deleted_count} old metrics')
            except Exception as e:
                self._log_error(f'Failed to cleanup old metrics: {e}')
    
    def _collect_server_tps_safe(self) -> Optional[Dict]:
        """Safely collect server TPS data via RCON without blocking the metrics thread"""
        try:
            # Get server configuration for RCON connection
            server_host = self.app.config.get('MINECRAFT_SERVER_HOST', 'localhost')
            
            # Get RCON port and password from server.properties
            rcon_port = self._get_rcon_port()
            if not rcon_port:
                return None
            
            rcon_password = self._get_rcon_password()
            if not rcon_password:
                return None
            
            # Create isolated RCON client with very short timeout for metrics collection
            from services.rcon_client import RconClient
            rcon = RconClient(server_host, rcon_port, rcon_password, timeout=3.0, max_retries=1)
            
            # Quick connect and execute
            rcon.connect()
            response = rcon.command("forge tps", auto_reconnect=False)
            rcon.disconnect()
            
            # Parse TPS data from response
            return self._parse_forge_tps_response(response)
            
        except Exception as e:
            # Log warning but don't let RCON failures break metrics collection
            self._log_warning(f'RCON TPS collection failed (this is non-critical): {e}')
            return None
    
    def _get_rcon_port(self) -> Optional[int]:
        """Get RCON port from server.properties or config"""
        try:
            # Try config first
            config_rcon_port = self.app.config.get('RCON_PORT')
            if config_rcon_port:
                return int(config_rcon_port)
            
            # Try reading from server.properties
            server_path = self.app.config.get('MINECRAFT_SERVER_PATH')
            if server_path:
                props_file = os.path.join(server_path, 'server.properties')
                if os.path.exists(props_file):
                    with open(props_file, 'r') as f:
                        for line in f:
                            if line.startswith('rcon.port='):
                                return int(line.split('=')[1].strip())
            
            return None
        except Exception:
            return None
    
    def _get_rcon_password(self) -> Optional[str]:
        """Get RCON password from server.properties"""
        try:
            # Try config first (though it's usually not stored there for security)
            config_password = self.app.config.get('RCON_PASSWORD')
            if config_password:
                return config_password
            
            # Read from server.properties
            server_path = self.app.config.get('MINECRAFT_SERVER_PATH')
            if server_path:
                props_file = os.path.join(server_path, 'server.properties')
                if os.path.exists(props_file):
                    with open(props_file, 'r') as f:
                        for line in f:
                            if line.startswith('rcon.password='):
                                password = line.split('=', 1)[1].strip()
                                return password if password else None
            
            return None
        except Exception:
            return None
    
    def _parse_forge_tps_response(self, response: str) -> Optional[Dict]:
        """Parse /forge tps response to extract dimension TPS data"""
        if not response:
            return None
        
        try:
            dimensions = {}
            overall_tps = 20.0  # Default fallback
            overall_tick_time = 50.0  # Default fallback (50ms = 20 TPS)
            
            lines = response.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Look for dimension TPS lines like:
                # "Dim minecraft:overworld (minecraft:overworld): Mean tick time: 0.654 ms. Mean TPS: 20.000"
                # "Overall: Mean tick time: 0.896 ms. Mean TPS: 20.000"
                
                if 'Mean tick time:' in line and 'Mean TPS:' in line:
                    try:
                        # Extract tick time and TPS
                        tick_time_part = line.split('Mean tick time:')[1].split('ms')[0].strip()
                        tps_part = line.split('Mean TPS:')[1].strip()
                        
                        tick_time = float(tick_time_part)
                        tps = float(tps_part)
                        
                        if line.startswith('Overall:'):
                            overall_tps = tps
                            overall_tick_time = tick_time
                        elif line.startswith('Dim '):
                            # Extract dimension info from "Dim minecraft:overworld (minecraft:overworld): Mean tick time..."
                            # Use the FIRST part (before parentheses) as the unique dimension identifier
                            if ':' in line and '(' in line:
                                # Extract the dimension name before parentheses
                                # Format: "Dim minecraft:overworld (minecraft:overworld): Mean tick time..."
                                dim_part = line.split('(')[0].strip()  # "Dim minecraft:overworld"
                                if dim_part.startswith('Dim '):
                                    dim_name = dim_part[4:].strip()  # Remove "Dim " prefix
                                    # Clean dimension name but preserve uniqueness
                                    dim_name = dim_name.replace('minecraft:', '').replace('the_vault:', '').replace('ae2:', '').replace(':', '_')
                                    dimensions[dim_name] = {
                                        'tps': tps,
                                        'mean_tick_time': tick_time
                                    }
                    except (ValueError, IndexError) as e:
                        self._log_warning(f'Failed to parse TPS line "{line}": {e}')
                        continue
            
            # Return data if we found any TPS information
            found_tps_data = False
            
            # Check if we parsed any lines with TPS data
            for line in lines:
                if 'Mean tick time:' in line and 'Mean TPS:' in line:
                    found_tps_data = True
                    break
            
            if found_tps_data:
                return {
                    'overall_tps': overall_tps,
                    'overall_tick_time': overall_tick_time,
                    'dimensions': dimensions
                }
            
            return None
            
        except Exception as e:
            self._log_warning(f'Failed to parse forge tps response: {e}')
            return None

    def collect_system_metrics(self):
        """Collect current system metrics"""
        config = self.app.config
        
        try:
            # System memory
            if config.get('METRICS_COLLECT_SYSTEM_MEMORY', True):
                memory = psutil.virtual_memory()
                self.store_metric('system_memory_used_mb', memory.used / (1024**2))
                self.store_metric('system_memory_percent', memory.percent)
                
                # Store detailed memory breakdown if available
                if hasattr(memory, 'buffers') and hasattr(memory, 'cached'):
                    self.store_metric('system_memory_buffers_mb', memory.buffers / (1024**2))
                    self.store_metric('system_memory_cache_mb', memory.cached / (1024**2))
                
                # Swap memory
                swap = psutil.swap_memory()
                self.store_metric('system_swap_used_mb', swap.used / (1024**2))
                self.store_metric('system_swap_percent', swap.percent)
            
            # System CPU
            if config.get('METRICS_COLLECT_SYSTEM_CPU', True):
                cpu_percent = psutil.cpu_percent(interval=None)
                self.store_metric('system_cpu_percent', cpu_percent)
                
                # Per-core CPU usage
                cpu_per_core = psutil.cpu_percent(percpu=True, interval=None)
                for i, core_usage in enumerate(cpu_per_core):
                    self.store_metric(f'system_cpu_core_{i}_percent', core_usage)
            
            # System load
            if config.get('METRICS_COLLECT_SYSTEM_LOAD', True):
                try:
                    load_avg = os.getloadavg()
                    self.store_metric('system_load_1min', load_avg[0])
                    self.store_metric('system_load_5min', load_avg[1])
                    self.store_metric('system_load_15min', load_avg[2])
                except (OSError, AttributeError):
                    pass  # getloadavg not available on all platforms
            
            # Java process metrics
            if config.get('METRICS_COLLECT_JAVA_PROCESS', True):
                try:
                    from services.system_control import SystemControlService
                    system_control = SystemControlService()
                    status = system_control.get_server_status()
                    
                    if status.get('running'):
                        if status.get('memory_usage'):
                            self.store_metric('java_memory_mb', status['memory_usage'])
                        if status.get('cpu_usage'):
                            self.store_metric('java_cpu_percent', status['cpu_usage'])
                        if status.get('pid'):
                            self.store_metric('java_pid', status['pid'])
                except Exception as e:
                    self._log_warning(f'Failed to collect Java process metrics: {e}')
            
            # Server TPS via RCON
            if config.get('METRICS_COLLECT_SERVER_TPS', True):
                try:
                    tps_data = self._collect_server_tps_safe()
                    if tps_data:
                        self.store_metric('server_tps', tps_data['overall_tps'], {
                            'source': 'rcon_forge_tps',
                            'dimensions': tps_data['dimensions']
                        })
                        
                        # Store individual dimension TPS
                        for dim_name, dim_data in tps_data['dimensions'].items():
                            self.store_metric(f'server_tps_{dim_name}', dim_data['tps'], {
                                'source': 'rcon_forge_tps',
                                'dimension': dim_name,
                                'mean_tick_time': dim_data['mean_tick_time']
                            })
                    else:
                        # Fallback to placeholder when RCON fails
                        self.store_metric('server_tps', 20.0, {'source': 'placeholder_rcon_failed'})
                except Exception as e:
                    self._log_warning(f'Failed to collect server TPS via RCON: {e}')
                    # Store placeholder on any error to keep metrics consistent
                    self.store_metric('server_tps', 20.0, {'source': 'placeholder_rcon_error'})
            
            
            # Hardware temperature monitoring
            if config.get('METRICS_COLLECT_TEMPERATURE', True):
                try:
                    from services.temperature_monitor import get_temperature_monitor
                    temp_monitor = get_temperature_monitor()
                    readings = temp_monitor.get_temperature_readings()
                    
                    if readings.get('status') == 'success':
                        # Store CPU temperature
                        if readings.get('cpu'):
                            self.store_metric('temperature_cpu_celsius', readings['cpu']['current'], {
                                'sensor': readings['cpu']['sensor'],
                                'label': readings['cpu']['label'],
                                'high_threshold': readings['cpu']['high'],
                                'critical_threshold': readings['cpu']['critical']
                            })
                        
                        # Store GPU temperature
                        if readings.get('gpu'):
                            self.store_metric('temperature_gpu_celsius', readings['gpu']['current'], {
                                'sensor': readings['gpu']['sensor'],
                                'label': readings['gpu']['label'],
                                'high_threshold': readings['gpu']['high'],
                                'critical_threshold': readings['gpu']['critical']
                            })
                        
                        # Store NVMe temperature (composite)
                        if readings.get('nvme', {}).get('composite'):
                            nvme_data = readings['nvme']['composite']
                            self.store_metric('temperature_nvme_celsius', nvme_data['current'], {
                                'sensor': nvme_data['sensor'],
                                'label': nvme_data['label'],
                                'high_threshold': nvme_data['high'],
                                'critical_threshold': nvme_data['critical']
                            })
                        
                        # Store NVMe Sensor 1 temperature if available
                        if readings.get('nvme', {}).get('sensor1'):
                            nvme_sensor1 = readings['nvme']['sensor1']
                            self.store_metric('temperature_nvme_sensor1_celsius', nvme_sensor1['current'], {
                                'sensor': nvme_sensor1['sensor'],
                                'label': nvme_sensor1['label'],
                                'high_threshold': nvme_sensor1['high'],
                                'critical_threshold': nvme_sensor1['critical']
                            })
                    else:
                        self._log_warning(f"Temperature reading failed: {readings.get('error', 'Unknown error')}")
                except Exception as e:
                    self._log_warning(f'Failed to collect temperature data: {e}')
                
        except Exception as e:
            self._log_error(f'Failed to collect system metrics: {e}')
    
    def collect_cpu_and_temperature_metrics(self):
        """Collect CPU and temperature metrics (5-second interval)"""
        try:
            # System CPU
            cpu_percent = psutil.cpu_percent(interval=None)
            self.store_metric('system_cpu_percent', cpu_percent)
            
            # Per-core CPU usage
            cpu_per_core = psutil.cpu_percent(percpu=True, interval=None)
            for i, core_usage in enumerate(cpu_per_core):
                self.store_metric(f'system_cpu_core_{i}_percent', core_usage)
            
            # System load
            try:
                load_avg = os.getloadavg()
                self.store_metric('system_load_1min', load_avg[0])
                self.store_metric('system_load_5min', load_avg[1])
                self.store_metric('system_load_15min', load_avg[2])
            except (OSError, AttributeError):
                pass  # getloadavg not available on all platforms
            
            # Hardware temperature monitoring
            try:
                from services.temperature_monitor import get_temperature_monitor
                temp_monitor = get_temperature_monitor()
                readings = temp_monitor.get_temperature_readings()
                
                if readings.get('status') == 'success':
                    # Store CPU temperature
                    if readings.get('cpu'):
                        self.store_metric('temperature_cpu_celsius', readings['cpu']['current'], {
                            'sensor': readings['cpu']['sensor'],
                            'label': readings['cpu']['label'],
                            'high_threshold': readings['cpu']['high'],
                            'critical_threshold': readings['cpu']['critical']
                        })
                    
                    # Store GPU temperature
                    if readings.get('gpu'):
                        self.store_metric('temperature_gpu_celsius', readings['gpu']['current'], {
                            'sensor': readings['gpu']['sensor'],
                            'label': readings['gpu']['label'],
                            'high_threshold': readings['gpu']['high'],
                            'critical_threshold': readings['gpu']['critical']
                        })
                    
                    # Store NVMe temperature (composite and individual sensors)
                    if readings.get('nvme', {}).get('composite'):
                        self.store_metric('temperature_nvme_celsius', readings['nvme']['composite']['current'], {
                            'sensor': 'nvme_composite',
                            'label': readings['nvme']['composite']['label'],
                            'high_threshold': readings['nvme']['composite']['high'],
                            'critical_threshold': readings['nvme']['composite']['critical']
                        })
                    
                    # Additional NVMe sensor readings
                    if readings.get('nvme', {}).get('sensors'):
                        for i, sensor in enumerate(readings['nvme']['sensors'], 1):
                            self.store_metric(f'temperature_nvme_sensor{i}_celsius', sensor['current'], {
                                'sensor': sensor['sensor'],
                                'label': sensor['label']
                            })
            except Exception as e:
                self._log_warning(f'Failed to collect temperature metrics: {e}')
        
        except Exception as e:
            self._log_error(f'Failed to collect CPU and temperature metrics: {e}')
    
    def collect_memory_metrics(self):
        """Collect memory metrics (10-second interval)"""
        try:
            # System memory
            memory = psutil.virtual_memory()
            self.store_metric('system_memory_used_mb', memory.used / (1024**2))
            self.store_metric('system_memory_percent', memory.percent)
            
            # Store detailed memory breakdown if available
            if hasattr(memory, 'buffers') and hasattr(memory, 'cached'):
                self.store_metric('system_memory_buffers_mb', memory.buffers / (1024**2))
                self.store_metric('system_memory_cache_mb', memory.cached / (1024**2))
            
            # Swap memory
            swap = psutil.swap_memory()
            self.store_metric('system_swap_used_mb', swap.used / (1024**2))
            self.store_metric('system_swap_percent', swap.percent)
            
            # Java process metrics
            try:
                from services.system_control import SystemControlService
                system_control = SystemControlService()
                status = system_control.get_server_status()
                
                if status.get('running'):
                    if status.get('memory_usage'):
                        self.store_metric('java_memory_mb', status['memory_usage'])
                    if status.get('cpu_usage'):
                        self.store_metric('java_cpu_percent', status['cpu_usage'])
                    if status.get('pid'):
                        self.store_metric('java_pid', status['pid'])
            except Exception as e:
                self._log_warning(f'Failed to collect Java process metrics: {e}')
            
        
        except Exception as e:
            self._log_error(f'Failed to collect memory metrics: {e}')
    
    def collect_tps_and_lag_metrics(self):
        """Collect TPS and lag spike metrics (3-second interval)"""
        try:
            # Server TPS via RCON
            try:
                tps_data = self._collect_server_tps_safe()
                if tps_data:
                    self.store_metric('server_tps', tps_data['overall_tps'], {
                        'source': 'rcon_forge_tps',
                        'dimensions': tps_data['dimensions'],
                        'overall_tick_time': tps_data['overall_tick_time']
                    })
                    
                    # Store overall mean tick time as separate metric for charting
                    self.store_metric('server_tick_time', tps_data['overall_tick_time'], {
                        'source': 'rcon_forge_tps'
                    })
                    
                    # Store individual dimension TPS
                    for dim_name, dim_data in tps_data['dimensions'].items():
                        self.store_metric(f'server_tps_{dim_name}', dim_data['tps'], {
                            'source': 'rcon_forge_tps',
                            'dimension': dim_name,
                            'mean_tick_time': dim_data['mean_tick_time']
                        })
                else:
                    # Fallback to placeholder when RCON fails
                    self.store_metric('server_tps', 20.0, {'source': 'placeholder_rcon_failed'})
            except Exception as e:
                self._log_warning(f'Failed to collect server TPS via RCON: {e}')
                # Store placeholder on any error to keep metrics consistent
                self.store_metric('server_tps', 20.0, {'source': 'placeholder_rcon_error'})
            
            # Player count via mcstatus (fast and accurate) - moved to 3-second cycle
            try:
                player_status = self._collect_player_status_via_mcstatus()
                
                if player_status['success']:
                    self.store_metric('player_count', player_status['player_count'], {
                        'source': 'mcstatus_query',
                        'max_players': player_status['max_players'],
                        'player_names': player_status['players'],
                        'server_running': True
                    })
                else:
                    # Server likely offline or unreachable
                    self.store_metric('player_count', 0, {
                        'source': 'mcstatus_failed',
                        'error': player_status.get('error', 'Unknown error'),
                        'server_running': False
                    })
                    
            except Exception as e:
                self._log_warning(f'Failed to collect player count via mcstatus: {e}')
                self.store_metric('player_count', 0, {
                    'source': 'error',
                    'error': str(e)
                })
        
        except Exception as e:
            self._log_error(f'Failed to collect TPS and lag metrics: {e}')
    
    def _collection_worker(self):
        """Background thread worker for metric collection with staggered intervals per metric type"""
        # Hardcoded collection intervals (in seconds)
        COLLECTION_INTERVALS = {
            # High volatility - CPU and temperature metrics (5s)
            'cpu_temp_interval': 5,
            # Moderate change - Memory metrics only (10s) 
            'memory_interval': 10,
            # Critical performance - TPS, lag spikes, and player count (3s)
            'tps_lag_player_interval': 3
        }
        
        last_collection = {
            'cpu_temp': 0,
            'memory': 0, 
            'tps_lag_player': 0
        }
        
        while not self.stop_collection:
            try:
                with self.app.app_context():
                    current_time = time.time()
                    
                    # Check if it's time to collect each metric group
                    if current_time - last_collection['cpu_temp'] >= COLLECTION_INTERVALS['cpu_temp_interval']:
                        self.collect_cpu_and_temperature_metrics()
                        last_collection['cpu_temp'] = current_time
                    
                    if current_time - last_collection['memory'] >= COLLECTION_INTERVALS['memory_interval']:
                        self.collect_memory_metrics()
                        last_collection['memory'] = current_time
                    
                    if current_time - last_collection['tps_lag_player'] >= COLLECTION_INTERVALS['tps_lag_player_interval']:
                        self.collect_tps_and_lag_metrics()
                        last_collection['tps_lag_player'] = current_time
                    
                    # Cleanup old metrics and player data every hour (check every 60 seconds)
                    if int(current_time) % 3600 < 60:
                        self.cleanup_old_metrics()
                        self.cleanup_old_player_data()
                
            except Exception as e:
                self._log_error(f'Error in metrics collection: {e}')
            
            # Sleep for 1 second (shortest interval check)
            time.sleep(1)
    
    def start_collection(self):
        """Start the background metrics collection thread"""
        if self.collection_thread is not None and self.collection_thread.is_alive():
            self._log_warning('Metrics collection already running')
            return
        
        self.stop_collection = False
        self.collection_thread = threading.Thread(target=self._collection_worker, daemon=True)
        self.collection_thread.start()
        self._log_info('Started metrics collection thread')
    
    def stop_collection_thread(self):
        """Stop the background metrics collection thread"""
        if self.collection_thread is not None:
            self.stop_collection = True
            self.collection_thread.join(timeout=5)
            self._log_info('Stopped metrics collection thread')
    
    def get_config_value(self, key: str, default: Any = None) -> Any:
        """Get a configuration value from the database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT value FROM metrics_config WHERE key = ?', (key,))
                row = cursor.fetchone()
                if row:
                    return json.loads(row[0])
                return default
        except Exception as e:
            self._log_error(f'Failed to get config value {key}: {e}')
            return default
    
    def set_config_value(self, key: str, value: Any):
        """Set a configuration value in the database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO metrics_config (key, value, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                ''', (key, json.dumps(value)))
                conn.commit()
        except Exception as e:
            self._log_error(f'Failed to set config value {key}: {e}')
    
    def update_player_status(self, current_players: List[str]):
        """Update player login/logout status based on current online players"""
        current_time = datetime.now()
        
        with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    # Get currently online players from database
                    cursor.execute('SELECT username FROM players WHERE is_online = 1')
                    db_online_players = set(row[0] for row in cursor.fetchall())
                    
                    current_player_set = set(current_players)
                    
                    # Find players who just logged in
                    new_players = current_player_set - db_online_players
                    for username in new_players:
                        # Mark any previous sessions as offline first
                        cursor.execute('''
                            UPDATE players 
                            SET is_online = 0, logout_time = ?, updated_at = ?
                            WHERE username = ? AND is_online = 1
                        ''', (current_time, current_time, username))
                        
                        # Check if a session with similar login time already exists (within 10 seconds)
                        cursor.execute('''
                            SELECT id FROM players 
                            WHERE username = ? 
                            AND ABS(julianday(?) - julianday(login_time)) * 24 * 60 * 60 <= 10
                        ''', (username, current_time))
                        
                        # Only insert if no session exists within 10 seconds of this login time
                        if not cursor.fetchone():
                            cursor.execute('''
                                INSERT INTO players (username, login_time, is_online)
                                VALUES (?, ?, 1)
                            ''', (username, current_time))
                    
                    # Find players who just logged out
                    logged_out_players = db_online_players - current_player_set
                    for username in logged_out_players:
                        cursor.execute('''
                            UPDATE players 
                            SET is_online = 0, logout_time = ?, updated_at = ?
                            WHERE username = ? AND is_online = 1
                        ''', (current_time, current_time, username))
                    
                    conn.commit()
                    
                    if new_players:
                        self._log_info(f'Players logged in: {", ".join(new_players)}')
                    if logged_out_players:
                        self._log_info(f'Players logged out: {", ".join(logged_out_players)}')
                        
            except Exception as e:
                self._log_error(f'Failed to update player status: {e}')
    
    def get_players_status(self, hours: int = None) -> Dict:
        """Get player login/logout status for all players (ignores hours parameter for backward compatibility)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get ALL player sessions (no time restriction)
                cursor.execute('''
                    SELECT username, login_time, logout_time, is_online
                    FROM players 
                    ORDER BY login_time DESC
                ''')
                
                players_data = []
                online_players = []
                offline_players = []
                
                for row in cursor.fetchall():
                    username, login_time_str, logout_time_str, is_online = row
                    
                    player_info = {
                        'username': username,
                        'login_time': login_time_str,
                        'logout_time': logout_time_str,
                        'is_online': bool(is_online)
                    }
                    
                    players_data.append(player_info)
                    
                    if is_online:
                        online_players.append(player_info)
                    else:
                        offline_players.append(player_info)
                
                # Get unique players (latest session for each)
                unique_players = {}
                for player in players_data:
                    username = player['username']
                    if username not in unique_players or player['login_time'] > unique_players[username]['login_time']:
                        unique_players[username] = player
                
                return {
                    'online_players': online_players,
                    'offline_players': offline_players,
                    'all_sessions': players_data,
                    'unique_players': list(unique_players.values()),
                    'total_online': len(online_players),
                    'total_sessions': len(players_data)
                }
                
        except Exception as e:
            self._log_error(f'Failed to get players status: {e}')
            return {
                'online_players': [],
                'offline_players': [],
                'all_sessions': [],
                'unique_players': [],
                'total_online': 0,
                'total_sessions': 0
            }
    
    def cleanup_old_player_data(self):
        """DISABLED: Player login/logout history is preserved forever"""
        # Player data is intentionally preserved forever to maintain complete server history
        self._log_info('Player cleanup skipped - preserving all historical login/logout data')
        return
    
    def remove_duplicate_sessions(self):
        """Remove duplicate player sessions based on username and similar login_time (within 1 second)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get all sessions ordered by username and login_time
                cursor.execute('''
                    SELECT id, username, login_time, logout_time, is_online
                    FROM players
                    ORDER BY username, login_time
                ''')
                
                sessions = cursor.fetchall()
                to_delete = []
                total_removed = 0
                
                i = 0
                while i < len(sessions):
                    current_session = sessions[i]
                    current_id, username, login_time_str, logout_time_str, is_online = current_session
                    
                    # Parse current login time
                    try:
                        current_login = datetime.fromisoformat(login_time_str)
                    except:
                        i += 1
                        continue
                    
                    # Look for duplicates within 1 second
                    duplicates = [current_session]
                    j = i + 1
                    
                    while j < len(sessions) and sessions[j][1] == username:  # Same username
                        next_session = sessions[j]
                        next_id, _, next_login_str, _, _ = next_session
                        
                        try:
                            next_login = datetime.fromisoformat(next_login_str)
                            # If within 1 second, it's a duplicate
                            if abs((next_login - current_login).total_seconds()) <= 1:
                                duplicates.append(next_session)
                                j += 1
                            else:
                                break
                        except:
                            j += 1
                    
                    # If we found duplicates, keep the one with the highest ID and mark others for deletion
                    if len(duplicates) > 1:
                        duplicates.sort(key=lambda x: x[0], reverse=True)  # Sort by ID desc
                        keep_session = duplicates[0]
                        delete_sessions = duplicates[1:]
                        
                        for delete_session in delete_sessions:
                            to_delete.append(delete_session[0])  # Add ID to deletion list
                        
                        self._log_info(f"Found {len(duplicates)} duplicate sessions for {username} at {login_time_str}, keeping ID {keep_session[0]}")
                    
                    i = j  # Move to next group
                
                # Delete duplicates
                for session_id in to_delete:
                    cursor.execute('DELETE FROM players WHERE id = ?', (session_id,))
                    total_removed += 1
                
                conn.commit()
                self._log_info(f"Cleaned up {total_removed} duplicate player sessions")
                return total_removed
                
        except Exception as e:
            self._log_error(f'Failed to remove duplicate sessions: {e}')
            return 0
    

# Global instance
metrics_storage = MetricsStorage()