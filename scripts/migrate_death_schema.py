#!/usr/bin/env python3

import sqlite3
import sys
import os

def migrate_death_schema(db_path):
    """Migrate player_deaths table to new schema"""
    
    print(f"Migrating death schema in database: {db_path}")
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # Check current table structure
        cursor.execute("PRAGMA table_info(player_deaths)")
        columns = [column[1] for column in cursor.fetchall()]
        print(f"Current columns: {columns}")
        
        # Check if migration is needed
        if 'death_method' in columns and 'death_cause' in columns:
            print("✅ Database already has new schema, no migration needed")
            return
        
        if 'vault_type' not in columns:
            print("❌ Unexpected database structure, cannot migrate")
            return
        
        print("🔄 Migrating database schema...")
        
        # Add new columns if they don't exist
        if 'death_method' not in columns:
            print("  Adding death_method column...")
            cursor.execute('ALTER TABLE player_deaths ADD COLUMN death_method TEXT')
        else:
            print("  death_method column already exists")
            
        if 'death_cause' not in columns:
            print("  Adding death_cause column...")
            cursor.execute('ALTER TABLE player_deaths ADD COLUMN death_cause TEXT')
        else:
            print("  death_cause column already exists")
        
        # Migrate existing data
        cursor.execute('''
            UPDATE player_deaths 
            SET death_method = 'Vault Defeat', death_cause = vault_type 
            WHERE death_method IS NULL AND vault_type IS NOT NULL
        ''')
        
        # Verify migration
        cursor.execute("SELECT COUNT(*) FROM player_deaths WHERE death_method IS NOT NULL")
        migrated_count = cursor.fetchone()[0]
        
        conn.commit()
        print(f"✅ Migration completed! Updated {migrated_count} existing death records")
        
        # Show new structure
        cursor.execute("PRAGMA table_info(player_deaths)")
        new_columns = [column[1] for column in cursor.fetchall()]
        print(f"New columns: {new_columns}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python migrate_death_schema.py <path_to_database>")
        print("Example: python migrate_death_schema.py data/metrics.db")
        sys.exit(1)
    
    db_path = sys.argv[1]
    
    if not os.path.exists(db_path):
        print(f"❌ Database file not found: {db_path}")
        sys.exit(1)
    
    try:
        migrate_death_schema(db_path)
        print("🎉 Migration successful!")
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)