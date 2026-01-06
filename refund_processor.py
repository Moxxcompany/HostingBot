"""
Refund Processing System for Hosting Bundle Failures

This module provides comprehensive refund execution for hosting bundle failures,
handling both wallet payments (credit back to user balance) and crypto payments 
(initiate provider refund). Includes idempotent processing to prevent duplicate refunds.

Architecture:
- Idempotent refund processing with database tracking
- Payment provider refund APIs (DynoPay, BlockBee)
- Wallet transaction refunds (internal balance credits)
- State management for hosting_provision_intents and domain_orders
- User notifications for refund status updates
"""

import logging
import asyncio
import json
import secrets
import time
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from database import (
    execute_query, execute_update, get_telegram_id_from_user_id,
    verify_financial_operation_safety, ensure_financial_operations_allowed
)
from admin_alerts import send_critical_alert, send_error_alert, send_warning_alert

logger = logging.getLogger(__name__)

# ====================================================================
# REFUND PROCESSING SYSTEM - IDEMPOTENT BUNDLE REFUNDS
# ====================================================================

class RefundProcessingError(Exception):
    """Custom exception for refund processing errors"""
    pass

class DuplicateRefundError(Exception):
    """Raised when attempting to process a duplicate refund"""
    pass

async def refund_failed_bundle_payment(
    order_id: int,
    user_id: int,
    domain_name: str,
    bundle_result: Dict[str, Any],
    payment_details: Optional[Dict[str, Any]] = None,
    query_adapter: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Complete refund execution for hosting bundle failures.
    
    Handles both wallet payments (credit back to user balance) and crypto payments 
    (initiate provider refund). Includes comprehensive idempotent processing to prevent 
    duplicate refunds and ensure financial integrity.
    
    Args:
        order_id: Unique order identifier requiring refund
        user_id: Internal user ID for refund processing
        domain_name: Domain associated with the failed bundle
        bundle_result: Complete result from hosting orchestrator with failure details
        payment_details: Original payment information for provider refunds
        query_adapter: For sending user notifications
        
    Returns:
        Dict with refund processing results and status
    """
    logger.info(f"🔄 REFUND PROCESSOR: Starting refund for order {order_id}, domain {domain_name}")
    
    try:
        # CRITICAL SECURITY: Verify financial operations are allowed
        if not verify_financial_operation_safety(f"Bundle Refund Order {order_id}"):
            logger.error(f"🚫 REFUND BLOCKED: Financial safety check failed for order {order_id}")
            # Send admin alert for financial safety block
            await send_critical_alert(
                "RefundProcessor",
                f"Refund blocked - financial safety check failed for order {order_id}",
                "payment_processing",
                {
                    "order_id": order_id,
                    "user_id": user_id,
                    "domain_name": domain_name,
                    "bundle_result": bundle_result,
                    "safety_reason": "Financial operations currently disabled"
                }
            )
            return {
                'success': False,
                'error': 'Financial operations currently disabled - refund blocked for safety',
                'order_id': order_id,
                'financial_safety': False
            }
        
        # Step 1: Check for duplicate refund processing
        existing_refund = await _check_existing_refund(order_id, user_id, domain_name)
        if existing_refund:
            logger.warning(f"🔄 REFUND PROCESSOR: Duplicate refund detected for order {order_id}")
            return {
                'success': False,
                'error': 'Refund already processed',
                'order_id': order_id,
                'duplicate_refund': True,
                'existing_refund_id': existing_refund['id']
            }
        
        # Step 2: Create refund tracking record for idempotency
        refund_id = await _create_refund_tracking(order_id, user_id, domain_name, bundle_result)
        if not refund_id:
            logger.error(f"❌ REFUND PROCESSOR: Failed to create refund tracking for order {order_id}")
            return {
                'success': False,
                'error': 'Failed to initialize refund tracking',
                'order_id': order_id
            }
        
        # Step 3: Determine payment type and amount
        payment_info = await _analyze_payment_for_refund(order_id, user_id, domain_name, payment_details)
        if not payment_info:
            logger.error(f"❌ REFUND PROCESSOR: Could not analyze payment for refund - order {order_id}")
            await _fail_refund_tracking(refund_id, "Payment analysis failed")
            return {
                'success': False,
                'error': 'Payment analysis failed - cannot determine refund method',
                'order_id': order_id,
                'refund_id': refund_id
            }
        
        # Step 4: Execute appropriate refund method
        refund_result = await _execute_refund_by_type(
            refund_id=refund_id,
            payment_info=payment_info,
            bundle_result=bundle_result,
            user_id=user_id
        )
        
        if not refund_result.get('success'):
            logger.error(f"❌ REFUND PROCESSOR: Refund execution failed for order {order_id}: {refund_result.get('error')}")
            await _fail_refund_tracking(refund_id, refund_result.get('error', 'Refund execution failed'))
            
            # Send failure notification to user
            if query_adapter:
                await _send_refund_failure_notification(
                    query_adapter, user_id, domain_name, payment_info, refund_result.get('error', 'Unknown error')
                )
            
            return {
                'success': False,
                'error': refund_result.get('error', 'Refund execution failed'),
                'order_id': order_id,
                'refund_id': refund_id,
                'payment_type': payment_info.get('payment_type'),
                'amount': payment_info.get('amount')
            }
        
        # Step 5: Update database states after successful refund
        await _update_database_states_after_refund(order_id, user_id, domain_name, bundle_result)
        
        # Step 6: Complete refund tracking
        await _complete_refund_tracking(refund_id, refund_result)
        
        # Step 7: Send success notification to user
        if query_adapter:
            await _send_refund_success_notification(
                query_adapter, user_id, domain_name, payment_info, refund_result, bundle_result
            )
        
        logger.info(f"✅ REFUND PROCESSOR: Complete refund processed for order {order_id}")
        return {
            'success': True,
            'order_id': order_id,
            'refund_id': refund_id,
            'payment_type': payment_info.get('payment_type'),
            'amount': payment_info.get('amount'),
            'refund_method': refund_result.get('refund_method'),
            'provider_response': refund_result.get('provider_response'),
            'bundle_failure_phase': bundle_result.get('phase', 'unknown')
        }
        
    except Exception as e:
        logger.error(f"❌ REFUND PROCESSOR: Exception during refund processing for order {order_id}: {e}")
        return {
            'success': False,
            'error': f"Refund processing exception: {str(e)}",
            'order_id': order_id
        }

async def _check_existing_refund(order_id: int, user_id: int, domain_name: str) -> Optional[Dict[str, Any]]:
    """Check if refund has already been processed for this order"""
    try:
        existing_refunds = await execute_query(
            """SELECT id, status, created_at FROM refund_tracking 
               WHERE order_id = %s AND user_id = %s AND domain_name = %s 
               AND status IN ('processing', 'completed', 'provider_pending')
               ORDER BY created_at DESC LIMIT 1""",
            (order_id, user_id, domain_name)
        )
        
        if existing_refunds:
            refund = existing_refunds[0]
            logger.info(f"🔍 REFUND CHECK: Found existing refund {refund['id']} status: {refund['status']}")
            return refund
        
        return None
        
    except Exception as e:
        logger.error(f"❌ Error checking existing refund: {e}")
        return None

async def _create_refund_tracking(
    order_id: int, 
    user_id: int, 
    domain_name: str, 
    bundle_result: Dict[str, Any]
) -> Optional[int]:
    """Create refund tracking record for idempotency"""
    try:
        # Generate idempotency key
        idempotency_key = secrets.token_urlsafe(32)
        
        # Create refund tracking record
        refund_records = await execute_query(
            """INSERT INTO refund_tracking 
               (order_id, user_id, domain_name, status, failure_phase, failure_reason, idempotency_key)
               VALUES (%s, %s, %s, 'processing', %s, %s, %s)
               RETURNING id""",
            (
                order_id, 
                user_id, 
                domain_name, 
                bundle_result.get('phase', 'unknown'),
                bundle_result.get('error', 'Bundle processing failed'),
                idempotency_key
            )
        )
        
        if refund_records:
            refund_id = refund_records[0]['id']
            logger.info(f"✅ Created refund tracking record {refund_id} for order {order_id}")
            return refund_id
        
        return None
        
    except Exception as e:
        logger.error(f"❌ Failed to create refund tracking: {e}")
        return None

async def _analyze_payment_for_refund(
    order_id: int, 
    user_id: int, 
    domain_name: str, 
    payment_details: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Analyze payment type and amount for refund processing"""
    try:
        # Step 1: Check wallet transactions first (internal payments)
        wallet_transactions = await execute_query(
            """SELECT amount, currency, transaction_type, payment_id, external_txid 
               FROM wallet_transactions 
               WHERE user_id = %s AND description LIKE %s 
               AND transaction_type = 'debit' AND status = 'completed'
               ORDER BY created_at DESC LIMIT 1""",
            (user_id, f"%{domain_name}%")
        )
        
        if wallet_transactions:
            transaction = wallet_transactions[0]
            logger.info(f"💰 PAYMENT ANALYSIS: Wallet payment found - ${transaction['amount']} {transaction['currency']}")
            return {
                'payment_type': 'wallet',
                'amount': float(transaction['amount']),
                'currency': transaction['currency'],
                'transaction_id': transaction['payment_id'],
                'external_txid': transaction['external_txid']
            }
        
        # Step 2: Check domain_orders for crypto payments
        domain_orders = await execute_query(
            """SELECT expected_amount, currency, payment_address, blockbee_order_id, txid
               FROM domain_orders 
               WHERE user_id = %s AND domain_name = %s 
               AND status IN ('completed', 'paid')
               ORDER BY created_at DESC LIMIT 1""",
            (user_id, domain_name)
        )
        
        if domain_orders:
            order = domain_orders[0]
            logger.info(f"💰 PAYMENT ANALYSIS: Crypto payment found - ${order['expected_amount']} {order['currency']}")
            
            # Determine provider from payment details or order data
            provider = None
            if payment_details:
                if 'dynopay' in str(payment_details).lower():
                    provider = 'dynopay'
                elif 'blockbee' in str(payment_details).lower() or order['blockbee_order_id']:
                    provider = 'blockbee'
            
            return {
                'payment_type': 'crypto',
                'amount': float(order['expected_amount']),
                'currency': order['currency'],
                'payment_address': order['payment_address'],
                'provider': provider,
                'blockbee_order_id': order['blockbee_order_id'],
                'txid': order['txid']
            }
        
        # Step 3: Fallback to payment_details if database lookup fails
        if payment_details:
            # ARCHITECT FIX: Support both amount_usd and amount fields for better compatibility  
            amount = payment_details.get('amount_usd', payment_details.get('amount', 0))
            provider = payment_details.get('provider', payment_details.get('method', 'unknown'))
            
            if amount > 0:
                # ARCHITECT FIX: Determine payment type based on provider/method
                payment_type = 'wallet' if provider in ['wallet', 'wallet_payment'] else 'crypto'
                
                logger.info(f"💰 PAYMENT ANALYSIS: Using fallback from payment_details - ${amount} ({payment_type})")
                return {
                    'payment_type': payment_type,
                    'amount': float(amount),
                    'currency': 'USD',
                    'provider': provider,
                    'fallback': True
                }
        
        logger.warning(f"⚠️ PAYMENT ANALYSIS: No payment found for refund - order {order_id}")
        return None
        
    except Exception as e:
        logger.error(f"❌ Error analyzing payment for refund: {e}")
        return None

async def _execute_refund_by_type(
    refund_id: int,
    payment_info: Dict[str, Any],
    bundle_result: Dict[str, Any],
    user_id: int
) -> Dict[str, Any]:
    """Execute refund based on payment type and payment status"""
    try:
        payment_type = payment_info.get('payment_type')
        
        if payment_type == 'wallet':
            # Process wallet refund (credit back to user balance)
            return await _process_wallet_refund(refund_id, payment_info, user_id)
        
        elif payment_type == 'crypto':
            # CRITICAL FIX: Check if crypto was actually received - no refund if not paid
            crypto_was_received = await _was_crypto_payment_received(payment_info, bundle_result)
            
            if crypto_was_received:
                logger.info(f"💳 CRYPTO REFUND: Crypto was received - refunding USD equivalent to wallet balance")
                # Refund USD equivalent to wallet balance (not back to crypto)
                return await _process_wallet_refund(refund_id, payment_info, user_id)
            else:
                logger.info(f"✅ NO REFUND NEEDED: Crypto payment address generated but no payment received")
                # No refund needed - user didn't actually pay anything
                return {
                    'success': True,
                    'refund_method': 'no_refund_needed',
                    'reason': 'Payment address generated but crypto not received',
                    'order_cancelled': True
                }
        
        else:
            logger.error(f"❌ Unknown payment type for refund: {payment_type}")
            return {
                'success': False,
                'error': f'Unknown payment type: {payment_type}',
                'payment_type': payment_type
            }
            
    except Exception as e:
        logger.error(f"❌ Error executing refund by type: {e}")
        return {
            'success': False,
            'error': f'Refund execution failed: {str(e)}'
        }

async def _was_crypto_payment_received(
    payment_info: Dict[str, Any],
    bundle_result: Dict[str, Any]
) -> bool:
    """
    Determine if crypto payment was actually received and needs refunding.
    
    Returns True if crypto was received and needs refund.
    Returns False if no crypto was received (no refund needed).
    """
    try:
        # Step 1: Look up payment intent status to determine if crypto was actually sent
        payment_address = payment_info.get('payment_address')
        
        if not payment_address:
            logger.info(f"💰 CRYPTO CHECK: No payment address found - no crypto received")
            return False
        
        # Step 2: Query payment intent by payment address to get status
        from database import execute_query
        
        intent_results = await execute_query(
            """SELECT status, payment_provider, payment_address, updated_at 
               FROM payment_intents 
               WHERE payment_address = %s 
               ORDER BY created_at DESC LIMIT 1""",
            (payment_address,)
        )
        
        if not intent_results:
            logger.info(f"💰 CRYPTO CHECK: No payment intent found for address {payment_address} - no crypto received")
            return False
        
        intent = intent_results[0]
        intent_status = intent['status'].lower()
        
        # Step 3: Determine if crypto was received based on intent status
        # No crypto received: address created but no payment detected
        no_payment_statuses = ['created', 'creating_address', 'address_created']
        
        # Crypto received: payment has been sent and detected by provider
        payment_received_statuses = ['pending_confirmation', 'pending', 'completed', 'paid']
        
        if intent_status in no_payment_statuses:
            logger.info(f"💰 CRYPTO CHECK: Intent status '{intent_status}' - no crypto received yet")
            return False
        elif intent_status in payment_received_statuses:
            logger.info(f"💰 CRYPTO CHECK: Intent status '{intent_status}' - crypto was received and confirmed")
            return True
        else:
            # Unknown status - default to no payment received for safety
            logger.warning(f"⚠️ CRYPTO CHECK: Unknown intent status '{intent_status}' - assuming no crypto received")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error checking crypto payment status: {e}")
        # Default to no payment received on error for safety
        logger.warning(f"⚠️ CRYPTO CHECK: Error occurred - assuming no crypto received")
        return False

async def _process_wallet_refund(
    refund_id: int,
    payment_info: Dict[str, Any],
    user_id: int
) -> Dict[str, Any]:
    """
    ATOMIC REFUND: Process wallet refund by crediting balance back to user
    ARCHITECT FIX 2: Wrap refund insert + balance change in single DB transaction
    """
    try:
        amount = payment_info.get('amount', 0)
        currency = payment_info.get('currency', 'USD')
        
        logger.info(f"💳 ATOMIC WALLET REFUND: Processing ${amount} {currency} refund for user {user_id}")
        
        # CRITICAL SECURITY: Verify amount is positive
        if amount <= 0:
            return {
                'success': False,
                'error': f'Invalid refund amount: ${amount}',
                'amount': amount
            }
        
        # ARCHITECT FIX 2: ATOMIC TRANSACTION - Wrap both operations in single transaction
        from database import run_in_transaction
        try:
            from database import TEST_STRICT_DB
        except ImportError:
            TEST_STRICT_DB = False  # Default to non-strict mode if not defined
        
        # Generate unique refund transaction ID for idempotency
        refund_transaction_id = f"refund_{refund_id}_{int(time.time())}"
        
        def _atomic_refund_operation(conn):
            """Atomic operation: balance update + transaction record in single transaction"""
            import psycopg2
            from psycopg2.extras import RealDictCursor
            
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Step 1: Check for duplicate refund transaction (idempotency)
                cursor.execute(
                    """SELECT id FROM wallet_transactions 
                       WHERE payment_id = %s AND user_id = %s AND transaction_type = 'credit'""",
                    (refund_transaction_id, user_id)
                )
                existing_transaction = cursor.fetchone()
                
                if existing_transaction:
                    logger.info(f"✅ IDEMPOTENCY: Refund transaction {refund_transaction_id} already exists")
                    return {
                        'success': True,
                        'refund_method': 'wallet_credit',
                        'amount': amount,
                        'currency': currency,
                        'transaction_id': existing_transaction['id'],
                        'user_id': user_id,
                        'idempotent': True
                    }
                
                # Step 2: Update user wallet balance atomically
                cursor.execute(
                    """UPDATE users 
                       SET wallet_balance = wallet_balance + %s, updated_at = CURRENT_TIMESTAMP
                       WHERE id = %s""",
                    (amount, user_id)
                )
                
                # ARCHITECT FIX 4: Honor TEST_STRICT_DB - Check rowcount
                rows_updated = cursor.rowcount
                if rows_updated != 1:
                    error_msg = f"Failed to update wallet balance for user {user_id} (rows_updated: {rows_updated})"
                    logger.error(f"❌ ATOMIC REFUND: {error_msg}")
                    if TEST_STRICT_DB:
                        raise Exception(error_msg)
                    else:
                        return {
                            'success': False,
                            'error': error_msg,
                            'user_id': user_id,
                            'amount': amount
                        }
                
                # Step 3: Create wallet transaction record atomically
                cursor.execute(
                    """INSERT INTO wallet_transactions 
                       (user_id, transaction_type, amount, currency, status, payment_id, description)
                       VALUES (%s, 'credit', %s, %s, 'completed', %s, %s)
                       RETURNING id""",
                    (
                        user_id,
                        amount,
                        currency,
                        refund_transaction_id,
                        f"Refund for hosting bundle failure - ${amount} {currency}"
                    )
                )
                
                transaction_record = cursor.fetchone()
                if not transaction_record:
                    error_msg = "Failed to create refund transaction record"
                    logger.error(f"❌ ATOMIC REFUND: {error_msg}")
                    if TEST_STRICT_DB:
                        raise Exception(error_msg)
                    else:
                        return {
                            'success': False,
                            'error': error_msg
                        }
                
                transaction_id = transaction_record['id']
                logger.info(f"✅ ATOMIC WALLET REFUND: Successfully processed ${amount} refund for user {user_id}")
                return {
                    'success': True,
                    'refund_method': 'wallet_credit',
                    'amount': amount,
                    'currency': currency,
                    'transaction_id': transaction_id,
                    'user_id': user_id,
                    'refund_transaction_id': refund_transaction_id
                }
        
        # Execute atomic transaction
        result = await run_in_transaction(_atomic_refund_operation)
        return result
        
    except Exception as e:
        logger.error(f"❌ ATOMIC WALLET REFUND: Exception processing refund: {e}")
        # Handle TEST_STRICT_DB safely with proper scoping
        try:
            from database import TEST_STRICT_DB
            if TEST_STRICT_DB:
                # ARCHITECT FIX 4: Honor TEST_STRICT_DB - re-raise exceptions in strict mode
                raise e
        except (NameError, ImportError):
            # TEST_STRICT_DB not defined, continue with normal error handling
            pass
        return {
            'success': False,
            'error': f'Atomic wallet refund failed: {str(e)}'
        }

# REMOVED: _process_crypto_refund - All refunds now go to wallet balance

# REMOVED: Provider refund functions - All refunds now go to wallet balance

async def _update_database_states_after_refund(
    order_id: int,
    user_id: int,
    domain_name: str,
    bundle_result: Dict[str, Any]
) -> None:
    """Update database states after successful refund processing"""
    try:
        # Update hosting_provision_intents status
        await execute_update(
            """UPDATE hosting_provision_intents 
               SET status = 'refunded', updated_at = CURRENT_TIMESTAMP
               WHERE user_id = %s AND domain_name = %s 
               AND status IN ('payment_confirmed', 'processing', 'failed')""",
            (user_id, domain_name)
        )
        
        # Update domain_orders status
        await execute_update(
            """UPDATE domain_orders 
               SET status = 'refunded', updated_at = CURRENT_TIMESTAMP
               WHERE id = %s AND user_id = %s AND domain_name = %s""",
            (order_id, user_id, domain_name)
        )
        
        logger.info(f"✅ Updated database states after refund for order {order_id}")
        
    except Exception as e:
        logger.error(f"❌ Error updating database states after refund: {e}")

async def _complete_refund_tracking(
    refund_id: int,
    refund_result: Dict[str, Any]
) -> None:
    """Mark refund tracking as completed"""
    try:
        status = 'completed' if refund_result.get('success') else 'failed'
        provider_status = refund_result.get('status', status)
        
        await execute_update(
            """UPDATE refund_tracking 
               SET status = %s, provider_status = %s, refund_method = %s, 
                   provider_response = %s, completed_at = CURRENT_TIMESTAMP,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = %s""",
            (
                provider_status,  # Use provider status if available
                refund_result.get('status'),
                refund_result.get('refund_method'),
                json.dumps(refund_result.get('provider_response', {})),
                refund_id
            )
        )
        
        logger.info(f"✅ Completed refund tracking {refund_id} with status: {provider_status}")
        
    except Exception as e:
        logger.error(f"❌ Error completing refund tracking: {e}")

async def _fail_refund_tracking(
    refund_id: int,
    error_message: str
) -> None:
    """Mark refund tracking as failed"""
    try:
        await execute_update(
            """UPDATE refund_tracking 
               SET status = 'failed', error_message = %s, updated_at = CURRENT_TIMESTAMP
               WHERE id = %s""",
            (error_message, refund_id)
        )
        
        logger.info(f"❌ Failed refund tracking {refund_id}: {error_message}")
        
    except Exception as e:
        logger.error(f"❌ Error failing refund tracking: {e}")

async def _send_refund_success_notification(
    query_adapter: Any,
    user_id: int,
    domain_name: str,
    payment_info: Dict[str, Any],
    refund_result: Dict[str, Any],
    bundle_result: Dict[str, Any]
) -> None:
    """Send refund success notification to user"""
    try:
        amount = payment_info.get('amount', 0)
        currency = payment_info.get('currency', 'USD')
        refund_method = refund_result.get('refund_method', 'unknown')
        failure_phase = bundle_result.get('phase', 'unknown')
        
        if refund_method == 'wallet_credit':
            message = f"""🔄 <b>Refund Processed</b>

Your hosting bundle order for <code>{domain_name}</code> could not be completed due to a {failure_phase} failure.

💰 <b>Refund Details:</b>
• Amount: ${amount:.2f} {currency}
• Method: Wallet Credit
• Status: ✅ Completed

Your wallet balance has been credited automatically. You can use this balance for future purchases or request a withdrawal.

We apologize for the inconvenience. Please try again or contact support if you need assistance."""

        else:
            status_emoji = "⏳" if refund_result.get('status') == 'provider_pending' else "✅"
            status_text = "Processing" if refund_result.get('status') == 'provider_pending' else "Completed"
            
            message = f"""🔄 <b>Refund Initiated</b>

Your hosting bundle order for <code>{domain_name}</code> could not be completed due to a {failure_phase} failure.

💰 <b>Refund Details:</b>
• Amount: ${amount:.2f} {currency}
• Method: {refund_method.replace('_', ' ').title()}
• Status: {status_emoji} {status_text}

{refund_result.get('provider_response', 'Your refund is being processed by the payment provider.')}

We apologize for the inconvenience. Please try again or contact support if you need assistance."""

        # Use the same message sending pattern as hosting orchestrator
        await _send_message_to_user(query_adapter, message)
        logger.info(f"✅ Sent refund success notification to user {user_id}")
        
    except Exception as e:
        logger.error(f"❌ Error sending refund success notification: {e}")

async def _send_refund_failure_notification(
    query_adapter: Any,
    user_id: int,
    domain_name: str,
    payment_info: Dict[str, Any],
    error_message: str
) -> None:
    """Send refund failure notification to user"""
    try:
        amount = payment_info.get('amount', 0)
        currency = payment_info.get('currency', 'USD')
        
        message = f"""⚠️ <b>Refund Processing Issue</b>

Your hosting bundle order for <code>{domain_name}</code> failed, but there was an issue processing your refund.

💰 <b>Refund Details:</b>
• Amount: ${amount:.2f} {currency}
• Status: ❌ Processing Failed
• Error: {error_message}

<b>Important:</b> Your refund will be processed manually by our support team within 24 hours. Please contact support if you have any questions.

We sincerely apologize for this inconvenience and will ensure your refund is processed promptly."""

        # Use the same message sending pattern as hosting orchestrator
        await _send_message_to_user(query_adapter, message)
        logger.info(f"✅ Sent refund failure notification to user {user_id}")
        
    except Exception as e:
        logger.error(f"❌ Error sending refund failure notification: {e}")

async def _send_message_to_user(query_adapter: Any, message: str):
    """Send message to user using appropriate adapter method"""
    try:
        if hasattr(query_adapter, 'send_message_to_user'):
            await query_adapter.send_message_to_user(message, parse_mode='HTML')
        elif hasattr(query_adapter, 'user_id'):
            # Use webhook-style messaging for non-telegram contexts
            from webhook_handler import queue_user_message
            await queue_user_message(query_adapter.user_id, message, parse_mode='HTML')
        else:
            logger.warning("Query adapter doesn't support message sending")
    except Exception as e:
        logger.error(f"Failed to send message to user: {e}")