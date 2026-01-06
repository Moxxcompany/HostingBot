#!/usr/bin/env python3
"""
Telegram Bot Startup Script - Production Ready with Robust Error Handling
Environment validation, database initialization, and auto-recovery mechanisms
"""

import os
import sys
import asyncio
import logging
import time
import signal
from typing import Optional

# Configure logging early to capture startup issues
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s'
)

# SPAM FIX: Suppress aiohttp access logs for successful requests but keep errors  
logging.getLogger("aiohttp.access").setLevel(logging.WARNING)

# Lazy imports to handle missing dependencies gracefully
try:
    from brand_config import get_platform_name
    from health_monitor import get_health_monitor, log_error, log_restart
    from admin_alerts import send_critical_alert, send_error_alert, send_warning_alert
except ImportError as e:
    # FIXED: Use print instead of logger before it's initialized
    print(f"Warning: Import error during startup: {e}")
    get_platform_name = lambda: os.getenv('PLATFORM_NAME', 'HostBay')
    get_health_monitor = lambda: None
    log_error = lambda msg: None
    log_restart = lambda: None
    # Fallback functions for admin alerts
    send_critical_alert = lambda *args, **kwargs: None
    send_error_alert = lambda *args, **kwargs: None
    send_warning_alert = lambda *args, **kwargs: None

# Set default payment provider if not already configured
if not os.getenv('CRYPTO_PAYMENT_PROVIDER'):
    os.environ['CRYPTO_PAYMENT_PROVIDER'] = 'blockbee'
    logging.info("🔄 Set CRYPTO_PAYMENT_PROVIDER=blockbee as default")

# Environment-based control: Allow both development and production environments
environment = os.getenv('ENVIRONMENT', 'development').lower()
logger_temp = logging.getLogger(__name__)
logger_temp.info(f"🌍 Running in {environment} environment")

logger = logging.getLogger(__name__)

# Global shutdown flag for graceful termination
_shutdown_requested = False

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global _shutdown_requested
    _shutdown_requested = True
    logger.info(f"🛑 Shutdown signal received ({signum}), initiating graceful shutdown...")

def validate_environment(retry_attempt: int = 0) -> bool:
    """Validate required environment variables with degraded mode support"""
    required_vars = [
        'TELEGRAM_BOT_TOKEN',
        'DATABASE_URL'
    ]
    
    optional_vars = [
        'PLATFORM_NAME',
        'OPENPROVIDER_EMAIL',
        'OPENPROVIDER_PASSWORD',
        'CLOUDFLARE_EMAIL', 
        'CLOUDFLARE_API_KEY',
        'BLOCKBEE_API_KEY'
    ]
    
    missing_required = []
    missing_optional = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_required.append(var)
    
    for var in optional_vars:
        if not os.getenv(var):
            missing_optional.append(var)
    
    if missing_required:
        if retry_attempt == 0:
            logger.error(f"❌ Missing required environment variables: {', '.join(missing_required)}")
            logger.info("💡 Tip: Set these environment variables in your Replit secrets or .env file")
            logger.info("🔄 Will retry environment validation in production mode...")
        else:
            logger.warning(f"⚠️ Still missing required variables on retry {retry_attempt}: {', '.join(missing_required)}")
        return False
    
    if missing_optional:
        logger.warning(f"⚠️ Missing optional environment variables: {', '.join(missing_optional)}")
        logger.warning("📝 Some features (domain registration, DNS management, payments) may not work without these variables")
        logger.info("✅ Bot will run in limited mode - basic commands will still work")
    
    logger.info("✅ Environment validation passed - all required variables found")
    return True

def init_database_with_retry(max_retries: int = 3, base_delay: float = 1.0) -> bool:
    """Initialize database with exponential backoff retry"""
    global _shutdown_requested
    
    for attempt in range(max_retries):
        if _shutdown_requested:
            logger.info("🛑 Shutdown requested during database initialization")
            return False
            
        try:
            logger.info(f"🔄 Database initialization attempt {attempt + 1}/{max_retries}")
            # Lazy import database to handle missing dependencies
            try:
                from database import init_database
                asyncio.run(init_database())
                logger.info("✅ Database initialization completed successfully")
                return True
            except ImportError as e:
                logger.error(f"❌ Database module import failed: {e}")
                logger.info("🔄 Bot will continue in degraded mode - database features unavailable")
                return False
            
        except Exception as e:
            delay = base_delay * (2 ** attempt)  # Exponential backoff
            
            if attempt < max_retries - 1:
                logger.warning(f"⚠️ Database initialization failed (attempt {attempt + 1}/{max_retries}): {e}")
                logger.info(f"⏰ Retrying in {delay:.1f} seconds...")
                time.sleep(delay)
            else:
                logger.error(f"❌ Database initialization failed after {max_retries} attempts: {e}")
                logger.info("🔄 Bot will continue in degraded mode - some features may not work")
                return False
    
    return False

def start_consolidated_bot() -> bool:
    """Start bot with consolidated single event loop"""
    global _shutdown_requested
    
    if _shutdown_requested:
        logger.info("🛑 Shutdown requested during bot startup")
        return False
        
    try:
        logger.info("🚀 Starting consolidated bot with single event loop...")
        
        # Import consolidated bot module
        import importlib
        if 'bot' in sys.modules:
            importlib.reload(sys.modules['bot'])
        
        from bot import main as bot_main
        logger.info("✅ Starting consolidated Telegram bot...")
        
        # Run consolidated bot (handles everything in single event loop)
        result = bot_main()
        
        if result:
            logger.info("✅ Bot stopped normally")
            return True
        else:
            logger.warning("⚠️ Bot returned failure status")
            return False
            
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user (Ctrl+C)")
        return True
        
    except Exception as e:
        logger.error(f"❌ Critical bot startup failure: {e}")
        logger.error("🆘 Consolidated bot failed - this indicates a serious issue")
        
        # Log error to health monitor
        log_error(f"Consolidated bot startup failed: {e}")
        log_restart()
        
        # Fail fast - exit for supervisor restart
        logger.error("💥 FAIL FAST: Exiting for supervisor restart")
        sys.exit(1)
    
    return False

def main():
    """Main startup function with comprehensive error handling and recovery"""
    global _shutdown_requested
    
    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    logger.info(f"🚀 Starting {get_platform_name()} Telegram Bot with production stability...")
    logger.info("🛡️ Enhanced error handling and auto-recovery enabled")
    
    startup_success = False
    environment_retries = 0
    max_environment_retries = 3
    
    try:
        # Environment validation with retries
        while not startup_success and environment_retries < max_environment_retries and not _shutdown_requested:
            if validate_environment(environment_retries):
                startup_success = True
                break
            
            environment_retries += 1
            if environment_retries < max_environment_retries:
                logger.info(f"⏰ Retrying environment validation in 5 seconds... (attempt {environment_retries + 1}/{max_environment_retries})")
                time.sleep(5)
        
        if not startup_success:
            logger.error("❌ Environment validation failed after all retries")
            logger.info("🔄 Bot will attempt to continue in emergency mode - limited functionality")
            # Don't exit - try to continue with basic functionality
        
        # Database initialization with retry (non-blocking failure)
        if not _shutdown_requested:
            database_ready = init_database_with_retry(max_retries=3, base_delay=1.0)
            if not database_ready:
                logger.warning("⚠️ Database not available - bot will run in read-only mode")
        
        # Start consolidated bot 
        if not _shutdown_requested:
            logger.info("🚀 Starting consolidated single event loop bot...")
            bot_started = start_consolidated_bot()
            if not bot_started:
                logger.error("💥 Consolidated bot could not be started")
                logger.info("🔧 Check logs above for specific error details")
                logger.error("💥 FAIL FAST: Exiting for supervisor restart")
                sys.exit(1)
    
    except KeyboardInterrupt:
        logger.info("🛑 Startup interrupted by user")
    except Exception as e:
        logger.error(f"💥 Critical startup error: {e}")
        logger.info("🔧 This may indicate a serious configuration or dependency issue")
    finally:
        logger.info("🏁 Bot startup process completed")
        
        # Graceful cleanup
        if _shutdown_requested:
            logger.info("✅ Graceful shutdown completed")
        else:
            logger.info("⚠️ Startup process ended - check logs for issues")

if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    
    # Run the main function
    main()