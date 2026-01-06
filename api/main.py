"""
HostBay REST API v1

Main API application with authentication, rate limiting, and routing.
"""
import logging
import time
import os
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.openapi.utils import get_openapi
from api.utils.errors import APIError
from api.services.rate_limit_service import RateLimitService

logger = logging.getLogger(__name__)

def get_api_servers():
    """
    Automatically detect and configure API server URLs for documentation.
    
    Returns list of server configurations for FastAPI/OpenAPI docs.
    Reads environment variables dynamically to support changing development URLs.
    """
    servers = []
    
    dev_domain = os.environ.get('REPLIT_DEV_DOMAIN') or os.environ.get('REPLIT_DOMAINS')
    if dev_domain:
        servers.append({
            "url": f"https://{dev_domain}",
            "description": "Current Server (Development)"
        })
    
    servers.extend([
        {
            "url": "https://developers.hostbay.io",
            "description": "Production Server"
        },
        {
            "url": "https://staging.hostbay.io",
            "description": "Staging Server"
        }
    ])
    
    return servers

app = FastAPI(
    title="HostBay API",
    description="Production-ready REST API for programmatic domain and hosting management",
    version="1.0.0",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
    servers=get_api_servers()
)

def custom_openapi():
    """
    Generate OpenAPI schema with dynamic server URLs.
    
    Reads environment variables on each call to ensure server URLs are always current.
    This allows the development URL to update automatically if the Replit domain changes.
    """
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        servers=get_api_servers(),
    )
    return openapi_schema

app.openapi = custom_openapi

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Log all API requests"""
    start_time = time.time()
    
    try:
        response = await call_next(request)
        process_time = int((time.time() - start_time) * 1000)
        
        api_key_id = getattr(request.state, "api_key_id", None)
        if api_key_id:
            await RateLimitService.log_request(
                api_key_id=api_key_id,
                endpoint=request.url.path,
                method=request.method,
                status_code=response.status_code,
                response_time_ms=process_time,
                request_ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent")
            )
        
        response.headers["X-Process-Time-Ms"] = str(process_time)
        return response
        
    except Exception as e:
        logger.error(f"Request processing error: {e}")
        raise


@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError):
    """Handle custom API errors"""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail
    )


@app.get("/api/v1")
async def api_root():
    """API root endpoint"""
    return {
        "name": "HostBay API",
        "version": "1.0.0",
        "documentation": "/api/v1/docs",
        "endpoints": {
            "domains": "/api/v1/domains",
            "dns": "/api/v1/domains/{domain_name}/dns",
            "nameservers": "/api/v1/domains/{domain_name}/nameservers",
            "hosting": "/api/v1/hosting",
            "bundles": "/api/v1/bundles",
            "wallet": "/api/v1/wallet",
            "orders": "/api/v1/orders",
            "monitoring": "/api/v1/system",
            "linking": "/api/v1/domains/{domain_name}/link",
            "api_keys": "/api/v1/keys"
        }
    }


from api.routes import (
    domains,
    dns,
    nameservers,
    hosting,
    bundles,
    wallet,
    monitoring,
    linking,
    api_keys,
    status
)

app.include_router(domains.router, prefix="/api/v1", tags=["Domains"])
app.include_router(dns.router, prefix="/api/v1", tags=["DNS"])
app.include_router(nameservers.router, prefix="/api/v1", tags=["Nameservers"])
app.include_router(hosting.router, prefix="/api/v1", tags=["Hosting"])
app.include_router(bundles.router, prefix="/api/v1", tags=["Bundles"])
app.include_router(wallet.router, prefix="/api/v1", tags=["Wallet"])
app.include_router(monitoring.router, prefix="/api/v1", tags=["Monitoring"])
app.include_router(linking.router, prefix="/api/v1", tags=["Domain Linking"])
app.include_router(api_keys.router, prefix="/api/v1", tags=["API Keys"])
app.include_router(status.router, prefix="/api/v1", tags=["Status"])

logger.info("✅ HostBay REST API v1 initialized")
