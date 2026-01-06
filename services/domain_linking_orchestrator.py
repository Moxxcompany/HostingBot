"""
Domain Linking Orchestrator - Phase 1 Foundation
Manages the workflow for linking existing domains to HostBay hosting services

This orchestrator handles:
- Smart mode: Automatic nameserver changes to HostBay nameservers
- Manual DNS mode: Providing instructions for manual DNS configuration
- Domain ownership verification
- DNS propagation monitoring
- Integration with existing hosting subscriptions
"""

import asyncio
import logging
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta, timezone
from enum import Enum

from database import execute_query, execute_update, run_in_transaction
from services.domain_analysis_service import DomainAnalysisService
from services.verification_service import VerificationService
from services.domain_linking_config import WORKFLOW_PROGRESS, get_workflow_progress

logger = logging.getLogger(__name__)


class LinkingMode(Enum):
    """Domain linking strategy modes"""
    SMART_MODE = "smart_mode"  # Automatic nameserver changes
    MANUAL_DNS = "manual_dns"  # Manual DNS record instructions
    

class WorkflowState(Enum):
    """Domain linking workflow states"""
    INITIATED = "initiated"
    ANALYZING_DOMAIN = "analyzing_domain"
    AWAITING_USER_CHOICE = "awaiting_user_choice"
    CONFIGURING_DNS = "configuring_dns"
    VERIFYING_NAMESERVERS = "verifying_nameservers"
    VERIFYING_OWNERSHIP = "verifying_ownership"
    PROVISIONING_HOSTING = "provisioning_hosting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DomainLinkingOrchestrator:
    """
    Orchestrates the complete domain linking workflow from analysis to completion.
    
    Features:
    - State persistence and recovery
    - Multiple linking strategies (smart/manual)
    - Real-time progress tracking
    - Integration with existing hosting systems
    """
    
    def __init__(self):
        self.domain_analysis = DomainAnalysisService()
        self.verification = VerificationService()
        self._verification_scheduler_running = False
        
    async def create_linking_intent(
        self,
        user_id: int,
        domain_name: str,
        hosting_subscription_id: Optional[int] = None,
        intent_type: str = LinkingMode.SMART_MODE.value
    ) -> Dict[str, Any]:
        """
        Create a new domain linking intent and begin the workflow.
        
        Args:
            user_id: Internal user ID
            domain_name: Domain to link (e.g., "example.com")
            hosting_subscription_id: Optional existing hosting subscription
            intent_type: Linking strategy (smart_mode or manual_dns)
            
        Returns:
            Dict with intent_id and initial workflow state
        """
        logger.info(f"🔗 DOMAIN LINKING: Creating intent for {domain_name} (user: {user_id})")
        
        try:
            # Create the intent record
            initial_progress = get_workflow_progress(WorkflowState.INITIATED.value)
            initial_config = {"step": "intent_created", "strategy": None}
            
            intent_data = await execute_query("""
                INSERT INTO domain_link_intents (
                    user_id, domain_name, hosting_subscription_id, intent_type,
                    workflow_state, current_step, progress_percentage,
                    configuration_data, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
                ) RETURNING id, workflow_state, created_at
            """, (
                user_id, domain_name, hosting_subscription_id, intent_type,
                WorkflowState.INITIATED.value, "intent_created", initial_progress,
                json.dumps(initial_config)
            ))
            
            if not intent_data:
                raise Exception("Failed to create domain linking intent")
                
            intent_id = intent_data[0]['id']
            logger.info(f"✅ DOMAIN LINKING: Intent created with ID {intent_id}")
            
            # Start the workflow asynchronously with error handling
            asyncio.create_task(self._execute_workflow_supervised(intent_id))
            
            return {
                'success': True,
                'intent_id': intent_id,
                'workflow_state': WorkflowState.INITIATED.value,
                'domain_name': domain_name,
                'intent_type': intent_type,
                'progress_percentage': initial_progress
            }
            
        except Exception as e:
            logger.error(f"💥 DOMAIN LINKING: Failed to create intent: {e}")
            return {
                'success': False,
                'error': str(e),
                'domain_name': domain_name
            }
    
    async def get_intent_status(self, intent_id: int) -> Optional[Dict[str, Any]]:
        """Get current status of a domain linking intent"""
        intent_data = await execute_query("""
            SELECT 
                id, user_id, domain_name, hosting_subscription_id,
                intent_type, workflow_state, current_step, progress_percentage,
                linking_strategy, current_nameservers, target_nameservers,
                dns_verification_status, ownership_verification_status,
                configuration_data, error_details, retry_count,
                last_verification_at, estimated_completion_at,
                completed_at, failed_at, created_at, updated_at
            FROM domain_link_intents 
            WHERE id = %s
        """, (intent_id,))
        
        if not intent_data:
            return None
            
        return intent_data[0]
    
    async def update_intent_state(
        self,
        intent_id: int,
        workflow_state: str,
        current_step: Optional[str] = None,
        progress_percentage: Optional[int] = None,
        configuration_data: Optional[Dict] = None,
        error_details: Optional[Dict] = None
    ) -> bool:
        """Update the state of a domain linking intent"""
        
        update_fields = ["workflow_state = %s", "updated_at = NOW()"]
        update_values: List[Any] = [workflow_state]
        
        if current_step:
            update_fields.append("current_step = %s")
            update_values.append(current_step)
            
        if progress_percentage is not None:
            update_fields.append("progress_percentage = %s")
            update_values.append(progress_percentage)
            
        if configuration_data:
            update_fields.append("configuration_data = %s")
            update_values.append(json.dumps(configuration_data))
            
        if error_details:
            update_fields.append("error_details = %s")
            update_values.append(json.dumps(error_details))
            
        # Handle completion timestamps
        if workflow_state == WorkflowState.COMPLETED.value:
            update_fields.append("completed_at = NOW()")
        elif workflow_state == WorkflowState.FAILED.value:
            update_fields.append("failed_at = NOW()")
            
        update_values.append(intent_id)
        
        result = await execute_update(f"""
            UPDATE domain_link_intents 
            SET {', '.join(update_fields)}
            WHERE id = %s
        """, tuple(update_values))
        
        return result > 0
    
    async def _execute_workflow_supervised(self, intent_id: int) -> None:
        """
        Supervised wrapper for workflow execution with error handling.
        Ensures exceptions are properly logged and handled.
        """
        try:
            await self._execute_workflow(intent_id)
        except Exception as e:
            logger.error(f"💥 DOMAIN LINKING: Unhandled exception in workflow {intent_id}: {e}")
            await self._handle_workflow_failure(intent_id, "workflow_exception", str(e))
    
    async def _execute_workflow(self, intent_id: int) -> None:
        """
        Execute the complete domain linking workflow.
        This runs asynchronously in the background.
        """
        logger.info(f"🔄 DOMAIN LINKING: Starting workflow for intent {intent_id}")
        
        try:
            # Get intent details
            intent = await self.get_intent_status(intent_id)
            if not intent:
                logger.error(f"💥 DOMAIN LINKING: Intent {intent_id} not found")
                return
                
            domain_name = intent['domain_name']
            user_id = intent['user_id']
            
            # Phase 1: Domain Analysis
            analysis_progress = get_workflow_progress(WorkflowState.ANALYZING_DOMAIN.value)
            await self.update_intent_state(
                intent_id, 
                WorkflowState.ANALYZING_DOMAIN.value,
                "analyzing_domain",
                analysis_progress
            )
            
            analysis_result = await self.domain_analysis.analyze_domain(domain_name)
            
            if not analysis_result.get('success'):
                await self._handle_workflow_failure(
                    intent_id, 
                    "domain_analysis_failed",
                    analysis_result.get('error', 'Domain analysis failed')
                )
                return
            
            # Phase 2: Strategy Selection and User Guidance
            strategy = await self._select_linking_strategy(intent_id, analysis_result)
            
            # Check if domain is already linked before executing strategy
            recommendation = analysis_result.get('recommendation', {})
            if recommendation.get('strategy') == 'already_linked':
                await self._handle_already_linked_domain(intent_id, analysis_result)
                return
            
            # Phase 3: Execute linking strategy
            if strategy == LinkingMode.SMART_MODE.value:
                await self._execute_smart_mode_linking(intent_id, analysis_result)
            elif strategy == LinkingMode.MANUAL_DNS.value:
                await self._execute_manual_dns_linking(intent_id, analysis_result)
            else:
                await self._handle_workflow_failure(
                    intent_id, 
                    "unknown_strategy",
                    f"Unknown linking strategy: {strategy}"
                )
                return
            
            logger.info(f"✅ DOMAIN LINKING: Workflow execution initiated for intent {intent_id} with strategy {strategy}")
            
        except Exception as e:
            logger.error(f"💥 DOMAIN LINKING: Workflow failed for intent {intent_id}: {e}")
            await self._handle_workflow_failure(intent_id, "workflow_exception", str(e))
    
    async def _select_linking_strategy(
        self, 
        intent_id: int, 
        analysis_result: Dict[str, Any]
    ) -> str:
        """
        Select the optimal linking strategy based on domain analysis.
        Enhanced Phase 2 implementation with intelligent strategy selection.
        """
        try:
            dns_info = analysis_result.get('dns_info', {})
            recommendation = analysis_result.get('recommendation', {})
            
            # Check if already using HostBay nameservers
            if recommendation.get('strategy') == 'already_linked':
                return LinkingMode.SMART_MODE.value  # Will be handled as already linked in execution
            
            # Check for Cloudflare proxy (requires manual DNS)
            if dns_info.get('cloudflare_proxy', False):
                logger.info(f"🔧 DOMAIN LINKING: Cloudflare proxy detected for intent {intent_id}, selecting manual DNS mode")
                return LinkingMode.MANUAL_DNS.value
            
            # Check for complex DNS setup (many MX records, subdomains, etc.)
            mx_records = dns_info.get('mx_records', [])
            if len(mx_records) > 2:
                logger.info(f"🔧 DOMAIN LINKING: Complex email setup detected for intent {intent_id}, recommending manual DNS mode")
                return LinkingMode.MANUAL_DNS.value
            
            # Check for specific nameserver providers that require special handling
            nameservers = dns_info.get('nameservers', [])
            if any('cloudns' in ns.lower() or 'route53' in ns.lower() for ns in nameservers):
                logger.info(f"🔧 DOMAIN LINKING: Specialized DNS provider detected for intent {intent_id}, selecting manual DNS mode")
                return LinkingMode.MANUAL_DNS.value
            
            # Default to smart mode for standard setups
            logger.info(f"🚀 DOMAIN LINKING: Standard setup detected for intent {intent_id}, selecting smart mode")
            return LinkingMode.SMART_MODE.value
            
        except Exception as e:
            logger.warning(f"⚠️ DOMAIN LINKING: Strategy selection failed for intent {intent_id}: {e}, defaulting to smart mode")
            return LinkingMode.SMART_MODE.value
    
    async def _handle_workflow_failure(
        self,
        intent_id: int,
        failure_reason: str,
        error_message: str,
        recovery_action: Optional[str] = None
    ) -> None:
        """Handle workflow failures with comprehensive error reporting and recovery options"""
        logger.error(f"💥 DOMAIN LINKING: Workflow failed for intent {intent_id}: {failure_reason} - {error_message}")
        
        try:
            # Get intent details for context
            intent_details = await self.get_intent_status(intent_id)
            if not intent_details:
                logger.error(f"💥 DOMAIN LINKING: Cannot handle failure - intent {intent_id} not found")
                return
            
            # Determine recovery strategy based on failure type
            recovery_strategies = self._determine_recovery_strategies(failure_reason, error_message)
            
            # Update intent state to failed with recovery information
            failure_data = {
                'error': error_message,
                'failure_reason': failure_reason,
                'recovery_action': recovery_action,
                'recovery_strategies': recovery_strategies,
                'failed_at': datetime.now(timezone.utc).isoformat(),
                'retry_count': intent_details.get('retry_count', 0) + 1,
                'user_guidance': {
                    'step': 'Workflow failed',
                    'description': f'Domain linking encountered an error: {self._get_user_friendly_error(failure_reason)}',
                    'next_actions': recovery_strategies.get('user_actions', [])
                }
            }
            
            await self.update_intent_state(
                intent_id,
                WorkflowState.FAILED.value,
                failure_reason,
                0,  # 0% progress for failed state
                error_details=failure_data
            )
            
            # Update retry count in the database
            await execute_update("""
                UPDATE domain_link_intents 
                SET retry_count = %s
                WHERE id = %s
            """, (failure_data['retry_count'], intent_id))
            
            # Send failure notification to user
            await self._notify_user_workflow_progress(
                intent_id,
                intent_details['user_id'],
                "workflow_failed",
                additional_data={'error': self._get_user_friendly_error(failure_reason)}
            )
            
            logger.info(f"✅ DOMAIN LINKING: Failure handling completed for intent {intent_id}")
            
        except Exception as e:
            logger.error(f"💥 DOMAIN LINKING: Failed to handle workflow failure for intent {intent_id}: {e}")
    
    def _determine_recovery_strategies(self, failure_reason: str, error_message: str) -> Dict[str, Any]:
        """Determine available recovery strategies based on failure type"""
        strategies = {
            'auto_retry': False,
            'user_actions': [],
            'admin_intervention': False,
            'alternative_workflow': None
        }
        
        if failure_reason in ['dns_lookup_failed', 'nameserver_timeout', 'dns_verification_timeout']:
            strategies.update({
                'auto_retry': True,
                'user_actions': [
                    'Check that DNS changes have been saved and propagated',
                    'Wait 15-30 minutes for DNS propagation',
                    'Verify domain DNS settings with your provider'
                ]
            })
            
        elif failure_reason in ['invalid_domain', 'domain_not_found']:
            strategies.update({
                'user_actions': [
                    'Verify the domain name is spelled correctly',
                    'Ensure the domain is registered and active',
                    'Check domain status with your registrar'
                ]
            })
            
        elif failure_reason in ['verification_creation_failed', 'analysis_failed', 'domain_analysis_failed']:
            strategies.update({
                'auto_retry': True,
                'admin_intervention': True
            })
            
        elif failure_reason in ['nameserver_verification_failed', 'dns_verification_failed']:
            strategies.update({
                'user_actions': [
                    'Double-check nameserver or DNS record configuration',
                    'Ensure changes are saved in your DNS provider',
                    'Try alternative DNS configuration method'
                ],
                'alternative_workflow': 'suggest_manual_dns' if 'nameserver' in failure_reason else 'suggest_smart_mode'
            })
            
        elif failure_reason in ['smart_mode_failed', 'workflow_exception']:
            strategies.update({
                'auto_retry': True,
                'admin_intervention': True,
                'user_actions': [
                    'Please try again in a few minutes',
                    'If the problem persists, contact support'
                ]
            })
            
        return strategies
    
    def _get_user_friendly_error(self, failure_reason: str) -> str:
        """Convert technical failure reasons to user-friendly messages"""
        error_messages = {
            'dns_lookup_failed': 'DNS lookup failed. Please check your internet connection and domain settings.',
            'nameserver_timeout': 'Nameserver changes are taking longer than expected. DNS propagation can take up to 24 hours.',
            'dns_verification_timeout': 'DNS record verification timed out. Please ensure records are correctly configured.',
            'invalid_domain': 'The domain name appears to be invalid or not properly formatted.',
            'domain_not_found': 'Domain not found. Please verify the domain exists and is properly registered.',
            'verification_creation_failed': 'System error occurred while setting up verification. Please try again.',
            'analysis_failed': 'Domain analysis failed. This may be a temporary issue.',
            'domain_analysis_failed': 'Domain analysis failed. This may be a temporary issue.',
            'nameserver_verification_failed': 'Nameserver verification failed. Please check your nameserver configuration.',
            'dns_verification_failed': 'DNS record verification failed. Please verify your DNS settings.',
            'finalization_failed': 'Domain linking setup failed during final configuration.',
            'smart_mode_failed': 'Smart mode configuration failed. Please try manual DNS configuration instead.',
            'workflow_exception': 'An unexpected error occurred during domain linking. Please try again.'
        }
        
        return error_messages.get(failure_reason, f'An unexpected error occurred: {failure_reason}')
    
    async def resume_intent(self, intent_id: int) -> Dict[str, Any]:
        """
        Resume a domain linking intent from its current state.
        Useful for recovery and user-initiated retries.
        """
        intent = await self.get_intent_status(intent_id)
        if not intent:
            return {'success': False, 'error': 'Intent not found'}
            
        current_state = intent['workflow_state']
        
        if current_state in [WorkflowState.COMPLETED.value, WorkflowState.CANCELLED.value]:
            return {
                'success': False, 
                'error': f'Intent is already {current_state}',
                'current_state': current_state
            }
        
        logger.info(f"🔄 DOMAIN LINKING: Resuming intent {intent_id} from state {current_state}")
        
        # Restart the workflow from current state
        asyncio.create_task(self._execute_workflow(intent_id))
        
        return {
            'success': True,
            'intent_id': intent_id,
            'resumed_from_state': current_state,
            'message': 'Domain linking workflow resumed'
        }
    
    async def cancel_intent(self, intent_id: int, reason: str = "user_cancelled") -> Dict[str, Any]:
        """Cancel a domain linking intent"""
        success = await self.update_intent_state(
            intent_id,
            WorkflowState.CANCELLED.value,
            f"cancelled_{reason}",
            0,
            configuration_data={'cancellation_reason': reason}
        )
        
        if success:
            logger.info(f"✅ DOMAIN LINKING: Intent {intent_id} cancelled ({reason})")
            return {'success': True, 'message': 'Domain linking cancelled'}
        else:
            return {'success': False, 'error': 'Failed to cancel intent'}
    
    async def get_user_active_intents(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all active domain linking intents for a user"""
        intents = await execute_query("""
            SELECT 
                id, domain_name, intent_type, workflow_state, 
                current_step, progress_percentage, created_at
            FROM domain_link_intents 
            WHERE user_id = %s 
            AND workflow_state NOT IN (%s, %s, %s)
            ORDER BY created_at DESC
        """, (
            user_id, 
            WorkflowState.COMPLETED.value,
            WorkflowState.FAILED.value, 
            WorkflowState.CANCELLED.value
        ))
        
        return intents or []
    
    async def _execute_smart_mode_linking(
        self, 
        intent_id: int, 
        analysis_result: Dict[str, Any]
    ) -> None:
        """
        Execute smart mode linking workflow with automated nameserver changes.
        Provides step-by-step user guidance throughout the process.
        """
        logger.info(f"🚀 DOMAIN LINKING: Starting smart mode workflow for intent {intent_id}")
        
        try:
            intent = await self.get_intent_status(intent_id)
            if not intent:
                raise Exception("Intent not found")
                
            domain_name = intent['domain_name']
            user_id = intent['user_id']
            
            # Check if domain already uses HostBay nameservers
            recommendation = analysis_result.get('recommendation', {})
            if recommendation.get('strategy') == 'already_linked':
                await self._handle_already_linked_domain(intent_id, analysis_result)
                return
            
            # Step 1: Generate nameserver change instructions
            await self.update_intent_state(
                intent_id,
                WorkflowState.AWAITING_USER_CHOICE.value,
                "nameserver_instructions_ready",
                get_workflow_progress(WorkflowState.AWAITING_USER_CHOICE.value),
                {
                    'analysis': analysis_result,
                    'linking_strategy': LinkingMode.SMART_MODE.value,
                    'instructions': await self._generate_nameserver_instructions(domain_name),
                    'next_action': 'awaiting_nameserver_change',
                    'user_guidance': {
                        'step': 'Change your domain nameservers',
                        'description': 'Update your domain nameservers to point to HostBay',
                        'estimated_time': '5-15 minutes'
                    }
                }
            )
            
            # Update linking_strategy column for data consistency
            await execute_update("""
                UPDATE domain_link_intents 
                SET linking_strategy = %s
                WHERE id = %s
            """, (LinkingMode.SMART_MODE.value, intent_id))
            
            # Send user notification about instructions being ready
            await self._notify_user_workflow_progress(intent_id, user_id, "nameserver_instructions")
            
            # Step 2: Create nameserver verification task
            verification_result = await self.verification.create_verification(
                intent_id,
                "nameserver_change",
                "awaiting_nameserver_change",
                verification_method="dns_lookup"
            )
            
            if not verification_result.get('success'):
                await self._handle_workflow_failure(
                    intent_id,
                    "verification_creation_failed",
                    verification_result.get('error', 'Failed to create verification')
                )
                return
            
            verification_id = verification_result['verification_id']
            
            # Step 3: Start nameserver monitoring
            await self.update_intent_state(
                intent_id,
                WorkflowState.VERIFYING_NAMESERVERS.value,
                "monitoring_nameserver_change",
                get_workflow_progress(WorkflowState.VERIFYING_NAMESERVERS.value),
                {
                    'verification_id': verification_id,
                    'monitoring_started': datetime.now(timezone.utc).isoformat(),
                    'user_guidance': {
                        'step': 'Monitoring nameserver changes',
                        'description': 'We are automatically checking for nameserver updates',
                        'estimated_time': '5-30 minutes for DNS propagation'
                    }
                }
            )
            
            # Schedule periodic nameserver checks
            await self._schedule_nameserver_monitoring(intent_id, verification_id, domain_name)
            
            logger.info(f"✅ DOMAIN LINKING: Smart mode monitoring initiated for intent {intent_id}")
            
        except Exception as e:
            logger.error(f"💥 DOMAIN LINKING: Smart mode workflow failed for intent {intent_id}: {e}")
            await self._handle_workflow_failure(intent_id, "smart_mode_failed", str(e))
    
    async def _execute_manual_dns_linking(
        self, 
        intent_id: int, 
        analysis_result: Dict[str, Any]
    ) -> None:
        """
        Execute manual DNS linking workflow with step-by-step instructions.
        Used when smart mode is not suitable (e.g., Cloudflare proxy).
        """
        logger.info(f"🔧 DOMAIN LINKING: Starting manual DNS workflow for intent {intent_id}")
        
        try:
            intent = await self.get_intent_status(intent_id)
            if not intent:
                raise Exception("Intent not found")
                
            domain_name = intent['domain_name']
            user_id = intent['user_id']
            
            # Step 1: Generate DNS record instructions
            dns_instructions = await self._generate_manual_dns_instructions(domain_name)
            
            await self.update_intent_state(
                intent_id,
                WorkflowState.AWAITING_USER_CHOICE.value,
                "dns_instructions_ready",
                get_workflow_progress(WorkflowState.AWAITING_USER_CHOICE.value),
                {
                    'analysis': analysis_result,
                    'linking_strategy': LinkingMode.MANUAL_DNS.value,
                    'dns_instructions': dns_instructions,
                    'next_action': 'awaiting_dns_configuration',
                    'user_guidance': {
                        'step': 'Configure DNS records manually',
                        'description': 'Add the required DNS records to your domain',
                        'estimated_time': '10-20 minutes'
                    }
                }
            )
            
            # Send user notification about instructions being ready
            await self._notify_user_workflow_progress(intent_id, user_id, "dns_instructions")
            
            # Step 2: Create DNS verification task
            verification_result = await self.verification.create_verification(
                intent_id,
                "dns_txt",
                "awaiting_dns_records",
                expected_value=dns_instructions.get('verification_token'),
                verification_method="dns_txt_lookup"
            )
            
            if not verification_result.get('success'):
                await self._handle_workflow_failure(
                    intent_id,
                    "verification_creation_failed",
                    verification_result.get('error', 'Failed to create verification')
                )
                return
            
            # Step 3: Start DNS monitoring
            verification_id = verification_result['verification_id']
            await self.update_intent_state(
                intent_id,
                WorkflowState.VERIFYING_OWNERSHIP.value,
                "monitoring_dns_records",
                get_workflow_progress(WorkflowState.VERIFYING_OWNERSHIP.value),
                {
                    'verification_id': verification_id,
                    'monitoring_started': datetime.now(timezone.utc).isoformat(),
                    'user_guidance': {
                        'step': 'Monitoring DNS records',
                        'description': 'We are checking for the required DNS records',
                        'estimated_time': '5-30 minutes for DNS propagation'
                    }
                }
            )
            
            # Update linking_strategy column for data consistency
            await execute_update("""
                UPDATE domain_link_intents 
                SET linking_strategy = %s
                WHERE id = %s
            """, (LinkingMode.MANUAL_DNS.value, intent_id))
            
            # Schedule periodic DNS verification monitoring
            verification_token = dns_instructions.get('verification_token', '')
            if verification_token:
                await self._schedule_dns_monitoring(intent_id, verification_id, domain_name, verification_token)
            else:
                logger.error(f"💥 DOMAIN LINKING: No verification token for DNS monitoring intent {intent_id}")
            
            logger.info(f"✅ DOMAIN LINKING: Manual DNS monitoring initiated for intent {intent_id}")
            
        except Exception as e:
            logger.error(f"💥 DOMAIN LINKING: Manual DNS workflow failed for intent {intent_id}: {e}")
            await self._handle_workflow_failure(intent_id, "manual_dns_failed", str(e))
    
    async def _handle_already_linked_domain(
        self, 
        intent_id: int, 
        analysis_result: Dict[str, Any]
    ) -> None:
        """Handle domains that are already using HostBay nameservers"""
        logger.info(f"✅ DOMAIN LINKING: Domain already linked for intent {intent_id}")
        
        await self.update_intent_state(
            intent_id,
            WorkflowState.COMPLETED.value,
            "already_linked",
            100,
            {
                'analysis': analysis_result,
                'linking_strategy': 'already_linked',
                'completion_reason': 'domain_already_uses_hostbay_nameservers',
                'user_guidance': {
                    'step': 'Domain linking complete',
                    'description': 'Your domain is already configured with HostBay',
                    'message': 'No additional configuration needed'
                }
            }
        )
        
        intent = await self.get_intent_status(intent_id)
        if intent:
            await self._notify_user_workflow_progress(intent_id, intent['user_id'], "already_linked")
    
    async def _generate_nameserver_instructions(self, domain_name: str) -> Dict[str, Any]:
        """Generate nameserver change instructions for smart mode"""
        from services.domain_linking_config import HOSTBAY_NAMESERVERS
        
        return {
            'type': 'nameserver_change',
            'domain_name': domain_name,
            'target_nameservers': HOSTBAY_NAMESERVERS,
            'instructions': [
                f"1. Log into your domain registrar's control panel",
                f"2. Find the nameserver settings for {domain_name}",
                f"3. Replace the current nameservers with:",
                *[f"   • {ns}" for ns in HOSTBAY_NAMESERVERS],
                f"4. Save the changes",
                f"5. DNS propagation can take 5-30 minutes"
            ],
            'warnings': [
                "Changing nameservers will affect all DNS records for this domain",
                "Email services may be temporarily interrupted during propagation"
            ],
            'estimated_propagation_time': '5-30 minutes'
        }
    
    async def _generate_manual_dns_instructions(self, domain_name: str) -> Dict[str, Any]:
        """Generate manual DNS configuration instructions"""
        import secrets
        
        verification_token = f"hostbay-verify-{secrets.token_hex(16)}"
        
        return {
            'type': 'manual_dns',
            'domain_name': domain_name,
            'verification_token': verification_token,
            'dns_records': [
                {
                    'type': 'TXT',
                    'name': f'_hostbay-verify.{domain_name}',
                    'value': verification_token,
                    'ttl': 300
                },
                {
                    'type': 'A',
                    'name': f'{domain_name}',
                    'value': '193.143.1.147',  # HostBay hosting server IP
                    'ttl': 300
                }
            ],
            'instructions': [
                f"1. Log into your DNS provider's control panel",
                f"2. Add the following DNS records:",
                f"   • TXT record: _hostbay-verify.{domain_name} → {verification_token}",
                f"   • A record: {domain_name} → 192.168.1.100",
                f"3. Save the changes",
                f"4. DNS propagation can take 5-30 minutes"
            ],
            'verification_method': 'dns_txt',
            'estimated_propagation_time': '5-30 minutes'
        }
    
    async def _schedule_nameserver_monitoring(
        self, 
        intent_id: int, 
        verification_id: int, 
        domain_name: str
    ) -> None:
        """Schedule periodic nameserver monitoring"""
        # Create background task for periodic verification
        async def monitor_nameservers():
            max_attempts = 60  # Monitor for up to 5 hours (5 minute intervals)
            attempt = 0
            
            while attempt < max_attempts:
                try:
                    # Check if intent is still active
                    intent = await self.get_intent_status(intent_id)
                    if not intent or intent['workflow_state'] not in [
                        WorkflowState.VERIFYING_NAMESERVERS.value,
                        WorkflowState.AWAITING_USER_CHOICE.value
                    ]:
                        logger.info(f"🛑 DOMAIN LINKING: Stopping nameserver monitoring for intent {intent_id} (state changed)")
                        break
                    
                    # Perform nameserver check
                    verification_result = await self.verification.check_nameserver_verification(
                        verification_id, domain_name
                    )
                    
                    if verification_result.get('verified'):
                        # Success! Proceed to final configuration
                        await self._finalize_domain_linking(intent_id)
                        break
                    elif not verification_result.get('success'):
                        # Failed verification
                        await self._handle_workflow_failure(
                            intent_id,
                            "nameserver_verification_failed",
                            verification_result.get('error', 'Nameserver verification failed')
                        )
                        break
                    
                    # Wait before next check
                    await asyncio.sleep(300)  # 5 minutes
                    attempt += 1
                    
                except Exception as e:
                    logger.error(f"💥 DOMAIN LINKING: Nameserver monitoring error for intent {intent_id}: {e}")
                    await asyncio.sleep(300)  # Continue trying despite errors
                    attempt += 1
            
            if attempt >= max_attempts:
                await self._handle_workflow_failure(
                    intent_id,
                    "nameserver_timeout",
                    "Nameserver change was not detected within the expected timeframe"
                )
        
        # Start monitoring as background task
        asyncio.create_task(monitor_nameservers())
        logger.info(f"🔄 DOMAIN LINKING: Nameserver monitoring scheduled for intent {intent_id}")
    
    async def _schedule_dns_monitoring(
        self, 
        intent_id: int, 
        verification_id: int, 
        domain_name: str,
        verification_token: str
    ) -> None:
        """Schedule periodic DNS TXT record monitoring"""
        # Create background task for periodic DNS verification
        async def monitor_dns_records():
            max_attempts = 120  # Monitor for up to 10 hours (5 minute intervals)
            attempt = 0
            
            while attempt < max_attempts:
                try:
                    # Check if intent is still active
                    intent = await self.get_intent_status(intent_id)
                    if not intent or intent['workflow_state'] not in [
                        WorkflowState.VERIFYING_OWNERSHIP.value,
                        WorkflowState.AWAITING_USER_CHOICE.value
                    ]:
                        logger.info(f"🛑 DOMAIN LINKING: Stopping DNS monitoring for intent {intent_id} (state changed)")
                        break
                    
                    # Perform DNS TXT verification check
                    verification_result = await self.verification.check_dns_txt_verification(
                        verification_id, domain_name, verification_token
                    )
                    
                    if verification_result.get('verified'):
                        # Success! Proceed to final configuration
                        await self._finalize_domain_linking(intent_id)
                        break
                    elif not verification_result.get('success'):
                        # Failed verification
                        await self._handle_workflow_failure(
                            intent_id,
                            "dns_verification_failed",
                            verification_result.get('error', 'DNS TXT verification failed')
                        )
                        break
                    
                    # Wait before next check
                    await asyncio.sleep(300)  # 5 minutes
                    attempt += 1
                    
                except Exception as e:
                    logger.error(f"💥 DOMAIN LINKING: DNS monitoring error for intent {intent_id}: {e}")
                    await asyncio.sleep(300)  # Continue trying despite errors
                    attempt += 1
            
            if attempt >= max_attempts:
                await self._handle_workflow_failure(
                    intent_id,
                    "dns_verification_timeout",
                    "DNS TXT record was not detected within the expected timeframe"
                )
        
        # Start monitoring as background task
        asyncio.create_task(monitor_dns_records())
        logger.info(f"🔄 DOMAIN LINKING: DNS TXT monitoring scheduled for intent {intent_id}")
    
    async def _finalize_domain_linking(self, intent_id: int) -> None:
        """Finalize the domain linking process"""
        logger.info(f"🏁 DOMAIN LINKING: Finalizing linking for intent {intent_id}")
        
        try:
            intent = await self.get_intent_status(intent_id)
            if not intent:
                raise Exception("Intent not found")
            
            # Update to provisioning state
            await self.update_intent_state(
                intent_id,
                WorkflowState.PROVISIONING_HOSTING.value,
                "finalizing_configuration",
                get_workflow_progress(WorkflowState.PROVISIONING_HOSTING.value),
                {
                    'user_guidance': {
                        'step': 'Finalizing hosting configuration',
                        'description': 'Setting up your domain with HostBay hosting',
                        'estimated_time': '2-5 minutes'
                    }
                }
            )
            
            # Simulate hosting configuration (Phase 1: basic completion)
            await asyncio.sleep(2)  # Simulate configuration time
            
            # Mark as completed
            await self.update_intent_state(
                intent_id,
                WorkflowState.COMPLETED.value,
                "linking_completed",
                100,
                {
                    'completion_timestamp': datetime.now(timezone.utc).isoformat(),
                    'user_guidance': {
                        'step': 'Domain linking complete',
                        'description': 'Your domain is now linked to HostBay hosting',
                        'message': 'Your domain is ready to use!'
                    }
                }
            )
            
            # Send completion notification
            await self._notify_user_workflow_progress(intent_id, intent['user_id'], "linking_completed")
            
            logger.info(f"✅ DOMAIN LINKING: Successfully completed intent {intent_id}")
            
        except Exception as e:
            logger.error(f"💥 DOMAIN LINKING: Finalization failed for intent {intent_id}: {e}")
            await self._handle_workflow_failure(intent_id, "finalization_failed", str(e))
    
    async def _notify_user_workflow_progress(
        self,
        intent_id: int,
        user_id: int,
        message_type: str,
        additional_data: Optional[Dict] = None
    ) -> bool:
        """
        Send user notification about domain linking workflow progress with deduplication protection.
        
        Args:
            intent_id: Domain linking intent ID
            user_id: Telegram user ID
            message_type: Type of notification (nameserver_instructions, dns_instructions, completed, failed, etc.)
            additional_data: Additional context data for the notification
            
        Returns:
            bool: True if notification was sent successfully, False if skipped or failed
        """
        logger.debug(f"📧 DOMAIN LINKING: Sending {message_type} notification for intent {intent_id} to user {user_id}")
        
        try:
            # Step 1: Check for deduplication using domain_notifications table
            notification_key = f"domain_linking_{intent_id}"
            existing_notifications = await execute_query("""
                SELECT id, sent_at FROM domain_notifications 
                WHERE order_id = %s AND message_type = %s
            """, (notification_key, message_type))
            
            if existing_notifications:
                logger.warning(f"🚫 DOMAIN LINKING: {message_type} notification already sent for intent {intent_id}")
                return False
            
            # Step 2: Get intent details for context
            intent_details = await self.get_intent_status(intent_id)
            if not intent_details:
                logger.error(f"💥 DOMAIN LINKING: Cannot send notification - intent {intent_id} not found")
                return False
            
            domain_name = intent_details['domain_name']
            configuration_data = json.loads(intent_details.get('configuration_data') or '{}')
            
            # Step 3: Generate notification message based on type
            message = await self._generate_notification_message(
                message_type=message_type,
                domain_name=domain_name,
                user_id=user_id,
                configuration_data=configuration_data,
                additional_data=additional_data or {}
            )
            
            if not message:
                logger.error(f"💥 DOMAIN LINKING: Failed to generate {message_type} message for intent {intent_id}")
                return False
            
            # Step 4: Record notification in ledger for deduplication
            try:
                await execute_update("""
                    INSERT INTO domain_notifications (order_id, user_id, domain_name, message_type, sent_at)
                    VALUES (%s, %s, %s, %s, %s)
                """, (notification_key, user_id, domain_name, message_type, datetime.now(timezone.utc)))
                
                logger.info(f"✅ DOMAIN LINKING: Recorded {message_type} notification for intent {intent_id}")
                
            except Exception as ledger_error:
                logger.error(f"⚠️ DOMAIN LINKING: Failed to record notification ledger for intent {intent_id}: {ledger_error}")
                # Continue with sending even if ledger fails
            
            # Step 5: Send the actual notification to user
            success = await self._send_telegram_message(user_id, message)
            
            if success:
                logger.info(f"📧 DOMAIN LINKING: {message_type} notification sent successfully to user {user_id}")
                return True
            else:
                logger.error(f"💥 DOMAIN LINKING: Failed to send {message_type} notification to user {user_id}")
                return False
                
        except Exception as e:
            logger.error(f"💥 DOMAIN LINKING: Notification system error for intent {intent_id}: {e}")
            return False
    
    async def _generate_notification_message(
        self,
        message_type: str,
        domain_name: str,
        user_id: int,
        configuration_data: Dict,
        additional_data: Dict
    ) -> Optional[str]:
        """Generate notification message with graceful fallback for missing localization"""
        try:
            # Fallback messages in case localization fails
            fallback_messages = {
                "nameserver_instructions": f"🔧 Nameserver Update Required\n\nPlease update your nameservers for {domain_name}. We'll automatically detect the changes once they propagate.",
                "dns_instructions": f"📝 DNS Records Required\n\nPlease add the required DNS records for {domain_name}. Check your account dashboard for detailed instructions.",
                "linking_completed": f"✅ Domain Linked Successfully!\n\nYour domain {domain_name} has been successfully linked to your hosting package. It should be accessible within a few minutes.",
                "already_linked": f"ℹ️ Domain Already Configured\n\nYour domain {domain_name} is already properly configured and linked to your hosting package.",
                "workflow_failed": f"❌ Domain Linking Failed\n\nWe encountered an issue linking {domain_name}: {additional_data.get('error', 'Unknown error')}. Please check the instructions and try again.",
                "verification_timeout": f"⏰ Verification Timeout\n\nDNS verification for {domain_name} timed out. Please ensure your DNS changes are saved and try again in a few minutes."
            }
            
            # Try localized message generation first
            try:
                from message_utils import create_success_message_localized, create_error_message_localized, create_info_message_localized
                
                lang_code = 'en'  # Default, can be enhanced with user language resolution
                
                if message_type == "nameserver_instructions":
                    instructions = configuration_data.get('instructions', {})
                    nameservers = ', '.join(instructions.get('target_nameservers', []))
                    
                    return create_info_message_localized(
                        'domain_linking.nameserver_instructions.title',
                        lang_code,
                        'domain_linking.nameserver_instructions.details',
                        domain=domain_name,
                        nameservers=nameservers
                    )
                    
                elif message_type == "dns_instructions":
                    dns_records = configuration_data.get('analysis', {}).get('dns_records', [])
                    record_count = len(dns_records)
                    
                    return create_info_message_localized(
                        'domain_linking.dns_instructions.title',
                        lang_code,
                        'domain_linking.dns_instructions.details',
                        domain=domain_name,
                        record_count=record_count
                    )
                    
                elif message_type == "linking_completed":
                    return create_success_message_localized(
                        'domain_linking.completed.title',
                        lang_code,
                        'domain_linking.completed.details',
                        domain=domain_name
                    )
                    
                elif message_type == "already_linked":
                    return create_info_message_localized(
                        'domain_linking.already_linked.title',
                        lang_code,
                        'domain_linking.already_linked.details',
                        domain=domain_name
                    )
                    
                elif message_type == "workflow_failed":
                    error_details = additional_data.get('error', 'Unknown error occurred')
                    return create_error_message_localized(
                        'domain_linking.failed.title',
                        lang_code,
                        'domain_linking.failed.details',
                        domain=domain_name,
                        error=error_details
                    )
                    
                elif message_type == "verification_timeout":
                    return create_error_message_localized(
                        'domain_linking.timeout.title',
                        lang_code,
                        'domain_linking.timeout.details',
                        domain=domain_name
                    )
                
            except Exception as loc_error:
                logger.warning(f"⚠️ DOMAIN LINKING: Localization failed for {message_type}: {loc_error}, using fallback")
            
            # Use fallback message if localization fails or message type not found
            if message_type in fallback_messages:
                return fallback_messages[message_type]
            else:
                logger.warning(f"⚠️ DOMAIN LINKING: Unknown message type: {message_type}")
                return f"ℹ️ Domain Linking Update\n\nUpdate for domain {domain_name}: {message_type}"
                
        except Exception as e:
            logger.error(f"💥 DOMAIN LINKING: Failed to generate {message_type} message: {e}")
            # Last resort fallback
            return f"ℹ️ Domain Linking Notification\n\nDomain: {domain_name}\nStatus: {message_type}"
    
    async def _send_telegram_message(self, user_id: int, message: str) -> bool:
        """Send message to Telegram user"""
        try:
            # This would integrate with the callback router or message sending system
            # For now, log the message that would be sent
            logger.info(f"📤 DOMAIN LINKING: Sending message to user {user_id}: {message[:100]}...")
            
            # TODO: Integrate with actual Telegram message sending
            # from callback_router import send_message_to_user
            # return await send_message_to_user(user_id, message)
            
            return True
            
        except Exception as e:
            logger.error(f"💥 DOMAIN LINKING: Failed to send Telegram message to user {user_id}: {e}")
            return False
    
    async def get_user_workflow_status(self, user_id: int, intent_id: int) -> Dict[str, Any]:
        """
        Get detailed workflow status for user interface display.
        Provides user-friendly status information and next steps.
        """
        try:
            intent = await self.get_intent_status(intent_id)
            if not intent or intent['user_id'] != user_id:
                return {
                    'success': False,
                    'error': 'Domain linking workflow not found'
                }
            
            workflow_state = intent['workflow_state']
            configuration_data = intent.get('configuration_data') or {}
            if isinstance(configuration_data, str):
                configuration_data = json.loads(configuration_data)
            user_guidance = configuration_data.get('user_guidance', {})
            
            # Base status information
            status_info = {
                'success': True,
                'intent_id': intent_id,
                'domain_name': intent['domain_name'],
                'workflow_state': workflow_state,
                'current_step': intent['current_step'],
                'progress_percentage': intent['progress_percentage'],
                'created_at': intent['created_at'],
                'updated_at': intent['updated_at']
            }
            
            # Add user guidance information
            if user_guidance:
                status_info.update({
                    'current_step_name': user_guidance.get('step', 'Processing'),
                    'step_description': user_guidance.get('description', ''),
                    'estimated_time': user_guidance.get('estimated_time', 'Unknown'),
                    'user_message': user_guidance.get('message', '')
                })
            
            # Add state-specific information
            if workflow_state == WorkflowState.AWAITING_USER_CHOICE.value:
                status_info.update(await self._get_user_choice_options(intent, configuration_data))
            elif workflow_state == WorkflowState.VERIFYING_NAMESERVERS.value:
                status_info.update(await self._get_nameserver_verification_status(intent, configuration_data))
            elif workflow_state == WorkflowState.VERIFYING_OWNERSHIP.value:
                status_info.update(await self._get_ownership_verification_status(intent, configuration_data))
            elif workflow_state == WorkflowState.COMPLETED.value:
                status_info['completion_details'] = configuration_data.get('completion_reason', 'Successfully linked')
            elif workflow_state == WorkflowState.FAILED.value:
                error_details = json.loads(intent.get('error_details') or '{}')
                status_info.update({
                    'failure_reason': error_details.get('failure_reason', 'Unknown error'),
                    'error_message': error_details.get('error_message', 'An error occurred'),
                    'retry_available': True
                })
            
            return status_info
            
        except Exception as e:
            logger.error(f"💥 DOMAIN LINKING: Failed to get workflow status for intent {intent_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _get_user_choice_options(
        self, 
        intent: Dict[str, Any], 
        configuration_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get user choice options for awaiting choice state"""
        linking_strategy = configuration_data.get('linking_strategy')
        
        if linking_strategy == LinkingMode.SMART_MODE.value:
            instructions = configuration_data.get('instructions', {})
            return {
                'action_required': 'nameserver_change',
                'instructions_type': 'nameserver_change',
                'nameserver_instructions': instructions.get('instructions', []),
                'target_nameservers': instructions.get('target_nameservers', []),
                'warnings': instructions.get('warnings', []),
                'estimated_time': instructions.get('estimated_propagation_time', '5-30 minutes'),
                'next_step': 'Change your domain nameservers as instructed, then we\'ll automatically detect the changes'
            }
        elif linking_strategy == LinkingMode.MANUAL_DNS.value:
            dns_instructions = configuration_data.get('dns_instructions', {})
            return {
                'action_required': 'dns_configuration',
                'instructions_type': 'manual_dns',
                'dns_records': dns_instructions.get('dns_records', []),
                'dns_instructions': dns_instructions.get('instructions', []),
                'verification_token': dns_instructions.get('verification_token'),
                'estimated_time': dns_instructions.get('estimated_propagation_time', '5-30 minutes'),
                'next_step': 'Add the required DNS records, then we\'ll automatically verify them'
            }
        else:
            return {
                'action_required': 'unknown',
                'next_step': 'Please wait while we prepare your instructions'
            }
    
    async def _get_nameserver_verification_status(
        self, 
        intent: Dict[str, Any], 
        configuration_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get nameserver verification status"""
        verification_id = configuration_data.get('verification_id')
        
        verification_status = {
            'verification_type': 'nameserver_change',
            'status': 'monitoring',
            'monitoring_since': configuration_data.get('monitoring_started'),
            'check_frequency': '5 minutes',
            'max_wait_time': '5 hours'
        }
        
        if verification_id:
            verification = await self.verification.get_verification_status(verification_id)
            if verification:
                verification_status.update({
                    'last_check': verification.get('last_checked_at'),
                    'next_check': verification.get('next_check_at'),
                    'retry_count': verification.get('retry_count', 0)
                })
        
        return verification_status
    
    async def _get_ownership_verification_status(
        self, 
        intent: Dict[str, Any], 
        configuration_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get DNS ownership verification status"""
        verification_id = configuration_data.get('verification_id')
        
        verification_status = {
            'verification_type': 'dns_txt',
            'status': 'monitoring',
            'monitoring_since': configuration_data.get('monitoring_started'),
            'check_frequency': '5 minutes',
            'max_wait_time': '24 hours'
        }
        
        if verification_id:
            verification = await self.verification.get_verification_status(verification_id)
            if verification:
                verification_status.update({
                    'expected_value': verification.get('expected_value'),
                    'last_check': verification.get('last_checked_at'),
                    'next_check': verification.get('next_check_at'),
                    'retry_count': verification.get('retry_count', 0)
                })
        
        return verification_status
    
    async def user_confirm_instructions(self, user_id: int, intent_id: int) -> Dict[str, Any]:
        """
        User confirms they have completed the required instructions.
        This triggers immediate verification instead of waiting for automatic checks.
        """
        try:
            intent = await self.get_intent_status(intent_id)
            if not intent or intent['user_id'] != user_id:
                return {
                    'success': False,
                    'error': 'Domain linking workflow not found'
                }
            
            workflow_state = intent['workflow_state']
            if workflow_state != WorkflowState.AWAITING_USER_CHOICE.value:
                return {
                    'success': False,
                    'error': 'No instructions are currently pending for this domain'
                }
            
            configuration_data = intent.get('configuration_data') or {}
            if isinstance(configuration_data, str):
                configuration_data = json.loads(configuration_data)
            linking_strategy = configuration_data.get('linking_strategy')
            
            # Trigger immediate verification based on strategy
            if linking_strategy == LinkingMode.SMART_MODE.value:
                # Start nameserver verification immediately
                await self.update_intent_state(
                    intent_id,
                    WorkflowState.VERIFYING_NAMESERVERS.value,
                    "user_confirmed_nameserver_change",
                    get_workflow_progress(WorkflowState.VERIFYING_NAMESERVERS.value)
                )
                
                # Trigger immediate nameserver check
                verification_id = configuration_data.get('verification_id')
                if verification_id:
                    verification_result = await self.verification.check_nameserver_verification(
                        verification_id, intent['domain_name']
                    )
                    
                    if verification_result.get('verified'):
                        await self._finalize_domain_linking(intent_id)
                        return {
                            'success': True,
                            'message': 'Nameserver change detected! Your domain is now being configured.',
                            'status': 'verifying_completion'
                        }
                    else:
                        return {
                            'success': True,
                            'message': 'Checking for nameserver changes. This may take a few minutes for DNS to propagate.',
                            'status': 'verifying_nameservers'
                        }
                
            elif linking_strategy == LinkingMode.MANUAL_DNS.value:
                # Start DNS verification immediately
                await self.update_intent_state(
                    intent_id,
                    WorkflowState.VERIFYING_OWNERSHIP.value,
                    "user_confirmed_dns_changes",
                    get_workflow_progress(WorkflowState.VERIFYING_OWNERSHIP.value)
                )
                
                return {
                    'success': True,
                    'message': 'Checking for DNS records. This may take a few minutes for DNS to propagate.',
                    'status': 'verifying_dns'
                }
            
            return {
                'success': False,
                'error': 'Unknown linking strategy'
            }
            
        except Exception as e:
            logger.error(f"💥 DOMAIN LINKING: User confirmation failed for intent {intent_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def start_verification_scheduler(self) -> None:
        """
        Start the background verification scheduler to process pending verifications.
        This ensures verifications are monitored and workflows progress automatically.
        """
        if self._verification_scheduler_running:
            logger.info("🔄 DOMAIN LINKING: Verification scheduler already running")
            return
        
        self._verification_scheduler_running = True
        logger.info("🚀 DOMAIN LINKING: Starting background verification scheduler")
        
        async def verification_processor():
            """Background task to process pending verifications"""
            while self._verification_scheduler_running:
                try:
                    # Get pending verifications
                    pending_verifications = await self.verification.get_pending_verifications()
                    
                    for verification in pending_verifications:
                        try:
                            await self._process_verification(verification)
                        except Exception as e:
                            logger.error(f"💥 DOMAIN LINKING: Error processing verification {verification['id']}: {e}")
                    
                    # Cleanup expired verifications
                    await self.verification.cleanup_expired_verifications()
                    
                    # Wait before next cycle
                    await asyncio.sleep(60)  # Check every minute
                    
                except Exception as e:
                    logger.error(f"💥 DOMAIN LINKING: Verification scheduler error: {e}")
                    await asyncio.sleep(60)  # Continue despite errors
        
        # Start as background task
        asyncio.create_task(verification_processor())
    
    async def _process_verification(self, verification: Dict[str, Any]) -> None:
        """Process a single verification and update workflow state if needed"""
        verification_id = verification['id']
        verification_type = verification['verification_type']
        intent_id = verification['domain_link_intent_id']
        
        try:
            # Get domain name for verification
            intent = await self.get_intent_status(intent_id)
            if not intent:
                logger.warning(f"⚠️ DOMAIN LINKING: Intent {intent_id} not found for verification {verification_id}")
                return
                
            domain_name = intent['domain_name']
            
            # Process based on verification type
            if verification_type == "nameserver_change":
                result = await self.verification.check_nameserver_verification(verification_id, domain_name)
                
                if result.get('verified'):
                    # Nameserver change verified, proceed to finalization
                    await self._finalize_domain_linking(intent_id)
                    logger.info(f"✅ DOMAIN LINKING: Nameserver verification completed for intent {intent_id}")
                    
            elif verification_type == "dns_txt":
                expected_token = verification.get('expected_value', '')
                result = await self.verification.check_dns_txt_verification(
                    verification_id, domain_name, expected_token
                )
                
                if result.get('verified'):
                    # DNS ownership verified, proceed to finalization
                    await self._finalize_domain_linking(intent_id)
                    logger.info(f"✅ DOMAIN LINKING: DNS ownership verification completed for intent {intent_id}")
                    
        except Exception as e:
            logger.error(f"💥 DOMAIN LINKING: Failed to process verification {verification_id}: {e}")
    
    async def stop_verification_scheduler(self) -> None:
        """Stop the background verification scheduler"""
        self._verification_scheduler_running = False
        logger.info("🛑 DOMAIN LINKING: Verification scheduler stopped")