#!/usr/bin/env python3

import os
import re
import gzip
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Set
import logging

class PlayerLogParser:
    """Parser for Minecraft server logs to extract player login/logout history"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
        
        # Pattern to match player join/leave events - handles both timestamp formats
        self.join_pattern = re.compile(
            r'\[(\d{2}[A-Za-z]{3}\d{4} \d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}:\d{2})\] '
            r'\[Server thread/INFO\] \[(?:net\.minecraft\.server\.dedicated\.DedicatedServer|minecraft/DedicatedServer)/?\]: '
            r'(.+?) joined the game'
        )
        
        self.leave_pattern = re.compile(
            r'\[(\d{2}[A-Za-z]{3}\d{4} \d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}:\d{2})\] '
            r'\[Server thread/INFO\] \[(?:net\.minecraft\.server\.dedicated\.DedicatedServer|minecraft/DedicatedServer)/?\]: '
            r'(.+?) left the game'
        )
        
        # Multiple death patterns for different death types
        self.death_patterns = [
            # Vault deaths (VaultHunters specific)
            re.compile(
                r'\[(\d{2}[A-Za-z]{3}\d{4} \d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}:\d{2})\] '
                r'\[Server thread/INFO\] \[(?:net\.minecraft\.server\.dedicated\.DedicatedServer|minecraft/DedicatedServer)/?\]: '
                r'(.+?) was defeated in a (.+? Vault)\.'
            ),
            # Player vs entity/mob deaths
            re.compile(
                r'\[(\d{2}[A-Za-z]{3}\d{4} \d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}:\d{2})\] '
                r'\[Server thread/INFO\] \[(?:net\.minecraft\.server\.dedicated\.DedicatedServer|minecraft/DedicatedServer)/?\]: '
                r'(.+?) was slain by (.+?)(?:\s|$)'
            ),
            # Fall damage
            re.compile(
                r'\[(\d{2}[A-Za-z]{3}\d{4} \d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}:\d{2})\] '
                r'\[Server thread/INFO\] \[(?:net\.minecraft\.server\.dedicated\.DedicatedServer|minecraft/DedicatedServer)/?\]: '
                r'(.+?) fell from a high place'
            ),
            # Explosion deaths
            re.compile(
                r'\[(\d{2}[A-Za-z]{3}\d{4} \d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}:\d{2})\] '
                r'\[Server thread/INFO\] \[(?:net\.minecraft\.server\.dedicated\.DedicatedServer|minecraft/DedicatedServer)/?\]: '
                r'(.+?) was blown up by (.+?)(?:\s|$)'
            ),
            # Fire/lava deaths
            re.compile(
                r'\[(\d{2}[A-Za-z]{3}\d{4} \d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}:\d{2})\] '
                r'\[Server thread/INFO\] \[(?:net\.minecraft\.server\.dedicated\.DedicatedServer|minecraft/DedicatedServer)/?\]: '
                r'(.+?) burned to death'
            ),
            # Suffocation
            re.compile(
                r'\[(\d{2}[A-Za-z]{3}\d{4} \d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}:\d{2})\] '
                r'\[Server thread/INFO\] \[(?:net\.minecraft\.server\.dedicated\.DedicatedServer|minecraft/DedicatedServer)/?\]: '
                r'(.+?) suffocated'
            ),
            # Projectile deaths
            re.compile(
                r'\[(\d{2}[A-Za-z]{3}\d{4} \d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}:\d{2})\] '
                r'\[Server thread/INFO\] \[(?:net\.minecraft\.server\.dedicated\.DedicatedServer|minecraft/DedicatedServer)/?\]: '
                r'(.+?) was shot by (.+?)(?:\s|$)'
            ),
            # Drowning
            re.compile(
                r'\[(\d{2}[A-Za-z]{3}\d{4} \d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}:\d{2})\] '
                r'\[Server thread/INFO\] \[(?:net\.minecraft\.server\.dedicated\.DedicatedServer|minecraft/DedicatedServer)/?\]: '
                r'(.+?) drowned'
            ),
            # Generic death pattern (fallback for other death messages)
            re.compile(
                r'\[(\d{2}[A-Za-z]{3}\d{4} \d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}:\d{2})\] '
                r'\[Server thread/INFO\] \[(?:net\.minecraft\.server\.dedicated\.DedicatedServer|minecraft/DedicatedServer)/?\]: '
                r'(.+?) (died|was killed|starved to death|froze to death|withered away|hit the ground too hard)'
            )
        ]
        
        # Player name variations mapping (base_name -> set of variations)
        self.player_variations: Dict[str, Set[str]] = {}
        
        # Cache for resolved player names
        self.name_cache: Dict[str, str] = {}
    
    def parse_timestamp(self, timestamp_str: str, context_year: int = 2025) -> datetime:
        """Parse Minecraft log timestamp format: 22Aug2025 00:16:55.377 or 15:09:47"""
        try:
            # Full format: 22Aug2025 00:16:55.377
            if len(timestamp_str) > 10 and 'Aug' in timestamp_str:
                return datetime.strptime(timestamp_str, '%d%b%Y %H:%M:%S.%f')
            # Short format: 15:09:47 - need to infer date from context
            elif ':' in timestamp_str and len(timestamp_str) <= 8:
                # For short format, we need to estimate the date
                # Use current year and month, or context from filename
                time_part = datetime.strptime(timestamp_str, '%H:%M:%S').time()
                # Default to August 2025 for these logs based on the data
                estimated_date = datetime(context_year, 8, 20).date()
                return datetime.combine(estimated_date, time_part)
            else:
                self.logger.warning(f"Unknown timestamp format: '{timestamp_str}'")
                return datetime.now()
        except ValueError as e:
            self.logger.warning(f"Failed to parse timestamp '{timestamp_str}': {e}")
            return datetime.now()
    
    def normalize_player_name(self, display_name: str) -> str:
        """
        Normalize player names to handle achievement titles
        Examples:
        - 'MadSavage69' -> 'MadSavage69'
        - 'Slayer MadSavage69 of the Ancients' -> 'MadSavage69'
        """
        if display_name in self.name_cache:
            return self.name_cache[display_name]
        
        # Check if this name is already a known variation
        for base_name, variations in self.player_variations.items():
            if display_name in variations:
                self.name_cache[display_name] = base_name
                return base_name
        
        # Try to extract base name from achievement titles
        # Common patterns in VaultHunters:
        # - "Title Username of the Something"
        # - "Title Username"
        # - Just "Username"
        
        # Look for patterns that might indicate titles
        title_patterns = [
            # "Slayer MadSavage69 of the Ancients"
            r'^[A-Za-z\s]+ ([A-Za-z0-9_]+) of the .+$',
            # "Champion Username"
            r'^[A-Za-z\s]+ ([A-Za-z0-9_]+)$',
        ]
        
        for pattern in title_patterns:
            match = re.match(pattern, display_name)
            if match:
                base_name = match.group(1)
                # Add this variation to our mapping
                if base_name not in self.player_variations:
                    self.player_variations[base_name] = {base_name}
                self.player_variations[base_name].add(display_name)
                self.name_cache[display_name] = base_name
                self.logger.info(f"Mapped '{display_name}' -> '{base_name}'")
                return base_name
        
        # If no pattern matches, assume it's a base name
        base_name = display_name
        if base_name not in self.player_variations:
            self.player_variations[base_name] = {base_name}
        self.name_cache[display_name] = base_name
        return base_name
    
    def parse_log_file(self, file_path: str) -> List[Tuple[str, str, datetime, str]]:
        """
        Parse a single log file and extract player events
        Returns list of (username, action, timestamp, extra_data) tuples
        """
        events = []
        
        # Extract date context from filename if possible
        filename = os.path.basename(file_path)
        context_year = 2025
        context_month = 8
        context_day = 20
        
        # Try to extract date from filename like "2025-08-17-1.log.gz"
        date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', filename)
        if date_match:
            context_year = int(date_match.group(1))
            context_month = int(date_match.group(2))
            context_day = int(date_match.group(3))
        
        try:
            if file_path.endswith('.gz'):
                with gzip.open(file_path, 'rt', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            else:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            
            # Find all join events
            for match in self.join_pattern.finditer(content):
                timestamp_str = match.group(1)
                display_name = match.group(2)
                
                # Use context date for short timestamps
                if len(timestamp_str) <= 8:
                    time_part = datetime.strptime(timestamp_str, '%H:%M:%S').time()
                    timestamp = datetime.combine(datetime(context_year, context_month, context_day).date(), time_part)
                else:
                    timestamp = self.parse_timestamp(timestamp_str, context_year)
                
                username = self.normalize_player_name(display_name)
                events.append((username, 'join', timestamp, ''))
            
            # Find all leave events
            for match in self.leave_pattern.finditer(content):
                timestamp_str = match.group(1)
                display_name = match.group(2)
                
                # Use context date for short timestamps
                if len(timestamp_str) <= 8:
                    time_part = datetime.strptime(timestamp_str, '%H:%M:%S').time()
                    timestamp = datetime.combine(datetime(context_year, context_month, context_day).date(), time_part)
                else:
                    timestamp = self.parse_timestamp(timestamp_str, context_year)
                
                username = self.normalize_player_name(display_name)
                events.append((username, 'leave', timestamp, ''))
            
            # Find all death events (multiple patterns)
            for i, death_pattern in enumerate(self.death_patterns):
                for match in death_pattern.finditer(content):
                    timestamp_str = match.group(1)
                    display_name = match.group(2)
                    
                    # Use context date for short timestamps
                    if len(timestamp_str) <= 8:
                        time_part = datetime.strptime(timestamp_str, '%H:%M:%S').time()
                        timestamp = datetime.combine(datetime(context_year, context_month, context_day).date(), time_part)
                    else:
                        timestamp = self.parse_timestamp(timestamp_str, context_year)
                    
                    username = self.normalize_player_name(display_name)
                    
                    # Determine death cause and method based on pattern
                    if i == 0:  # Vault defeat
                        vault_type = match.group(3)
                        death_data = f"Vault Defeat|{vault_type}"
                    elif i == 1:  # Slain by entity
                        killer = match.group(3)
                        death_data = f"Slain|{killer}"
                    elif i == 2:  # Fall damage
                        death_data = "Fall Damage|High Place"
                    elif i == 3:  # Explosion
                        bomber = match.group(3)
                        death_data = f"Explosion|{bomber}"
                    elif i == 4:  # Burned to death
                        death_data = "Burned|Fire/Lava"
                    elif i == 5:  # Suffocation
                        death_data = "Suffocation|Blocks"
                    elif i == 6:  # Shot by
                        shooter = match.group(3)
                        death_data = f"Projectile|{shooter}"
                    elif i == 7:  # Drowning
                        death_data = "Drowning|Water"
                    elif i == 8:  # Generic death
                        death_cause = match.group(3)
                        death_data = f"Other|{death_cause}"
                    
                    events.append((username, 'death', timestamp, death_data))
        
        except Exception as e:
            self.logger.error(f"Failed to parse {file_path}: {e}")
        
        return sorted(events, key=lambda x: x[2])  # Sort by timestamp
    
    def get_all_log_files(self, log_dir: str) -> List[str]:
        """Get all log files in chronological order"""
        log_files = []
        
        for filename in os.listdir(log_dir):
            if filename.endswith('.log') or filename.endswith('.log.gz'):
                if filename == 'crafttweaker.log':
                    continue  # Skip crafttweaker logs
                
                full_path = os.path.join(log_dir, filename)
                log_files.append(full_path)
        
        # Sort by modification time to get chronological order
        log_files.sort(key=lambda x: os.path.getmtime(x))
        return log_files
    
    def deduplicate_events(self, events: List[Tuple[str, str, datetime, str]]) -> List[Tuple[str, str, datetime, str]]:
        """Remove duplicate events (same player, action, and timestamp within 1 second)"""
        unique_events = []
        seen_events = set()
        
        for username, action, timestamp, extra_data in events:
            # Create a key that allows for slight timestamp differences (within 1 second)
            # This handles duplicates between main logs and debug logs
            timestamp_key = (username, action, int(timestamp.timestamp()))
            
            if timestamp_key not in seen_events:
                seen_events.add(timestamp_key)
                unique_events.append((username, action, timestamp, extra_data))
            else:
                self.logger.debug(f"Skipping duplicate event: {username} {action} at {timestamp}")
        
        return unique_events
    
    def create_session_from_events(self, events: List[Tuple[str, str, datetime, str]]) -> List[Dict]:
        """
        Convert raw events into login sessions
        Handles cases where players disconnect without proper logout
        """
        sessions = []
        active_sessions = {}  # username -> login_time
        
        for username, action, timestamp, extra_data in events:
            if action == 'join':
                # Close any existing session for this user (server restart, crash, etc.)
                if username in active_sessions:
                    login_time = active_sessions[username]
                    sessions.append({
                        'username': username,
                        'login_time': login_time,
                        'logout_time': timestamp,  # Use join time as logout for previous session
                        'completed': False  # Mark as incomplete session
                    })
                
                # Start new session
                active_sessions[username] = timestamp
            
            elif action == 'leave':
                if username in active_sessions:
                    login_time = active_sessions.pop(username)
                    sessions.append({
                        'username': username,
                        'login_time': login_time,
                        'logout_time': timestamp,
                        'completed': True
                    })
                else:
                    # Leave without join (server restart scenario)
                    self.logger.warning(f"Found leave event without join for {username} at {timestamp}")
            # Note: death events are handled separately, not in sessions
        
        # Handle any remaining active sessions (server still running or crashed)
        for username, login_time in active_sessions.items():
            sessions.append({
                'username': username,
                'login_time': login_time,
                'logout_time': None,  # Still online or server crashed
                'completed': False
            })
        
        return sessions
    
    def extract_deaths_from_events(self, events: List[Tuple[str, str, datetime, str]]) -> List[Dict]:
        """Extract death events from the parsed events"""
        deaths = []
        for username, action, timestamp, extra_data in events:
            if action == 'death':
                # Parse death_data format: "method|cause"
                if '|' in extra_data:
                    death_method, death_cause = extra_data.split('|', 1)
                else:
                    # Fallback for old format
                    death_method = 'Vault Defeat'
                    death_cause = extra_data
                
                deaths.append({
                    'username': username,
                    'death_time': timestamp,
                    'death_cause': death_cause,
                    'death_method': death_method
                })
        return deaths
    
    def import_deaths_to_database(self, deaths: List[Dict]):
        """Import death events to SQLite database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            imported_count = 0
            skipped_count = 0
            
            for death in deaths:
                username = death['username']
                death_time = death['death_time']
                death_cause = death['death_cause']
                death_method = death['death_method']
                
                # Check if this exact death already exists
                cursor.execute('''
                    SELECT id FROM player_deaths 
                    WHERE username = ? AND death_time = ? AND death_cause = ? AND death_method = ?
                ''', (username, death_time, death_cause, death_method))
                
                if cursor.fetchone():
                    skipped_count += 1
                    continue
                
                # Insert new death with new schema
                cursor.execute('''
                    INSERT INTO player_deaths (username, death_time, death_cause, death_method)
                    VALUES (?, ?, ?, ?)
                ''', (username, death_time, death_cause, death_method))
                imported_count += 1
            
            conn.commit()
            self.logger.info(f"Imported {imported_count} deaths, skipped {skipped_count} duplicates")
            return imported_count, skipped_count
    
    def import_to_database(self, sessions: List[Dict]):
        """Import sessions to SQLite database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            imported_count = 0
            skipped_count = 0
            
            for session in sessions:
                username = session['username']
                login_time = session['login_time']
                logout_time = session.get('logout_time')
                
                # Check if this exact session already exists
                cursor.execute('''
                    SELECT id FROM players 
                    WHERE username = ? AND login_time = ?
                ''', (username, login_time))
                
                if cursor.fetchone():
                    skipped_count += 1
                    continue
                
                # Insert new session
                is_online = 1 if logout_time is None else 0
                cursor.execute('''
                    INSERT INTO players (username, login_time, logout_time, is_online)
                    VALUES (?, ?, ?, ?)
                ''', (username, login_time, logout_time, is_online))
                imported_count += 1
            
            conn.commit()
            self.logger.info(f"Imported {imported_count} sessions, skipped {skipped_count} duplicates")
            return imported_count, skipped_count
    
    def parse_all_logs(self, log_dir: str) -> Dict:
        """Parse all logs and import to database"""
        self.logger.info(f"Starting log parsing from {log_dir}")
        
        log_files = self.get_all_log_files(log_dir)
        self.logger.info(f"Found {len(log_files)} log files to process")
        
        all_events = []
        
        # Parse each log file
        for log_file in log_files:
            self.logger.info(f"Processing {log_file}")
            events = self.parse_log_file(log_file)
            all_events.extend(events)
            self.logger.info(f"Found {len(events)} events in {os.path.basename(log_file)}")
        
        # Sort all events by timestamp
        all_events.sort(key=lambda x: x[2])
        self.logger.info(f"Total events found: {len(all_events)}")
        
        # Remove duplicates (events that appear in both main and debug logs)
        unique_events = self.deduplicate_events(all_events)
        self.logger.info(f"Unique events after deduplication: {len(unique_events)}")
        
        # Convert to sessions
        sessions = self.create_session_from_events(unique_events)
        self.logger.info(f"Created {len(sessions)} player sessions")
        
        # Death tracking disabled - skip death extraction
        deaths = []
        self.logger.info(f"Death tracking disabled - skipping death events")
        
        # Import sessions to database
        imported, skipped = self.import_to_database(sessions)
        deaths_imported, deaths_skipped = 0, 0
        
        # Log player name variations found
        self.logger.info("Player name variations discovered:")
        for base_name, variations in self.player_variations.items():
            if len(variations) > 1:
                self.logger.info(f"  {base_name}: {sorted(variations)}")
        
        return {
            'log_files_processed': len(log_files),
            'total_events': len(all_events),
            'sessions_created': len(sessions),
            'sessions_imported': imported,
            'sessions_skipped': skipped,
            'deaths_found': len(deaths),
            'deaths_imported': deaths_imported,
            'deaths_skipped': deaths_skipped,
            'player_variations': dict(self.player_variations)
        }
    
    def recalculate_player_sessions(self, log_dir: str, player_name: Optional[str] = None) -> Dict:
        """
        Force recalculation of player sessions for specific player or all players
        This will:
        1. Re-parse all logs to get fresh login/logout events
        2. Delete existing sessions for the player(s) 
        3. Recalculate sessions based on actual log timestamps
        4. Update the database with corrected sessions
        """
        self.logger.info(f"Starting session recalculation for player: {player_name or 'ALL PLAYERS'}")
        
        # Parse all logs to get fresh events
        log_files = self.get_all_log_files(log_dir)
        self.logger.info(f"Re-parsing {len(log_files)} log files for session correction")
        
        all_events = []
        for log_file in log_files:
            events = self.parse_log_file(log_file)
            all_events.extend(events)
        
        # Sort and deduplicate events
        all_events.sort(key=lambda x: x[2])
        unique_events = self.deduplicate_events(all_events)
        
        # Filter events for specific player if requested
        if player_name:
            # Normalize the requested player name to handle variations
            normalized_player = self.normalize_player_name(player_name)
            unique_events = [event for event in unique_events if event[0] == normalized_player]
            self.logger.info(f"Filtered to {len(unique_events)} events for player '{normalized_player}'")
            
            # Check if player was found in logs
            if not unique_events:
                available_players = sorted(set(event[0] for event in all_events))
                raise ValueError(f"Player '{player_name}' not found in logs. Available players: {', '.join(available_players)}")
        
        # Convert to sessions
        sessions = self.create_session_from_events(unique_events)
        self.logger.info(f"Recreated {len(sessions)} sessions from log data")
        
        # Database operations
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Delete existing sessions for the player(s)
            if player_name:
                normalized_player = self.normalize_player_name(player_name)
                cursor.execute('DELETE FROM players WHERE username = ?', (normalized_player,))
                deleted_count = cursor.rowcount
                self.logger.info(f"Deleted {deleted_count} existing sessions for player '{normalized_player}'")
            else:
                cursor.execute('DELETE FROM players')
                deleted_count = cursor.rowcount
                self.logger.info(f"Deleted {deleted_count} existing sessions for all players")
            
            # Insert corrected sessions
            imported_count = 0
            for session in sessions:
                username = session['username']
                login_time = session['login_time']
                logout_time = session.get('logout_time')
                is_online = 1 if logout_time is None else 0
                
                cursor.execute('''
                    INSERT INTO players (username, login_time, logout_time, is_online)
                    VALUES (?, ?, ?, ?)
                ''', (username, login_time, logout_time, is_online))
                imported_count += 1
            
            conn.commit()
            self.logger.info(f"Imported {imported_count} corrected sessions")
            
            # Calculate and log playtime statistics
            stats = self._calculate_playtime_stats(cursor, player_name)
            
        return {
            'player_name': player_name or 'ALL PLAYERS',
            'deleted_sessions': deleted_count,
            'imported_sessions': imported_count,
            'playtime_stats': stats
        }
    
    def _calculate_playtime_stats(self, cursor, player_name: Optional[str] = None) -> Dict:
        """Calculate playtime statistics for player(s)"""
        stats = {}
        
        if player_name:
            normalized_player = self.normalize_player_name(player_name)
            query = '''
                SELECT username, 
                       COUNT(*) as total_sessions,
                       SUM(CASE WHEN logout_time IS NOT NULL 
                           THEN (julianday(logout_time) - julianday(login_time)) * 24 * 60 * 60 
                           ELSE 0 END) as total_playtime_seconds,
                       MIN(login_time) as first_seen,
                       MAX(COALESCE(logout_time, login_time)) as last_seen
                FROM players 
                WHERE username = ?
                GROUP BY username
            '''
            cursor.execute(query, (normalized_player,))
            result = cursor.fetchone()
            
            if result:
                username, sessions, playtime_seconds, first_seen, last_seen = result
                hours = int(playtime_seconds // 3600)
                minutes = int((playtime_seconds % 3600) // 60)
                stats[username] = {
                    'total_sessions': sessions,
                    'total_playtime': f"{hours}h {minutes}m",
                    'total_playtime_seconds': playtime_seconds,
                    'first_seen': first_seen,
                    'last_seen': last_seen
                }
        else:
            # Get stats for all players
            query = '''
                SELECT username, 
                       COUNT(*) as total_sessions,
                       SUM(CASE WHEN logout_time IS NOT NULL 
                           THEN (julianday(logout_time) - julianday(login_time)) * 24 * 60 * 60 
                           ELSE 0 END) as total_playtime_seconds,
                       MIN(login_time) as first_seen,
                       MAX(COALESCE(logout_time, login_time)) as last_seen
                FROM players 
                GROUP BY username
                ORDER BY total_playtime_seconds DESC
            '''
            cursor.execute(query)
            
            for username, sessions, playtime_seconds, first_seen, last_seen in cursor.fetchall():
                hours = int(playtime_seconds // 3600)
                minutes = int((playtime_seconds % 3600) // 60)
                stats[username] = {
                    'total_sessions': sessions,
                    'total_playtime': f"{hours}h {minutes}m",
                    'total_playtime_seconds': playtime_seconds,
                    'first_seen': first_seen,
                    'last_seen': last_seen
                }
        
        return stats


def main():
    """Main function to run the log parser"""
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description='Parse Minecraft server logs for player activity')
    parser.add_argument('--log-dir', required=True, help='Directory containing server logs')
    parser.add_argument('--db-path', required=True, help='Path to SQLite database')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    parser.add_argument('--force', action='store_true', help='Force recalculation of playtime and correction of sessions')
    parser.add_argument('--player', help='Specific player name to recalculate (requires --force). If not specified, recalculates for all players')
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.player and not args.force:
        print("Error: --player parameter requires --force flag")
        sys.exit(1)
    
    # Set up logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Check if paths exist
    if not os.path.exists(args.log_dir):
        print(f"Error: Log directory {args.log_dir} does not exist")
        sys.exit(1)
    
    if not os.path.exists(args.db_path):
        print(f"Error: Database {args.db_path} does not exist")
        sys.exit(1)
    
    # Run parser
    parser_instance = PlayerLogParser(args.db_path)
    
    if args.force:
        # Force recalculation mode
        print(f"\n=== FORCE RECALCULATION MODE ===")
        if args.player:
            print(f"Recalculating sessions for player: {args.player}")
        else:
            print("Recalculating sessions for ALL players")
        
        try:
            results = parser_instance.recalculate_player_sessions(args.log_dir, args.player)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
        
        # Print recalculation results
        print(f"\n=== Session Recalculation Results ===")
        print(f"Player: {results['player_name']}")
        print(f"Deleted existing sessions: {results['deleted_sessions']}")
        print(f"Imported corrected sessions: {results['imported_sessions']}")
        
        # Print playtime statistics
        print(f"\n=== Updated Playtime Statistics ===")
        for username, stats in results['playtime_stats'].items():
            print(f"\nPlayer: {username}")
            print(f"  Total sessions: {stats['total_sessions']}")
            print(f"  Total playtime: {stats['total_playtime']}")
            print(f"  First seen: {stats['first_seen']}")
            print(f"  Last seen: {stats['last_seen']}")
        
        if not results['playtime_stats']:
            print("No session data found for the specified player(s)")
    
    else:
        # Normal parsing mode
        results = parser_instance.parse_all_logs(args.log_dir)
        
        # Print results
        print("\n=== Log Parsing Results ===")
        print(f"Log files processed: {results['log_files_processed']}")
        print(f"Total events found: {results['total_events']}")
        print(f"Sessions created: {results['sessions_created']}")
        print(f"Sessions imported: {results['sessions_imported']}")
        print(f"Sessions skipped (duplicates): {results['sessions_skipped']}")
        print(f"Deaths found: {results['deaths_found']}")
        print(f"Deaths imported: {results['deaths_imported']}")
        print(f"Deaths skipped (duplicates): {results['deaths_skipped']}")
        
        print(f"\nPlayer name variations found:")
        for base_name, variations in results['player_variations'].items():
            if len(variations) > 1:
                print(f"  {base_name}: {sorted(variations)}")


if __name__ == '__main__':
    main()