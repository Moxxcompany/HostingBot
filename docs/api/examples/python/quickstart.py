"""
HostBay API - Python Quickstart Guide

Install required package:
    pip install requests
"""
import requests


class HostBayAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://your-project.repl.co/api/v1"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    def register_domain(self, domain_name, contacts, period=1):
        """Register a new domain"""
        response = requests.post(
            f"{self.base_url}/domains/register",
            headers=self.headers,
            json={
                "domain_name": domain_name,
                "period": period,
                "auto_renew": True,
                "contacts": contacts,
                "privacy_protection": False
            }
        )
        return response.json()
    
    def list_domains(self, page=1, per_page=50):
        """List all domains"""
        response = requests.get(
            f"{self.base_url}/domains",
            headers=self.headers,
            params={"page": page, "per_page": per_page}
        )
        return response.json()
    
    def create_dns_record(self, domain_name, record_type, name, content, ttl=300):
        """Create a DNS record"""
        response = requests.post(
            f"{self.base_url}/domains/{domain_name}/dns/records",
            headers=self.headers,
            json={
                "type": record_type,
                "name": name,
                "content": content,
                "ttl": ttl,
                "proxied": False
            }
        )
        return response.json()
    
    def update_nameservers(self, domain_name, nameservers):
        """Update domain nameservers"""
        response = requests.put(
            f"{self.base_url}/domains/{domain_name}/nameservers",
            headers=self.headers,
            json={"nameservers": nameservers}
        )
        return response.json()
    
    def order_hosting(self, domain_name, plan="pro_30day", period=1):
        """Order hosting for existing domain"""
        response = requests.post(
            f"{self.base_url}/hosting/order-existing",
            headers=self.headers,
            json={
                "domain_name": domain_name,
                "plan": plan,
                "period": period
            }
        )
        return response.json()
    
    def get_wallet_balance(self):
        """Get wallet balance"""
        response = requests.get(
            f"{self.base_url}/wallet/balance",
            headers=self.headers
        )
        return response.json()


if __name__ == "__main__":
    api = HostBayAPI("hbay_live_YOUR_API_KEY")
    
    print("1. List domains:")
    domains = api.list_domains()
    print(f"Found {domains['data']['total']} domains")
    
    print("\n2. Get wallet balance:")
    balance = api.get_wallet_balance()
    print(f"Balance: ${balance['data']['balance']}")
    
    print("\n3. Create DNS record:")
    dns_result = api.create_dns_record(
        domain_name="example.com",
        record_type="A",
        name="www",
        content="192.168.1.1"
    )
    print(f"DNS record created: {dns_result}")
