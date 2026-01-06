#!/usr/bin/env python3
"""
Database Sync Script
Syncs production database schema and data to development environment for testing
"""

import os
import sys
import asyncio
import logging
import json
from datetime import datetime
from typing import List, Dict, Any

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import execute_query, execute_update
import psycopg2
from psycopg2.extras import Json

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DatabaseSync:
    """Manages database synchronization between environments"""
    
    def __init__(self):
        # DATABASE2_URL is the source (authoritative database)
        # DATABASE_URL is the destination (will be synced to match)
        self.source_db_url = os.getenv('DATABASE2_URL')
        self.dest_db_url = os.getenv('DATABASE_URL')
        
        if not self.source_db_url:
            raise ValueError("DATABASE2_URL not set - this is the source database")
        if not self.dest_db_url:
            raise ValueError("DATABASE_URL not set - this is the destination database")
    
    async def get_schema_info(self, db_url: str) -> List[Dict[str, Any]]:
        """Get table schema information from database"""
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        try:
            # Get all tables
            cursor.execute("""
                SELECT 
                    table_name,
                    table_type
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            
            tables = cursor.fetchall()
            schema_info = []
            
            for table_name, table_type in tables:
                # Get column information
                cursor.execute("""
                    SELECT 
                        column_name,
                        data_type,
                        is_nullable,
                        column_default
                    FROM information_schema.columns
                    WHERE table_name = %s
                    ORDER BY ordinal_position
                """, (table_name,))
                
                columns = cursor.fetchall()
                
                # Get row count
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                row_count = cursor.fetchone()[0]
                
                schema_info.append({
                    'table_name': table_name,
                    'table_type': table_type,
                    'columns': columns,
                    'row_count': row_count
                })
            
            return schema_info
            
        finally:
            cursor.close()
            conn.close()
    
    async def compare_schemas(self):
        """Compare source (DATABASE2_URL) and destination (DATABASE_URL) schemas"""
        logger.info("🔍 Comparing DATABASE2_URL (source) and DATABASE_URL (destination) schemas...")
        
        source_schema = await self.get_schema_info(self.source_db_url)
        dest_schema = await self.get_schema_info(self.dest_db_url)
        
        source_tables = {t['table_name']: t for t in source_schema}
        dest_tables = {t['table_name']: t for t in dest_schema}
        
        # Find differences
        source_only = set(source_tables.keys()) - set(dest_tables.keys())
        dest_only = set(dest_tables.keys()) - set(source_tables.keys())
        common = set(source_tables.keys()) & set(dest_tables.keys())
        
        print("\n" + "="*70)
        print("📊 SCHEMA COMPARISON REPORT")
        print("="*70)
        
        if source_only:
            print(f"\n⚠️  Tables in SOURCE (DATABASE2_URL) only ({len(source_only)}):")
            for table in sorted(source_only):
                print(f"   - {table} ({source_tables[table]['row_count']} rows)")
        
        if dest_only:
            print(f"\n⚠️  Tables in DESTINATION (DATABASE_URL) only ({len(dest_only)}):")
            for table in sorted(dest_only):
                print(f"   - {table} ({dest_tables[table]['row_count']} rows)")
        
        if common:
            print(f"\n✅ Common tables ({len(common)}):")
            for table in sorted(common):
                source_rows = source_tables[table]['row_count']
                dest_rows = dest_tables[table]['row_count']
                diff = source_rows - dest_rows
                symbol = "→" if diff >= 0 else "←"
                print(f"   - {table}: source={source_rows} {symbol} dest={dest_rows} (Δ {abs(diff)})")
        
        print("="*70 + "\n")
        
        return {
            'source_only': source_only,
            'dest_only': dest_only,
            'common': common,
            'source_schema': source_tables,
            'dest_schema': dest_tables
        }
    
    async def copy_table_data(self, table_name: str, limit: int = None):
        """Copy data from DATABASE2_URL (source) to DATABASE_URL (destination)"""
        logger.info(f"📋 Copying {table_name} data from DATABASE2_URL → DATABASE_URL...")
        
        source_conn = psycopg2.connect(self.source_db_url)
        dest_conn = psycopg2.connect(self.dest_db_url)
        
        source_cursor = None
        dest_cursor = None
        try:
            source_cursor = source_conn.cursor()
            dest_cursor = dest_conn.cursor()
            
            # Get column names
            source_cursor.execute(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = '{table_name}'
                ORDER BY ordinal_position
            """)
            columns = [row[0] for row in source_cursor.fetchall()]
            column_list = ', '.join(columns)
            
            # Fetch source data
            query = f"SELECT {column_list} FROM {table_name}"
            if limit:
                query += f" LIMIT {limit}"
            
            source_cursor.execute(query)
            rows = source_cursor.fetchall()
            
            if not rows:
                logger.info(f"   ℹ️  No data to copy for {table_name}")
                return 0
            
            # Get column data types to handle JSONB properly
            source_cursor.execute(f"""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = '{table_name}'
                ORDER BY ordinal_position
            """)
            column_types = {row[0]: row[1] for row in source_cursor.fetchall()}
            
            # Clear destination table
            dest_cursor.execute(f"TRUNCATE TABLE {table_name} CASCADE")
            
            # Convert dict/list values to Json for JSONB columns
            converted_rows = []
            for row in rows:
                converted_row = []
                for i, value in enumerate(row):
                    col_name = columns[i]
                    col_type = column_types.get(col_name, '')
                    
                    # Handle JSONB columns - convert dict/list to Json
                    if col_type in ('jsonb', 'json') and isinstance(value, (dict, list)):
                        converted_row.append(Json(value))
                    else:
                        converted_row.append(value)
                converted_rows.append(tuple(converted_row))
            
            # Insert data into destination
            placeholders = ', '.join(['%s'] * len(columns))
            insert_query = f"INSERT INTO {table_name} ({column_list}) VALUES ({placeholders})"
            
            dest_cursor.executemany(insert_query, converted_rows)
            dest_conn.commit()
            
            logger.info(f"   ✅ Copied {len(rows)} rows to {table_name}")
            return len(rows)
            
        except Exception as e:
            logger.error(f"   ❌ Error copying {table_name}: {e}")
            dest_conn.rollback()
            raise
        finally:
            if source_cursor:
                source_cursor.close()
            if dest_cursor:
                dest_cursor.close()
            source_conn.close()
            dest_conn.close()
    
    async def sync_all_tables(self):
        """Sync ALL tables from DATABASE2_URL to DATABASE_URL"""
        logger.info("🔄 Syncing ALL tables from DATABASE2_URL → DATABASE_URL...")
        
        # Get all tables from source
        comparison = await self.compare_schemas()
        all_tables = list(comparison['common'])
        
        if comparison['source_only']:
            logger.warning(f"⚠️  {len(comparison['source_only'])} tables exist only in source - cannot copy structure automatically")
        
        total_rows = 0
        for table in all_tables:
            try:
                # Copy ALL data (no limit)
                rows = await self.copy_table_data(table, limit=None)
                total_rows += rows
            except Exception as e:
                logger.error(f"Failed to sync {table}: {e}")
        
        logger.info(f"\n✅ Sync complete! Total rows synced: {total_rows}")


async def main():
    """Main entry point"""
    print("\n" + "="*70)
    print("🔄 DATABASE SYNC UTILITY")
    print("="*70)
    print("SOURCE: DATABASE2_URL (authoritative)")
    print("DESTINATION: DATABASE_URL (will be synced)")
    print("="*70 + "\n")
    
    sync = DatabaseSync()
    
    # Step 1: Compare schemas
    comparison = await sync.compare_schemas()
    
    # Step 2: Ask user what to do
    print("\nWhat would you like to do?")
    print("1. Compare schemas only (already done)")
    print("2. Sync ALL tables from DATABASE2_URL → DATABASE_URL (FULL COPY)")
    print("3. Exit")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == '2':
        confirm = input("\n⚠️  This will TRUNCATE DATABASE_URL tables and copy ALL data from DATABASE2_URL. Continue? (yes/no): ")
        if confirm.lower() == 'yes':
            await sync.sync_all_tables()
        else:
            print("❌ Sync cancelled")
    elif choice == '1':
        print("✅ Schema comparison complete (see above)")
    else:
        print("👋 Goodbye!")


if __name__ == "__main__":
    asyncio.run(main())
