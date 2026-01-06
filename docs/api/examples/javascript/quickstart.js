/**
 * HostBay API - JavaScript/Node.js Quickstart Guide
 * 
 * Install required package:
 *     npm install axios
 */
const axios = require('axios');


class HostBayAPI {
  constructor(apiKey) {
    this.apiKey = apiKey;
    this.baseUrl = 'https://your-project.repl.co/api/v1';
    this.headers = {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/json'
    };
  }
  
  async registerDomain(domainName, contacts, period = 1) {
    const response = await axios.post(
      `${this.baseUrl}/domains/register`,
      {
        domain_name: domainName,
        period: period,
        auto_renew: true,
        contacts: contacts,
        privacy_protection: false
      },
      { headers: this.headers }
    );
    return response.data;
  }
  
  async listDomains(page = 1, perPage = 50) {
    const response = await axios.get(
      `${this.baseUrl}/domains`,
      {
        headers: this.headers,
        params: { page, per_page: perPage }
      }
    );
    return response.data;
  }
  
  async createDNSRecord(domainName, recordType, name, content, ttl = 300) {
    const response = await axios.post(
      `${this.baseUrl}/domains/${domainName}/dns/records`,
      {
        type: recordType,
        name: name,
        content: content,
        ttl: ttl,
        proxied: false
      },
      { headers: this.headers }
    );
    return response.data;
  }
  
  async updateNameservers(domainName, nameservers) {
    const response = await axios.put(
      `${this.baseUrl}/domains/${domainName}/nameservers`,
      { nameservers: nameservers },
      { headers: this.headers }
    );
    return response.data;
  }
  
  async orderHosting(domainName, plan = 'pro_30day', period = 1) {
    const response = await axios.post(
      `${this.baseUrl}/hosting/order-existing`,
      {
        domain_name: domainName,
        plan: plan,
        period: period
      },
      { headers: this.headers }
    );
    return response.data;
  }
  
  async getWalletBalance() {
    const response = await axios.get(
      `${this.baseUrl}/wallet/balance`,
      { headers: this.headers }
    );
    return response.data;
  }
}


// Example usage
async function main() {
  const api = new HostBayAPI('hbay_live_YOUR_API_KEY');
  
  try {
    // 1. List domains
    console.log('1. List domains:');
    const domains = await api.listDomains();
    console.log(`Found ${domains.data.total} domains`);
    
    // 2. Get wallet balance
    console.log('\n2. Get wallet balance:');
    const balance = await api.getWalletBalance();
    console.log(`Balance: $${balance.data.balance}`);
    
    // 3. Create DNS record
    console.log('\n3. Create DNS record:');
    const dnsResult = await api.createDNSRecord(
      'example.com',
      'A',
      'www',
      '192.168.1.1'
    );
    console.log('DNS record created:', dnsResult);
    
  } catch (error) {
    console.error('Error:', error.response?.data || error.message);
  }
}


if (require.main === module) {
  main();
}


module.exports = HostBayAPI;
