#!/usr/bin/env python3
"""
Create a test Windows RDP server via Vultr API
This will show us the REAL total costs including Windows licensing
"""

import os
import requests
import json
import time

API_KEY = os.environ.get('VULTR_API_KEY')
BASE_URL = 'https://api.vultr.com/v2'

headers = {
    'Authorization': f'Bearer {API_KEY}',
    'Content-Type': 'application/json'
}

print('='*80)
print('🧪 CREATING VULTR TEST WINDOWS SERVER')
print('='*80)
print()

# Use smallest Windows Server for cost testing
server_config = {
    "region": "ewr",  # New Jersey
    "plan": "vc2-1c-2gb",  # Smallest suitable for Windows: 1 vCPU, 2GB RAM
    "os_id": 501,  # Windows Server 2022 Standard
    "label": "HostBay-Test-Win2022",
    "hostname": "test-win2022"
}

print('📋 Server Configuration:')
print(f'   OS: Windows Server 2022 Standard (ID: 501)')
print(f'   Plan: vc2-1c-2gb (1 vCPU, 2 GB RAM, 55 GB NVMe)')
print(f'   Region: New Jersey (ewr)')
print(f'   Base Cost: $10/month (+ Windows licensing)')
print()
print('⏳ Creating server...')
print()

try:
    response = requests.post(
        f'{BASE_URL}/instances',
        headers=headers,
        json=server_config,
        timeout=30
    )
    
    if response.status_code in [200, 201, 202]:
        result = response.json()
        instance = result.get('instance', {})
        
        print('✅ SERVER CREATED!')
        print('='*80)
        print()
        print(f'🆔 Instance ID: {instance.get("id")}')
        print(f'📛 Label: {instance.get("label")}')
        print(f'🌍 Region: {instance.get("region")}')
        print(f'💻 Plan: {instance.get("plan")}')
        print(f'🪟 OS: Windows Server 2022 Standard')
        print(f'⚡ Status: {instance.get("status")}')
        print()
        
        # Save instance ID for cleanup
        instance_id = instance.get('id')
        with open('vultr_test_server.txt', 'w') as f:
            f.write(f'Instance ID: {instance_id}\n')
            f.write(f'Created: {time.strftime("%Y-%m-%d %H:%M:%S")}\n')
        
        print('💾 Instance ID saved to: vultr_test_server.txt')
        print()
        
        # Wait for server to provision
        print('⏳ Waiting for server to provision (1-3 minutes)...')
        print()
        
        start_time = time.time()
        max_wait = 300  # 5 minutes
        password = None
        
        while time.time() - start_time < max_wait:
            time.sleep(10)
            
            # Get instance details
            status_response = requests.get(
                f'{BASE_URL}/instances/{instance_id}',
                headers=headers,
                timeout=10
            )
            
            if status_response.status_code == 200:
                status_data = status_response.json()
                inst = status_data.get('instance', {})
                
                status = inst.get('status')
                power_status = inst.get('power_status')
                main_ip = inst.get('main_ip')
                default_password = inst.get('default_password')
                
                elapsed = int(time.time() - start_time)
                print(f'   [{elapsed}s] Status: {status} | Power: {power_status}')
                
                if status == 'active' and main_ip and main_ip != '0.0.0.0':
                    print()
                    print('✅ SERVER IS READY!')
                    print('='*80)
                    print()
                    print('🌐 CONNECTION DETAILS:')
                    print(f'   IP Address: {main_ip}')
                    print(f'   RDP Port: 3389')
                    
                    if default_password:
                        print(f'   Username: Administrator')
                        print(f'   Password: {default_password}')
                        password = default_password
                        
                        # Save credentials
                        with open('vultr_rdp_credentials.txt', 'w') as f:
                            f.write(f'Instance ID: {instance_id}\n')
                            f.write(f'IP: {main_ip}\n')
                            f.write(f'Username: Administrator\n')
                            f.write(f'Password: {default_password}\n')
                        
                        print()
                        print('💾 Credentials saved to: vultr_rdp_credentials.txt')
                    else:
                        print('   ⚠️  Password not available yet, check Vultr dashboard')
                    
                    print()
                    print('='*80)
                    print('💰 IMPORTANT: Check Vultr Dashboard for ACTUAL PRICING')
                    print('='*80)
                    print()
                    print('   Go to: https://my.vultr.com/billing/')
                    print('   Look at the hourly/monthly cost for this instance')
                    print('   This will show Windows license cost included!')
                    print()
                    print(f'   Instance ID to track: {instance_id}')
                    print()
                    
                    # Get instance details for cost info
                    print('📊 Instance Details:')
                    print(f'   vCPU: {inst.get("vcpu_count", "N/A")}')
                    print(f'   RAM: {inst.get("ram", "N/A")} MB')
                    print(f'   Disk: {inst.get("disk", "N/A")} GB')
                    print(f'   Bandwidth: {inst.get("allowed_bandwidth", "N/A")} GB')
                    
                    # Try to get cost from instance data
                    if 'monthly_cost' in inst:
                        print(f'   Monthly Cost: ${inst["monthly_cost"]}')
                    
                    break
            else:
                print(f'   ⚠️  Status check failed: {status_response.status_code}')
        else:
            print()
            print('⏱️  Timeout waiting for server')
            print(f'   Instance ID: {instance_id}')
            print('   Check Vultr Control Panel for status')
    
    else:
        print(f'❌ Failed to create server: {response.status_code}')
        print(f'Response: {response.text}')
        
        try:
            error = response.json()
            print()
            print('Error details:')
            print(json.dumps(error, indent=2))
        except:
            pass

except Exception as e:
    print(f'❌ Error: {e}')
    import traceback
    traceback.print_exc()

print()
print('='*80)
print('🧹 CLEANUP: To delete this test server, use:')
print(f'   DELETE {BASE_URL}/instances/{{instance_id}}')
print('='*80)
