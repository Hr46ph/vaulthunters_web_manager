#!/usr/bin/env python3

import os
import sqlite3
import threading
import time
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from flask import current_app, has_app_context
import psutil

class MetricsStorage:
    """SQLite-based metrics storage service"""
    
    def __init__(self, app=None):
        self.app = app
        self.db_path = None
        self.collection_thread = None
        self.stop_collection = False
        self._lock = threading.Lock()
        self._logger = logging.getLogger(__name__)
        
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
            
            conn.commit()
            self._log_info(f'Initialized metrics database at {self.db_path}')
    
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
        """Remove metrics older than the retention period"""
        retention_days = self.app.config.get('METRICS_RETENTION_DAYS', 7)
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
            server_host = self.app.config.get('SERVER_HOST', 'localhost')
            rcon_password = self.app.config.get('RCON_PASSWORD')
            
            if not rcon_password:
                return None
            
            # Get RCON port from server.properties or config
            rcon_port = self._get_rcon_port()
            if not rcon_port:
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
            server_path = self.app.config.get('SERVER_PATH')
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
    
    def _parse_forge_tps_response(self, response: str) -> Optional[Dict]:
        """Parse /forge tps response to extract dimension TPS data"""
        if not response:
            return None
        
        try:
            dimensions = {}
            overall_tps = 20.0  # Default fallback
            
            lines = response.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Look for dimension TPS lines like:
                # "Dim  0 (minecraft:overworld): Mean tick time: 47.778 ms. Mean TPS: 20.000"
                # "Overall: Mean tick time: 47.778 ms. Mean TPS: 20.000"
                
                if 'Mean tick time:' in line and 'Mean TPS:' in line:
                    try:
                        # Extract tick time and TPS
                        tick_time_part = line.split('Mean tick time:')[1].split('ms')[0].strip()
                        tps_part = line.split('Mean TPS:')[1].strip()
                        
                        tick_time = float(tick_time_part)
                        tps = float(tps_part)
                        
                        if line.startswith('Overall:'):
                            overall_tps = tps
                        elif line.startswith('Dim '):
                            # Extract dimension info from "Dim  0 (minecraft:overworld): Mean tick time..."
                            if '(' in line and ')' in line:
                                # Extract the part between parentheses
                                paren_start = line.index('(')
                                paren_end = line.index(')')
                                dim_name = line[paren_start+1:paren_end]
                                # Clean dimension name
                                dim_name = dim_name.replace('minecraft:', '').replace('the_vault:', '').replace(':', '_')
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
            
            # Player count from server status
            if config.get('METRICS_COLLECT_PLAYER_COUNT', True):
                try:
                    from services.system_control import SystemControlService
                    system_control = SystemControlService()
                    status = system_control.get_server_status()
                    
                    if status.get('running') and status.get('players') is not None:
                        player_count = status.get('players', 0)
                        max_players = status.get('max_players', 20)
                        self.store_metric('player_count', player_count, {
                            'source': 'mcstatus',
                            'max_players': max_players,
                            'server_running': True
                        })
                    else:
                        # Server is not running or player data unavailable
                        self.store_metric('player_count', 0, {
                            'source': 'server_offline',
                            'server_running': False
                        })
                except Exception as e:
                    self._log_warning(f'Failed to collect player count: {e}')
                    # Store 0 with error info on failure
                    self.store_metric('player_count', 0, {
                        'source': 'error',
                        'error': str(e)
                    })
                
        except Exception as e:
            self._log_error(f'Failed to collect system metrics: {e}')
    
    def _collection_worker(self):
        """Background thread worker for metric collection"""
        while not self.stop_collection:
            try:
                with self.app.app_context():
                    # Check for updated collection interval from database
                    stored_interval = self.get_config_value('collection_interval')
                    if stored_interval:
                        interval = stored_interval
                    else:
                        interval = self.app.config.get('METRICS_COLLECTION_INTERVAL', 30)
                    
                    self.collect_system_metrics()
                    
                    # Cleanup old metrics every hour
                    if int(time.time()) % 3600 < interval:
                        self.cleanup_old_metrics()
                
            except Exception as e:
                self._log_error(f'Error in metrics collection: {e}')
                interval = self.app.config.get('METRICS_COLLECTION_INTERVAL', 30)  # Fallback interval on error
            
            # Sleep for the configured interval
            time.sleep(interval)
    
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

# Global instance
metrics_storage = MetricsStorage()