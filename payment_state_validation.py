"""
Payment State Validation Module
Implements state transition validation for payment intents to prevent invalid status changes
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class PaymentState:
    """Payment state constants"""
    CREATED = 'created'
    ADDRESS_CREATED = 'address_created'
    PROCESSING = 'processing'
    PENDING = 'pending'
    CONFIRMED = 'confirmed'
    FAILED = 'failed'
    EXPIRED = 'expired'


# Valid transitions mapping - defines allowed state transitions
VALID_TRANSITIONS: Dict[str, List[str]] = {
    PaymentState.CREATED: [PaymentState.ADDRESS_CREATED, PaymentState.PROCESSING, PaymentState.PENDING],
    PaymentState.ADDRESS_CREATED: [PaymentState.PENDING, PaymentState.CONFIRMED, PaymentState.FAILED, PaymentState.EXPIRED],
    PaymentState.PROCESSING: [PaymentState.CONFIRMED, PaymentState.FAILED, PaymentState.EXPIRED],
    PaymentState.PENDING: [PaymentState.CONFIRMED, PaymentState.FAILED, PaymentState.EXPIRED],
    PaymentState.CONFIRMED: [],  # Final state - no transitions allowed
    PaymentState.FAILED: [],     # Final state - no transitions allowed
    PaymentState.EXPIRED: []     # Final state - no transitions allowed
}


def validate_payment_state_transition(current_state: str, new_state: str) -> bool:
    """
    Validate if payment state transition is allowed
    
    Args:
        current_state: Current payment state
        new_state: Desired new payment state
        
    Returns:
        bool: True if transition is valid
        
    Raises:
        ValueError: If transition is invalid
    """
    if not current_state:
        # Allow setting initial state
        if new_state in VALID_TRANSITIONS:
            logger.info(f"✅ STATE VALIDATION: Setting initial state to '{new_state}'")
            return True
        else:
            raise ValueError(f"Invalid initial payment state: {new_state}")
    
    if current_state not in VALID_TRANSITIONS:
        raise ValueError(f"Invalid current payment state: {current_state}")
    
    if new_state not in VALID_TRANSITIONS[current_state]:
        raise ValueError(f"Invalid transition from {current_state} to {new_state}")
    
    logger.info(f"✅ STATE VALIDATION: Valid transition from '{current_state}' to '{new_state}'")
    return True


def is_final_state(state: str) -> bool:
    """
    Check if a payment state is final (no further transitions allowed)
    
    Args:
        state: Payment state to check
        
    Returns:
        bool: True if state is final
    """
    return state in [PaymentState.CONFIRMED, PaymentState.FAILED, PaymentState.EXPIRED]


def get_valid_next_states(current_state: str) -> List[str]:
    """
    Get list of valid next states from current state
    
    Args:
        current_state: Current payment state
        
    Returns:
        List[str]: List of valid next states
    """
    if current_state not in VALID_TRANSITIONS:
        return []
    
    return VALID_TRANSITIONS[current_state]


def log_transition_attempt(current_state: str, new_state: str, payment_intent_id: int = None, 
                          order_id: str = None) -> None:
    """
    Log payment state transition attempt for debugging and auditing
    
    Args:
        current_state: Current payment state
        new_state: Desired new payment state  
        payment_intent_id: Payment intent ID (optional)
        order_id: Order ID (optional)
    """
    context = []
    if payment_intent_id:
        context.append(f"intent_id={payment_intent_id}")
    if order_id:
        context.append(f"order_id={order_id}")
    
    context_str = f" ({', '.join(context)})" if context else ""
    
    try:
        validate_payment_state_transition(current_state, new_state)
        logger.info(f"🔄 STATE TRANSITION: {current_state} → {new_state}{context_str}")
    except ValueError as e:
        logger.error(f"🚫 INVALID STATE TRANSITION: {current_state} → {new_state}{context_str} - {e}")
        raise