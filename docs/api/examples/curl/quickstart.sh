#!/bin/bash

# HostBay API - cURL Examples
# Set your API key
API_KEY="hbay_live_YOUR_API_KEY"
BASE_URL="https://your-project.repl.co/api/v1"

# Helper function for API calls
api_call() {
  curl -s -H "Authorization: Bearer $API_KEY" \
       -H "Content-Type: application/json" \
       "$@"
}

echo "=== HostBay API Examples ==="

# 1. List domains
echo -e "\n1. List domains:"
api_call "$BASE_URL/domains?page=1&per_page=10"

# 2. Get wallet balance
echo -e "\n\n2. Get wallet balance:"
api_call "$BASE_URL/wallet/balance"

# 3. Create DNS record
echo -e "\n\n3. Create DNS record:"
api_call -X POST "$BASE_URL/domains/example.com/dns/records" \
  -d '{
    "type": "A",
    "name": "www",
    "content": "192.168.1.1",
    "ttl": 300,
    "proxied": false
  }'

# 4. Update nameservers
echo -e "\n\n4. Update nameservers:"
api_call -X PUT "$BASE_URL/domains/example.com/nameservers" \
  -d '{
    "nameservers": [
      "ns1.hostbay.com",
      "ns2.hostbay.com"
    ]
  }'

# 5. Order hosting
echo -e "\n\n5. Order hosting for existing domain:"
api_call -X POST "$BASE_URL/hosting/order-existing" \
  -d '{
    "domain_name": "example.com",
    "plan": "pro_30day",
    "period": 1
  }'

# 6. Get hosting plans
echo -e "\n\n6. Get hosting plans:"
api_call "$BASE_URL/hosting/plans"

# 7. List DNS records
echo -e "\n\n7. List DNS records:"
api_call "$BASE_URL/domains/example.com/dns/records"

# 8. Get system status
echo -e "\n\n8. Get system status:"
api_call "$BASE_URL/system/status"

echo -e "\n\n=== Examples complete ==="
