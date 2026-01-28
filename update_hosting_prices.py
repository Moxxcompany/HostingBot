#!/usr/bin/env python3
"""
Update hosting plan prices in database to match new pricing structure
"""
import os
import asyncio
from database import execute_update

async def update_prices():
    """Update hosting plan prices in database"""
    
    # Get new prices from environment
    plan_7_price = float(os.environ.get('HOSTING_PLAN_7_DAYS_PRICE', '40.00'))
    plan_30_price = float(os.environ.get('HOSTING_PLAN_30_DAYS_PRICE', '75.00'))
    
    print(f"Updating hosting plan prices:")
    print(f"  - Pro 7 Days: ${plan_7_price}")
    print(f"  - Pro 30 Days: ${plan_30_price}")
    
    # Update Pro 7 Days plan
    await execute_update("""
        UPDATE hosting_plans
        SET monthly_price = %s,
            yearly_price = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = 1
    """, (plan_7_price, plan_7_price))
    
    # Update Pro 30 Days plan
    await execute_update("""
        UPDATE hosting_plans
        SET monthly_price = %s,
            yearly_price = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = 2
    """, (plan_30_price, plan_30_price))
    
    print("✅ Hosting plan prices updated successfully!")
    
    # Verify update
    from database import execute_query
    plans = await execute_query("SELECT id, plan_name, monthly_price FROM hosting_plans WHERE id IN (1, 2) ORDER BY id")
    
    print("\nVerification:")
    for plan in plans:
        print(f"  - {plan['plan_name']}: ${plan['monthly_price']}")

if __name__ == '__main__':
    asyncio.run(update_prices())
