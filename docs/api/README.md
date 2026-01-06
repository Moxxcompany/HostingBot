# HostBay REST API Documentation

## Overview

The HostBay REST API provides programmatic access to domain registration, DNS management, hosting services, and more. Built with FastAPI, it features authentication, rate limiting, and comprehensive error handling.

**Base URL:** `https://your-project.repl.co/api/v1`

**Version:** 1.0.0-beta

**⚠️ IMPLEMENTATION STATUS:**
- ✅ **Fully Functional**: API Key Management, Authentication, Rate Limiting, Domain/DNS/Nameserver endpoints
- ✅ **Orchestrator-Integrated**: Hosting bundles, hosting provisioning, domain linking (async processing)
- 🔄 **Async Workflows**: Bundle/hosting/linking operations process asynchronously - check order status for progress

**SECURITY NOTE:** Hosting passwords are NOT stored in the database. The hosting orchestrator manages credentials securely. Use the password reset endpoint to generate new credentials when needed.

**ARCHITECTURE NOTE:** Bundle, hosting, and linking operations use asynchronous orchestration. Requests return immediately with an order ID - check the order status endpoint to track progress. The orchestrator handles retries and state persistence.

## Quick Start

### 1. Get Your API Key

Create an API key via the Telegram bot or through the API itself (requires initial authentication):

```bash
# Using existing Telegram bot auth, create API key
POST /api/v1/keys
{
  "name": "My Production Key",
  "permissions": {
    "domains": {"read": true, "write": true},
    "dns": {"read": true, "write": true},
    "hosting": {"read": true, "write": true}
  },
  "rate_limit_per_hour": 1000
}
```

**⚠️ Important:** The full API key is shown only once! Store it securely.

### 2. Make Your First Request

```bash
curl -H "Authorization: Bearer hbay_live_YOUR_API_KEY" \
     https://your-project.repl.co/api/v1/domains
```

### 3. Explore the API

**Interactive Documentation:**
- Swagger UI: `/api/v1/docs`
- ReDoc: `/api/v1/redoc`

## Authentication

All API requests require a Bearer token in the Authorization header:

```
Authorization: Bearer hbay_live_Ak7mN9pQr2tXvYz4bC6dE8fG1hJ3kL5nP
```

**API Key Format:**
- Prefix: `hbay_`
- Environment: `live` or `test`
- Random 32 characters

## Rate Limiting

Default limits per API key:
- **1,000 requests/hour**
- **10,000 requests/day**

Rate limit headers:
```
X-RateLimit-Limit-Hour: 1000
X-RateLimit-Remaining-Hour: 847
X-RateLimit-Reset: 1730476800
```

## Endpoints Summary

| Category | Endpoints | Description |
|----------|-----------|-------------|
| **Domains** | 15 | Register, transfer, renew, manage domains |
| **DNS** | 10 | CRUD operations for DNS records |
| **Nameservers** | 7 | Update and verify nameservers |
| **Hosting** | 18 | Order, manage hosting subscriptions |
| **Bundles** | 5 | Domain + hosting bundles |
| **Wallet** | 6 | Balance, topup, transactions |
| **Orders** | Included | Order tracking and management |
| **Monitoring** | 8 | Status, propagation, uptime checks |
| **Linking** | 8 | Link external domains to hosting |
| **API Keys** | 6 | Manage API keys and usage |

**Total:** 88 endpoints

## Code Examples

### Python
```python
from hostbay import HostBayAPI

api = HostBayAPI("hbay_live_YOUR_API_KEY")

# Register domain
result = api.register_domain("example.com", contacts={...})

# Create DNS record
dns = api.create_dns_record("example.com", "A", "www", "192.168.1.1")

# Order hosting
hosting = api.order_hosting("example.com", plan="pro_30day")
```

### JavaScript/Node.js
```javascript
const HostBayAPI = require('./hostbay');

const api = new HostBayAPI('hbay_live_YOUR_API_KEY');

// List domains
const domains = await api.listDomains();

// Create DNS record
const dns = await api.createDNSRecord('example.com', 'A', 'www', '192.168.1.1');
```

### cURL
```bash
curl -X POST https://your-project.repl.co/api/v1/domains/register \
  -H "Authorization: Bearer hbay_live_YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"domain_name": "example.com", "period": 1, "contacts": {...}}'
```

## Error Handling

All errors follow a standard format:

```json
{
  "success": false,
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Domain not found",
    "details": {
      "resource": "Domain",
      "identifier": "example.com"
    }
  }
}
```

**Common Error Codes:**
- `AUTHENTICATION_FAILED` (401)
- `PERMISSION_DENIED` (403)
- `RESOURCE_NOT_FOUND` (404)
- `VALIDATION_ERROR` (422)
- `RATE_LIMIT_EXCEEDED` (429)
- `INTERNAL_ERROR` (500)

## Pagination

List endpoints support pagination:

```bash
GET /api/v1/domains?page=2&per_page=50
```

Response includes pagination metadata:
```json
{
  "success": true,
  "data": {
    "domains": [...],
    "total": 150,
    "page": 2,
    "per_page": 50
  }
}
```

## Support

- **Documentation:** `/api/v1/docs`
- **GitHub:** [repository-url]
- **Support:** support@hostbay.com

## Changelog

### v1.0.8 (2025-12-14)
- **White-Label Field Naming**: API responses now include generic field names for brand consistency
  - New fields: `dns_zone_id`, `dns_nameservers`, `registry_id`, `username`, `control_panel_url`
  - **Backward Compatible**: Legacy field names still returned alongside new names
  - Both old and new field names work - no migration required for existing integrations
  - New integrations should use the generic field names
- **Documentation Updated**: Public documentation uses HostBay branding

### v1.0.7 (2025-12-12)
- **Addon Domain New Registration**: Added `register_new` parameter to `POST /hosting/{subscription_id}/addon-domains`
  - Set `register_new: true` to register a NEW domain and add it as addon in one request
  - Requires wallet balance for domain registration fee (10% API discount applies)
  - Auto-configures DNS zone and A records
  - New parameters: `register_new`, `period`, `auto_renew_domain`
  - Example request:
    ```json
    {
      "domain": "newdomain.com",
      "register_new": true,
      "period": 1,
      "auto_renew_domain": true
    }
    ```
  - Response includes `domain_type: "newly_registered"` and `registration` object with payment details
- **User Telegram Notifications for API Orders**: All API orders now send Telegram notifications to users
  - Domain registration via API → User receives confirmation with domain, amount, period
  - Hosting orders (all types) → User receives confirmation with hosting details
  - Addon domain registration → User receives confirmation with subscription info
- **Admin Notifications**: All API orders send admin alerts for monitoring
- **Consistent Notification Parity**: API orders now match Telegram bot order notifications

### v1.0.6 (2025-12-09)
- **API Response Consistency**: Normalized external domain responses between hosting order and addon domain endpoints
  - Both endpoints now return consistent fields: `nameservers`, `server_ip`, `zone_id`, `a_record_status`, `a_records`, `dns_instructions`
  - `dns_instructions.instructions` now uses array format (no empty strings)
  - `dns_instructions.nameservers` uses consistent field name
  - Hosting order: `a_record_status: "pending"` (async provisioning), `zone_id: null`
  - Addon domain: `a_record_status: "configured"` (inline creation), `zone_id: "zone_id"`

### v1.0.5 (2025-12-09)
- **Unified Server Info Endpoint**: Merged `/hosting/server-info` + `/domains/{domain}/link/dns-instructions`
  - Single endpoint: `GET /hosting/server-info`
  - Optional `domain_name` query parameter for personalized DNS instructions
  - Example: `GET /hosting/server-info?domain_name=example.com`
  - DEPRECATED: `GET /domains/{domain_name}/link/dns-instructions`

### v1.0.4 (2025-12-09)
- **BREAKING: Unified Hosting Order Endpoint**: Merged 3 endpoints into single `POST /hosting/order`
  - Replaces: `/hosting/order`, `/hosting/order-existing`, `/hosting/order-external`
  - New `domain_type` parameter: `new`, `existing`, or `external`
  - All domain types now properly provision hosting and finalize wallet payment
- **External Domain Flow Fixed**: External domains now fully provision hosting (was previously incomplete)
  - Creates hosting account
  - Creates DNS zone
  - Finalizes wallet payment
  - Returns `nameserver_status` and `dns_instructions` for user to configure DNS at their registrar
- **Request Body Changes**:
  ```json
  {
    "domain_name": "example.com",
    "domain_type": "new|existing|external",
    "plan": "pro_30day",
    "period": 1,
    "linking_mode": "nameserver",
    "auto_renew": true
  }
  ```

### v1.0.3 (2025-12-09)
- **Addon Domain Nameserver Auto-Update**: When adding addon domains via `POST /hosting/{subscription_id}/addon-domains`:
  - HostBay domains: Nameservers are automatically updated to HostBay DNS if not already configured
  - External domains: Returns DNS configuration instructions with HostBay nameservers
- Response includes `nameserver_status` field: `auto_updated`, `already_configured`, `update_failed`, or `manual_update_required`

### v1.0.2 (2025-12-08)
- Added addon domain management endpoints (list, create, delete)
- Dynamic nameserver fetching from API
- Enhanced server-info endpoint with dynamic nameserver data

### v1.0.1 (2025-12-01)
- PostgreSQL type mismatch fixes for order lookups
- Improved error handling and validation

### v1.0.0 (2025-10-31)
- Initial release
- 88 endpoints across 10 categories
- API key authentication
- Rate limiting
- Multi-language examples
