#!/usr/bin/env python3
"""
Sync Vultr Windows templates and plans to database
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import execute_update, execute_query
from services.vultr import vultr_service
import asyncio

async def sync_windows_templates():
    """Sync Windows OS templates to database"""
    print("🔄 Syncing Windows templates from Vultr...")
    
    # Get all OS options
    os_list = vultr_service.get_os_list()
    
    # Filter Windows Standard editions only (no Datacenter, no Core)
    windows_standard = [
        os for os in os_list
        if 'windows' in os.get('name', '').lower()
        and 'standard' in os.get('name', '').lower()
        and 'core' not in os.get('name', '').lower()
    ]
    
    synced = 0
    for os_item in windows_standard:
        os_id = os_item.get('id')
        name = os_item.get('name', '')
        
        # Extract version (2019, 2022, 2025)
        version = None
        for v in ['2025', '2022', '2019', '2016']:
            if v in name:
                version = v
                break
        
        if not version:
            continue
        
        # Insert or update
        await execute_update("""
            INSERT INTO rdp_templates (vultr_os_id, windows_version, edition, display_name, is_active)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (vultr_os_id) DO UPDATE
            SET display_name = EXCLUDED.display_name,
                is_active = EXCLUDED.is_active,
                updated_at = NOW()
        """, (os_id, version, 'Standard', name, True))
        
        print(f"   ✅ {name} (ID: {os_id})")
        synced += 1
    
    print(f"\n✅ Synced {synced} Windows templates")

async def sync_rdp_plans():
    """Sync RDP plans with 150% margin pricing"""
    print("\n🔄 Syncing RDP plans...")
    
    plans = vultr_service.get_plans()
    
    # Define our curated plans with pricing (150% margin)
    curated_plans = {
        'vc2-1c-2gb': {'name': 'Starter', 'price': 60},
        'vc2-2c-4gb': {'name': 'Basic', 'price': 90},
        'vc2-4c-8gb': {'name': 'Performance', 'price': 140},
        'vc2-6c-16gb': {'name': 'Power', 'price': 250},
    }
    
    synced = 0
    for plan in plans:
        plan_id = plan.get('id', '')
        
        # Only sync our curated plans
        if plan_id not in curated_plans:
            continue
        
        vcpu = plan.get('vcpu_count', 0)
        ram_mb = plan.get('ram', 0)
        disk_gb = plan.get('disk', 0)
        bandwidth_gb = plan.get('bandwidth', 0)
        bandwidth_tb = bandwidth_gb / 1024 if bandwidth_gb else 0
        vultr_cost = plan.get('monthly_cost', 0)
        
        our_price = curated_plans[plan_id]['price']
        plan_name = curated_plans[plan_id]['name']
        
        await execute_update("""
            INSERT INTO rdp_plans 
            (vultr_plan_id, plan_name, vcpu_count, ram_mb, storage_gb, bandwidth_tb, 
             vultr_monthly_cost, our_monthly_price, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (vultr_plan_id) DO UPDATE
            SET plan_name = EXCLUDED.plan_name,
                our_monthly_price = EXCLUDED.our_monthly_price,
                is_active = EXCLUDED.is_active,
                updated_at = NOW()
        """, (plan_id, plan_name, vcpu, ram_mb, disk_gb, bandwidth_tb, 
             vultr_cost, our_price, True))
        
        print(f"   ✅ {plan_name} ({plan_id}) - ${our_price}/mo ({vcpu}c/{ram_mb/1024:.0f}GB)")
        synced += 1
    
    print(f"\n✅ Synced {synced} RDP plans")

async def main():
    print("="*70)
    print("🔄 VULTR CATALOG SYNC")
    print("="*70)
    print()
    
    await sync_windows_templates()
    await sync_rdp_plans()
    
    print("\n" + "="*70)
    print("✅ SYNC COMPLETE!")
    print("="*70)

if __name__ == '__main__':
    asyncio.run(main())
