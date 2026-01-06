"""
Verification Service - Phase 1 Foundation
Handles domain ownership verification and DNS propagation monitoring

This service provides:
- DNS propagation checking with exponential backoff
- Domain ownership verification methods
- Background verification scheduling
- Integration with domain linking workflow
"""

import asyncio
import logging
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta, timezone
from enum import Enum

from database import execute_query, execute_update

logger = logging.getLogger(__name__)


class VerificationType(Enum):
    """Types of verification supported"""
    DNS_TXT = "dns_txt"
    NAMESERVER_CHANGE = "nameserver_change"
    DNS_PROPAGATION = "dns_propagation"
    OWNERSHIP_TOKEN = "ownership_token"


class VerificationStatus(Enum):
    """Verification status states"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class VerificationService:
    """
    Service for handling domain verifications during the linking process.
    
    Phase 1: Basic verification framework
    Phase 2: Will add advanced verification methods and scheduling
    """
    
    def __init__(self):
        self.max_verification_time = timedelta(hours=24)
        self.default_check_interval = timedelta(minutes=5)
    
    async def create_verification(
        self,
        domain_link_intent_id: int,
        verification_type: str,
        verification_step: str,
        expected_value: Optional[str] = None,
        verification_method: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new verification task for a domain linking intent.
        
        Args:
            domain_link_intent_id: ID of the domain linking intent
            verification_type: Type of verification (dns_txt, nameserver_change, etc.)
            verification_step: Specific step being verified
            expected_value: Expected value for verification
            verification_method: Method to use for verification
            
        Returns:
            Dict with verification_id and details
        """
        logger.info(f"🔍 VERIFICATION: Creating {verification_type} verification for intent {domain_link_intent_id}")
        
        try:
            verification_data = await execute_query("""
                INSERT INTO domain_verifications (
                    domain_link_intent_id, verification_type, verification_step,
                    status, verification_method, expected_value,
                    next_check_at, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
                ) RETURNING id, status, created_at
            """, (
                domain_link_intent_id, verification_type, verification_step,
                VerificationStatus.PENDING.value, verification_method, expected_value,
                datetime.now(timezone.utc) + self.default_check_interval
            ))
            
            if not verification_data:
                raise Exception("Failed to create verification")
                
            verification_id = verification_data[0]['id']
            logger.info(f"✅ VERIFICATION: Created verification {verification_id}")
            
            return {
                'success': True,
                'verification_id': verification_id,
                'status': VerificationStatus.PENDING.value,
                'next_check_at': (datetime.now(timezone.utc) + self.default_check_interval).isoformat()
            }
            
        except Exception as e:
            logger.error(f"💥 VERIFICATION: Failed to create verification: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_verification_status(self, verification_id: int) -> Optional[Dict[str, Any]]:
        """Get current status of a verification"""
        verification_data = await execute_query("""
            SELECT 
                id, domain_link_intent_id, verification_type, verification_step,
                status, verification_method, expected_value, actual_value,
                check_details, error_message, retry_count,
                next_check_at, first_checked_at, last_checked_at,
                completed_at, created_at, updated_at
            FROM domain_verifications 
            WHERE id = %s
        """, (verification_id,))
        
        if not verification_data:
            return None
            
        return verification_data[0]
    
    async def update_verification_status(
        self,
        verification_id: int,
        status: str,
        actual_value: Optional[str] = None,
        error_message: Optional[str] = None,
        check_details: Optional[Dict] = None,
        next_check_at: Optional[datetime] = None
    ) -> bool:
        """Update verification status and details"""
        
        update_fields = ["status = %s", "updated_at = NOW()"]
        update_values: List[Any] = [status]
        
        if actual_value is not None:
            update_fields.append("actual_value = %s")
            update_values.append(actual_value)
            
        if error_message is not None:
            update_fields.append("error_message = %s")
            update_values.append(error_message)
            
        if check_details is not None:
            update_fields.append("check_details = %s")
            update_values.append(json.dumps(check_details))
            
        if next_check_at is not None:
            update_fields.append("next_check_at = %s")
            update_values.append(next_check_at)
            
        # Handle completion/failure timestamps
        if status == VerificationStatus.COMPLETED.value:
            update_fields.append("completed_at = NOW()")
        elif status == VerificationStatus.IN_PROGRESS.value and "first_checked_at" not in update_fields:
            # Set first check time if not already set
            update_fields.append("first_checked_at = COALESCE(first_checked_at, NOW())")
            
        # Always update last check time for actual checks
        if status in [VerificationStatus.IN_PROGRESS.value, VerificationStatus.FAILED.value]:
            update_fields.append("last_checked_at = NOW()")
            
            # Only increment retry count on actual retries/failures, not on completion
            if status == VerificationStatus.IN_PROGRESS.value or status == VerificationStatus.FAILED.value:
                update_fields.append("retry_count = retry_count + 1")
        
        update_values.append(verification_id)
        
        result = await execute_update(f"""
            UPDATE domain_verifications 
            SET {', '.join(update_fields)}
            WHERE id = %s
        """, tuple(update_values))
        
        return result > 0
    
    async def check_dns_txt_verification(
        self,
        verification_id: int,
        domain_name: str,
        expected_token: str
    ) -> Dict[str, Any]:
        """
        Check DNS TXT record verification for domain ownership.
        Phase 1: Basic implementation
        """
        logger.info(f"🔍 VERIFICATION: Checking DNS TXT for domain {domain_name}")
        
        try:
            # Import here to avoid circular dependencies
            from services.domain_analysis_service import DomainAnalysisService
            
            analysis_service = DomainAnalysisService()
            verification_result = await analysis_service.validate_domain_ownership(
                domain_name, expected_token
            )
            
            if verification_result.get('success'):
                if verification_result.get('verified'):
                    # Verification successful
                    await self.update_verification_status(
                        verification_id,
                        VerificationStatus.COMPLETED.value,
                        actual_value=expected_token,
                        check_details=verification_result
                    )
                    
                    return {
                        'success': True,
                        'verified': True,
                        'message': 'Domain ownership verified successfully'
                    }
                else:
                    # Verification failed, schedule retry
                    next_check = datetime.now(timezone.utc) + self.default_check_interval
                    
                    await self.update_verification_status(
                        verification_id,
                        VerificationStatus.IN_PROGRESS.value,
                        error_message=verification_result.get('error', 'Verification token not found'),
                        check_details=verification_result,
                        next_check_at=next_check
                    )
                    
                    return {
                        'success': True,
                        'verified': False,
                        'error': verification_result.get('error'),
                        'next_check_at': next_check.isoformat()
                    }
            else:
                # DNS lookup failed
                await self.update_verification_status(
                    verification_id,
                    VerificationStatus.FAILED.value,
                    error_message=verification_result.get('error', 'DNS verification failed'),
                    check_details=verification_result
                )
                
                return {
                    'success': False,
                    'error': verification_result.get('error')
                }
                
        except Exception as e:
            logger.error(f"💥 VERIFICATION: DNS TXT check failed: {e}")
            
            await self.update_verification_status(
                verification_id,
                VerificationStatus.FAILED.value,
                error_message=str(e)
            )
            
            return {
                'success': False,
                'error': str(e)
            }
    
    async def check_nameserver_verification(
        self,
        verification_id: int,
        domain_name: str
    ) -> Dict[str, Any]:
        """
        Check if domain nameservers have been changed to HostBay nameservers.
        Phase 1: Basic implementation
        """
        logger.info(f"🔍 VERIFICATION: Checking nameservers for domain {domain_name}")
        
        try:
            # Import here to avoid circular dependencies
            from services.domain_analysis_service import DomainAnalysisService
            
            analysis_service = DomainAnalysisService()
            nameserver_result = await analysis_service.check_nameserver_changes(domain_name)
            
            if nameserver_result.get('success'):
                if nameserver_result.get('using_hostbay_nameservers'):
                    # Nameserver change verified
                    await self.update_verification_status(
                        verification_id,
                        VerificationStatus.COMPLETED.value,
                        actual_value=str(nameserver_result.get('current_nameservers')),
                        check_details=nameserver_result
                    )
                    
                    return {
                        'success': True,
                        'verified': True,
                        'message': 'Nameserver change verified successfully'
                    }
                else:
                    # Still waiting for nameserver change
                    next_check = datetime.now(timezone.utc) + self.default_check_interval
                    
                    await self.update_verification_status(
                        verification_id,
                        VerificationStatus.IN_PROGRESS.value,
                        actual_value=str(nameserver_result.get('current_nameservers')),
                        check_details=nameserver_result,
                        next_check_at=next_check
                    )
                    
                    return {
                        'success': True,
                        'verified': False,
                        'message': 'Waiting for nameserver propagation',
                        'current_nameservers': nameserver_result.get('current_nameservers'),
                        'next_check_at': next_check.isoformat()
                    }
            else:
                # DNS lookup failed
                await self.update_verification_status(
                    verification_id,
                    VerificationStatus.FAILED.value,
                    error_message=nameserver_result.get('error', 'Nameserver check failed'),
                    check_details=nameserver_result
                )
                
                return {
                    'success': False,
                    'error': nameserver_result.get('error')
                }
                
        except Exception as e:
            logger.error(f"💥 VERIFICATION: Nameserver check failed: {e}")
            
            await self.update_verification_status(
                verification_id,
                VerificationStatus.FAILED.value,
                error_message=str(e)
            )
            
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_pending_verifications(self) -> List[Dict[str, Any]]:
        """
        Get all pending verifications that need to be checked.
        Used by background verification scheduler.
        """
        verifications = await execute_query("""
            SELECT 
                id, domain_link_intent_id, verification_type, verification_step,
                expected_value, retry_count, next_check_at
            FROM domain_verifications 
            WHERE status IN (%s, %s)
            AND next_check_at <= NOW()
            AND retry_count < 50
            ORDER BY next_check_at ASC
            LIMIT 100
        """, (
            VerificationStatus.PENDING.value,
            VerificationStatus.IN_PROGRESS.value
        ))
        
        return verifications or []
    
    async def cleanup_expired_verifications(self) -> int:
        """Clean up expired verifications"""
        expired_time = datetime.now(timezone.utc) - self.max_verification_time
        
        result = await execute_update("""
            UPDATE domain_verifications 
            SET status = %s, updated_at = NOW()
            WHERE status IN (%s, %s)
            AND created_at < %s
        """, (
            VerificationStatus.EXPIRED.value,
            VerificationStatus.PENDING.value,
            VerificationStatus.IN_PROGRESS.value,
            expired_time
        ))
        
        if result > 0:
            logger.info(f"🧹 VERIFICATION: Cleaned up {result} expired verifications")
            
        return result