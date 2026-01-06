#!/usr/bin/env python3
"""
Create a test Windows RDP server via UpCloud API
This will show us the REAL costs and provisioning flow
"""

import os
import requests
from requests.auth import HTTPBasicAuth
import json
import time

API_USER = os.environ.get('UPCLOUD_API_USER')
API_PASS = os.environ.get('UPCLOUD_API_PASSWORD')
BASE_URL = 'https://api.upcloud.com/1.3'
auth = HTTPBasicAuth(API_USER, API_PASS)

print('='*80)
print('🧪 CREATING TEST WINDOWS SERVER')
print('='*80)
print()

# Use smallest Windows Server for testing
# Windows Server 2022 Standard (smallest license cost)
server_config = {
    "server": {
        "zone": "us-nyc1",
        "title": "HostBay-Test-Windows-2022",
        "hostname": "test-win2022.hostbay.io",
        "plan": "2xCPU-4GB",  # Smallest suitable plan
        "metadata": "yes",
        "storage_devices": {
            "storage_device": [
                {
                    "action": "clone",
                    "storage": "01000000-0000-4000-8000-000010080300",  # Windows 2022 Standard
                    "title": "Windows System Disk",
                    "size": 50,  # Minimum for Windows
                    "tier": "maxiops"
                }
            ]
        },
        "login_user": {
            "create_password": "yes"
        }
    }
}

print('📋 Server Configuration:')
print(f'   OS: Windows Server 2022 Standard')
print(f'   Plan: 2xCPU-4GB')
print(f'   Zone: New York (us-nyc1)')
print(f'   Storage: 50 GB MaxIOPS')
print()
print('⏳ Creating server...')
print()

try:
    response = requests.post(
        f'{BASE_URL}/server',
        auth=auth,
        json=server_config,
        timeout=30
    )
    
    if response.status_code == 202:
        server = response.json()['server']
        
        print('✅ SERVER CREATED!')
        print('='*80)
        print()
        print(f'🆔 Server UUID: {server["uuid"]}')
        print(f'📛 Title: {server["title"]}')
        print(f'🖥️  Hostname: {server["hostname"]}')
        print(f'⚡ State: {server["state"]}')
        print(f'💻 Plan: {server.get("plan", "N/A")}')
        print(f'🔢 CPU Cores: {server.get("core_number", "N/A")}')
        print(f'💾 RAM: {server.get("memory_amount", "N/A")} MB')
        print()
        
        # CRITICAL: Save the admin password!
        if 'password' in server:
            print('🔐 ADMINISTRATOR PASSWORD (SAVE THIS NOW!):')
            print('='*80)
            print(f'   Password: {server["password"]}')
            print('='*80)
            print()
            print('⚠️  This password is shown ONCE and cannot be retrieved later!')
            print()
            
            # Save to file for reference
            with open('test_windows_server_credentials.txt', 'w') as f:
                f.write(f'Server UUID: {server["uuid"]}\n')
                f.write(f'Hostname: {server["hostname"]}\n')
                f.write(f'Username: Administrator\n')
                f.write(f'Password: {server["password"]}\n')
                f.write(f'Created: {time.strftime("%Y-%m-%d %H:%M:%S")}\n')
            
            print('💾 Credentials saved to: test_windows_server_credentials.txt')
            print()
        
        # Check license field
        if 'license' in server:
            print(f'📜 License cost: ${server["license"]}/hour')
            print()
        
        # Poll for server to become ready
        print('⏳ Waiting for server to start (this may take 2-5 minutes)...')
        print()
        
        uuid = server['uuid']
        start_time = time.time()
        max_wait = 600  # 10 minutes max
        
        while time.time() - start_time < max_wait:
            time.sleep(10)
            
            status_response = requests.get(
                f'{BASE_URL}/server/{uuid}',
                auth=auth,
                timeout=10
            )
            
            if status_response.status_code == 200:
                status = status_response.json()['server']
                state = status['state']
                elapsed = int(time.time() - start_time)
                
                print(f'   [{elapsed}s] State: {state}')
                
                if state == 'started':
                    print()
                    print('✅ SERVER IS READY!')
                    print('='*80)
                    print()
                    
                    # Get IP address
                    ip_addresses = status.get('ip_addresses', {}).get('ip_address', [])
                    public_ip = next(
                        (ip['address'] for ip in ip_addresses 
                         if ip.get('access') == 'public' and ip.get('family') == 'IPv4'),
                        None
                    )
                    
                    if public_ip:
                        print(f'🌐 Public IP: {public_ip}')
                        print()
                        print('📋 RDP CONNECTION INFO:')
                        print(f'   Host: {public_ip}')
                        print(f'   Port: 3389')
                        print(f'   Username: Administrator')
                        print(f'   Password: (saved in test_windows_server_credentials.txt)')
                        print()
                    
                    # Show licensing info from status
                    if 'license' in status:
                        license_cost = status['license']
                        print(f'💰 LICENSE COST: ${license_cost}/hour per core')
                        
                        # Calculate monthly cost
                        cores = status.get('core_number', 0)
                        monthly_license = license_cost * cores * 730
                        print(f'   With {cores} cores: ${monthly_license:.2f}/month just for Windows license')
                        print()
                    
                    print('='*80)
                    print('🎯 IMPORTANT: Check your UpCloud billing to see actual charges!')
                    print('='*80)
                    print()
                    print(f'💡 Server UUID for cleanup: {uuid}')
                    print('   Use DELETE /1.3/server/{uuid} to remove it')
                    
                    break
                elif state == 'error':
                    print()
                    print('❌ Server encountered an error!')
                    break
            else:
                print(f'   ⚠️  Status check failed: {status_response.status_code}')
        else:
            print()
            print('⏱️  Timeout waiting for server to start')
            print(f'   Server UUID: {uuid}')
            print('   Check UpCloud Control Panel for status')
    
    else:
        print(f'❌ Failed to create server: {response.status_code}')
        print(f'Response: {response.text}')
        
        # Try to parse error
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
