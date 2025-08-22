#!/usr/bin/env python3

import sqlite3
import sys
import os

def fix_death_schema(db_path):
    """Fix player_deaths table schema by recreating it"""
    
    print(f"Fixing death schema in database: {db_path}")
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # Check if we need to fix the schema
        cursor.execute("PRAGMA table_info(player_deaths)")
        columns_info = cursor.fetchall()
        vault_type_info = None
        
        for column_info in columns_info:
            if column_info[1] == 'vault_type':  # column[1] is the name
                vault_type_info = column_info
                break
        
        if not vault_type_info or vault_type_info[3] == 0:  # column[3] is notnull flag
            print("✅ Schema is already correct")
            return
        
        print("🔄 Recreating table with correct schema...")
        
        # Backup existing data
        cursor.execute('''
            CREATE TEMPORARY TABLE player_deaths_backup AS 
            SELECT * FROM player_deaths
        ''')
        
        # Drop old table
        cursor.execute('DROP TABLE player_deaths')
        
        # Recreate table with correct schema
        cursor.execute('''
            CREATE TABLE player_deaths (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                death_time DATETIME NOT NULL,
                death_cause TEXT NOT NULL,
                death_method TEXT,
                vault_type TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Recreate indexes
        cursor.execute('''
            CREATE INDEX idx_deaths_username 
            ON player_deaths(username)
        ''')
        cursor.execute('''
            CREATE INDEX idx_deaths_time 
            ON player_deaths(death_time)
        ''')
        
        # Migrate data back - handle both old and new records
        cursor.execute('''
            INSERT INTO player_deaths (id, username, death_time, death_cause, death_method, vault_type, created_at)
            SELECT 
                id, 
                username, 
                death_time,
                COALESCE(death_cause, vault_type) as death_cause,
                COALESCE(death_method, 'Vault Defeat') as death_method,
                vault_type,
                created_at
            FROM player_deaths_backup
        ''')
        
        # Drop temporary table
        cursor.execute('DROP TABLE player_deaths_backup')
        
        # Verify migration
        cursor.execute("SELECT COUNT(*) FROM player_deaths")
        count = cursor.fetchone()[0]
        
        conn.commit()
        print(f"✅ Schema fixed! Preserved {count} existing death records")
        
        # Show new structure
        cursor.execute("PRAGMA table_info(player_deaths)")
        columns = [(col[1], col[2], 'NOT NULL' if col[3] else 'NULL') for col in cursor.fetchall()]
        print("New schema:")
        for name, type_, constraint in columns:
            print(f"  {name}: {type_} {constraint}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python fix_death_schema.py <path_to_database>")
        print("Example: python fix_death_schema.py data/metrics.db")
        sys.exit(1)
    
    db_path = sys.argv[1]
    
    if not os.path.exists(db_path):
        print(f"❌ Database file not found: {db_path}")
        sys.exit(1)
    
    try:
        fix_death_schema(db_path)
        print("🎉 Schema fix successful!")
    except Exception as e:
        print(f"❌ Schema fix failed: {e}")
        sys.exit(1)