"""
OpenProvider Credential Validation Service

Periodically validates OpenProvider account credentials.
Detects expired or revoked credentials and alerts admins.
"""
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class CredentialReconciliationService:
    """Service to validate and reconcile OpenProvider account credentials"""
    
    def __init__(self):
        self._running = False
        self._last_run: Optional[datetime] = None
        self._stats = {
            'total_runs': 0,
            'accounts_checked': 0,
            'valid_accounts': 0,
            'invalid_accounts': 0,
            'last_error': None
        }
    
    async def validate_all_credentials(self, notify_admin: bool = False) -> Dict:
        """
        Validate credentials for all OpenProvider accounts.
        
        Returns:
            Summary of validation results
        """
        from database import execute_query, execute_update
        
        start_time = datetime.now(timezone.utc)
        self._running = True
        
        summary = {
            'accounts_checked': 0,
            'valid_accounts': 0,
            'invalid_accounts': 0,
            'account_details': [],
            'errors': [],
            'duration_seconds': 0
        }
        
        try:
            logger.info("🔄 Starting OpenProvider credential validation...")
            
            try:
                from services.openprovider_manager import get_account_manager
                openprovider_manager = get_account_manager()
            except ImportError:
                summary['errors'].append("OpenProvider manager not available")
                logger.warning("⚠️ OpenProvider manager not available")
                return summary
            
            accounts = await execute_query(
                """SELECT id, account_name, username, is_active, is_default
                   FROM openprovider_accounts
                   WHERE is_active = TRUE"""
            )
            
            if not accounts:
                logger.info("ℹ️ No active OpenProvider accounts to validate")
                return summary
            
            logger.info(f"📊 Found {len(accounts)} active OpenProvider accounts to validate")
            
            for account in accounts:
                summary['accounts_checked'] += 1
                account_id = account.get('id')
                account_name = account.get('account_name')
                username = account.get('username')
                
                account_result = {
                    'id': account_id,
                    'name': account_name,
                    'username': username,
                    'valid': False,
                    'error': None
                }
                
                try:
                    op_account = openprovider_manager.get_account(account_id)
                    
                    if op_account:
                        auth_result = await op_account.authenticate()
                        
                        if auth_result:
                            account_result['valid'] = True
                            summary['valid_accounts'] += 1
                            logger.info(f"✅ Account {account_name} credentials valid")
                        else:
                            account_result['error'] = 'Authentication failed'
                            summary['invalid_accounts'] += 1
                            logger.warning(f"⚠️ Account {account_name} authentication failed")
                            
                            await execute_update(
                                """UPDATE openprovider_accounts 
                                   SET notes = COALESCE(notes, '') || E'\n[' || CURRENT_TIMESTAMP || '] Auth validation failed',
                                       updated_at = CURRENT_TIMESTAMP
                                   WHERE id = %s""",
                                (account_id,)
                            )
                    else:
                        account_result['error'] = 'Failed to get account service'
                        summary['invalid_accounts'] += 1
                        
                except Exception as e:
                    account_result['error'] = str(e)
                    summary['invalid_accounts'] += 1
                    logger.error(f"❌ Error validating account {account_name}: {e}")
                
                summary['account_details'].append(account_result)
                await asyncio.sleep(0.5)
            
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            summary['duration_seconds'] = duration
            
            self._stats['total_runs'] += 1
            self._stats['accounts_checked'] += summary['accounts_checked']
            self._stats['valid_accounts'] += summary['valid_accounts']
            self._stats['invalid_accounts'] += summary['invalid_accounts']
            self._last_run = datetime.now(timezone.utc)
            
            logger.info(f"✅ Credential validation complete: {summary['accounts_checked']} checked, "
                       f"{summary['valid_accounts']} valid, "
                       f"{summary['invalid_accounts']} invalid in {duration:.1f}s")
            
            if notify_admin and summary['invalid_accounts'] > 0:
                await self._notify_admin(summary)
                
        except Exception as e:
            summary['errors'].append(str(e))
            self._stats['last_error'] = str(e)
            logger.error(f"❌ Credential validation failed: {e}")
        finally:
            self._running = False
        
        return summary
    
    async def validate_cloudflare_credentials(self) -> Dict:
        """Validate Cloudflare API credentials"""
        result = {'valid': False, 'error': None}
        
        try:
            from services.cloudflare import cloudflare
            
            zones = await cloudflare.list_zones()
            if zones is not None:
                result['valid'] = True
                result['zones_count'] = len(zones)
                logger.info(f"✅ Cloudflare credentials valid ({len(zones)} zones)")
            else:
                result['error'] = 'Failed to list zones'
                
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"❌ Cloudflare credential validation failed: {e}")
        
        return result
    
    async def validate_cpanel_credentials(self) -> Dict:
        """Validate cPanel/WHM credentials"""
        result = {'valid': False, 'error': None}
        
        try:
            from services.cpanel import CPanelService
            cpanel = CPanelService()
            
            accounts = await asyncio.to_thread(cpanel.list_accounts)
            if accounts is not None:
                result['valid'] = True
                result['accounts_count'] = len(accounts)
                logger.info(f"✅ cPanel credentials valid ({len(accounts)} accounts)")
            else:
                result['error'] = 'Failed to list accounts'
                
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"❌ cPanel credential validation failed: {e}")
        
        return result
    
    async def validate_vultr_credentials(self) -> Dict:
        """Validate Vultr API credentials"""
        result = {'valid': False, 'error': None}
        
        try:
            from services.vultr import VultrService
            vultr = VultrService()
            
            instances = vultr.list_instances()
            if instances is not None:
                result['valid'] = True
                result['instances_count'] = len(instances)
                logger.info(f"✅ Vultr credentials valid ({len(instances)} instances)")
            else:
                result['error'] = 'Failed to list instances'
                
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"❌ Vultr credential validation failed: {e}")
        
        return result
    
    async def validate_all_service_credentials(self) -> Dict:
        """Validate credentials for all external services"""
        
        logger.info("🔄 Starting comprehensive credential validation...")
        
        results = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'services': {}
        }
        
        op_result, cf_result, cp_result, vultr_result = await asyncio.gather(
            self.validate_all_credentials(),
            self.validate_cloudflare_credentials(),
            self.validate_cpanel_credentials(),
            self.validate_vultr_credentials(),
            return_exceptions=True
        )
        
        results['services']['openprovider'] = op_result if not isinstance(op_result, Exception) else {'error': str(op_result)}
        results['services']['cloudflare'] = cf_result if not isinstance(cf_result, Exception) else {'error': str(cf_result)}
        results['services']['cpanel'] = cp_result if not isinstance(cp_result, Exception) else {'error': str(cp_result)}
        results['services']['vultr'] = vultr_result if not isinstance(vultr_result, Exception) else {'error': str(vultr_result)}
        
        valid_count = sum(1 for s in results['services'].values() if s.get('valid'))
        results['summary'] = {
            'total_services': len(results['services']),
            'valid_services': valid_count,
            'invalid_services': len(results['services']) - valid_count
        }
        
        logger.info(f"✅ Credential validation complete: {valid_count}/{len(results['services'])} services valid")
        
        return results
    
    async def _notify_admin(self, summary: Dict):
        """Log admin notification about validation results"""
        try:
            invalid_accounts = [a for a in summary.get('account_details', []) if not a.get('valid')]
            
            message = (
                f"⚠️ OpenProvider Credential Alert - "
                f"{summary['invalid_accounts']} account(s) have invalid credentials: "
                f"{', '.join(a.get('name', 'Unknown') for a in invalid_accounts)}"
            )
            
            logger.warning(f"📬 {message}")
            
        except Exception as e:
            logger.error(f"Failed to log admin notification: {e}")
    
    def get_stats(self) -> Dict:
        """Get validation service statistics"""
        return {
            **self._stats,
            'is_running': self._running,
            'last_run': self._last_run.isoformat() if self._last_run else None
        }


credential_reconciliation = CredentialReconciliationService()


async def run_credential_validation():
    """Entry point for scheduled credential validation job"""
    logger.info("📅 Scheduled credential validation starting...")
    result = await credential_reconciliation.validate_all_credentials(notify_admin=True)
    return result
