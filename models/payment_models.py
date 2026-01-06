#!/usr/bin/env python3
"""
Normalized Payment DTOs for HostBay
Standardized data transfer objects with type-safe conversion and validation
All monetary values use Decimal for precision
"""

import logging
from typing import Optional, List, Dict, Any, Union
from decimal import Decimal
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from utils.type_converters import (
    safe_decimal, safe_string, safe_int, safe_uuid, 
    validate_currency_code, validate_email, validate_domain
)

logger = logging.getLogger(__name__)

class PaymentStatus(Enum):
    """Standardized payment status values"""
    PENDING = "pending"
    PROCESSING = "processing"
    CONFIRMED = "confirmed"
    SUCCESSFUL = "successful"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REFUNDED = "refunded"

class PaymentProvider(Enum):
    """Supported payment providers"""
    DYNOPAY = "dynopay"
    BLOCKBEE = "blockbee"
    STRIPE = "stripe"
    PAYPAL = "paypal"
    MANUAL = "manual"

class PaymentMethod(Enum):
    """Payment method types"""
    CRYPTOCURRENCY = "crypto"
    CREDIT_CARD = "card"
    BANK_TRANSFER = "bank"
    WALLET = "wallet"
    STABLECOIN = "stablecoin"

@dataclass
class PaymentIntentDTO:
    """
    Normalized Payment Intent Data Transfer Object
    Standardizes payment data across all providers
    """
    
    # Required fields
    order_id: str
    user_id: Optional[int] = None
    amount_usd: Decimal = field(default_factory=lambda: Decimal('0.00'))
    status: PaymentStatus = PaymentStatus.PENDING
    
    # Optional tracking ID
    id: Optional[int] = None
    
    # Provider information
    provider: PaymentProvider = PaymentProvider.DYNOPAY
    provider_payment_id: Optional[str] = None
    transaction_id: Optional[str] = None
    
    # Currency information
    original_amount: Optional[Decimal] = None
    original_currency: str = "USD"
    exchange_rate: Optional[Decimal] = None
    
    # Payment method details
    payment_method: Optional[PaymentMethod] = None
    cryptocurrency: Optional[str] = None
    wallet_address: Optional[str] = None
    
    # Metadata
    description: Optional[str] = None
    customer_email: Optional[str] = None
    callback_url: Optional[str] = None
    external_reference: Optional[str] = None
    
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    
    # Validation fields
    confirmations: int = 0
    required_confirmations: int = 1
    network_fee: Optional[Decimal] = None
    
    # Additional data
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Post-initialization validation and conversion"""
        self.validate()
    
    def validate(self) -> bool:
        """
        Validate all fields and perform type-safe conversions
        
        Returns:
            True if validation passes, raises ValueError if not
        """
        errors = []
        
        # Validate required fields
        if not self.order_id or not self.order_id.strip():
            errors.append("order_id cannot be empty")
        
        # Validate and convert amounts
        if not isinstance(self.amount_usd, Decimal):
            try:
                self.amount_usd = safe_decimal(self.amount_usd, field_name="amount_usd") or Decimal('0.00')
            except Exception as e:
                errors.append(f"Invalid amount_usd: {e}")
        
        if self.amount_usd < Decimal('0'):
            errors.append("amount_usd cannot be negative")
        
        # Validate original amount if provided
        if self.original_amount is not None:
            if not isinstance(self.original_amount, Decimal):
                try:
                    self.original_amount = safe_decimal(self.original_amount, field_name="original_amount")
                except Exception as e:
                    errors.append(f"Invalid original_amount: {e}")
        
        # Validate exchange rate if provided
        if self.exchange_rate is not None:
            if not isinstance(self.exchange_rate, Decimal):
                try:
                    self.exchange_rate = safe_decimal(self.exchange_rate, field_name="exchange_rate")
                except Exception as e:
                    errors.append(f"Invalid exchange_rate: {e}")
        
        # Validate currency codes
        if self.original_currency and not validate_currency_code(self.original_currency):
            logger.warning(f"⚠️ Invalid currency code: {self.original_currency}")
        
        # Validate email if provided
        if self.customer_email and not validate_email(self.customer_email):
            errors.append(f"Invalid email format: {self.customer_email}")
        
        # Validate user_id
        if self.user_id is not None:
            self.user_id = safe_int(self.user_id, field_name="user_id", min_value=1)
            if self.user_id is None:
                errors.append("Invalid user_id")
        
        # Convert string enums to proper enum values
        if isinstance(self.status, str):
            try:
                self.status = PaymentStatus(self.status.lower())
            except ValueError:
                logger.warning(f"⚠️ Unknown payment status: {self.status}, using PENDING")
                self.status = PaymentStatus.PENDING
        
        if isinstance(self.provider, str):
            try:
                self.provider = PaymentProvider(self.provider.lower())
            except ValueError:
                logger.warning(f"⚠️ Unknown payment provider: {self.provider}, using DYNOPAY")
                self.provider = PaymentProvider.DYNOPAY
        
        if errors:
            raise ValueError(f"PaymentIntentDTO validation failed: {'; '.join(errors)}")
        
        return True
    
    def is_confirmed(self) -> bool:
        """Check if payment is confirmed"""
        confirmed_statuses = {PaymentStatus.CONFIRMED, PaymentStatus.SUCCESSFUL, PaymentStatus.COMPLETED}
        return self.status in confirmed_statuses
    
    def is_crypto_payment(self) -> bool:
        """Check if this is a cryptocurrency payment"""
        return (self.payment_method == PaymentMethod.CRYPTOCURRENCY or 
                self.payment_method == PaymentMethod.STABLECOIN or
                self.cryptocurrency is not None)
    
    def get_display_amount(self) -> str:
        """Get formatted amount for display"""
        return f"${self.amount_usd:.2f}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API/database storage"""
        return {
            'order_id': self.order_id,
            'user_id': self.user_id,
            'amount_usd': float(self.amount_usd),  # Convert to float for JSON serialization
            'status': self.status.value,
            'provider': self.provider.value,
            'provider_payment_id': self.provider_payment_id,
            'transaction_id': self.transaction_id,
            'original_amount': float(self.original_amount) if self.original_amount else None,
            'original_currency': self.original_currency,
            'exchange_rate': float(self.exchange_rate) if self.exchange_rate else None,
            'payment_method': self.payment_method.value if self.payment_method else None,
            'cryptocurrency': self.cryptocurrency,
            'wallet_address': self.wallet_address,
            'description': self.description,
            'customer_email': self.customer_email,
            'callback_url': self.callback_url,
            'external_reference': self.external_reference,
            'confirmations': self.confirmations,
            'required_confirmations': self.required_confirmations,
            'network_fee': float(self.network_fee) if self.network_fee else None,
            'metadata': self.metadata
        }

@dataclass
class WalletCreditDTO:
    """
    Normalized Wallet Credit Data Transfer Object
    Standardizes wallet funding operations
    """
    
    # Required fields
    user_id: int
    amount_usd: Decimal
    transaction_id: str
    
    # Payment source information
    payment_intent: Optional[PaymentIntentDTO] = None
    source_provider: PaymentProvider = PaymentProvider.DYNOPAY
    source_transaction_id: Optional[str] = None
    
    # Credit details
    credit_type: str = "payment_confirmed"  # payment_confirmed, manual_credit, bonus, refund
    reference_order_id: Optional[str] = None
    description: Optional[str] = None
    
    # Validation
    is_processed: bool = False
    processed_at: Optional[datetime] = None
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Post-initialization validation"""
        self.validate()
    
    def validate(self) -> bool:
        """Validate wallet credit data"""
        errors = []
        
        # Validate user_id
        if not isinstance(self.user_id, int) or self.user_id <= 0:
            converted_user_id = safe_int(self.user_id, field_name="user_id", min_value=1)
            if converted_user_id is None:
                errors.append("Invalid user_id")
            else:
                self.user_id = converted_user_id
        
        # Validate amount
        if not isinstance(self.amount_usd, Decimal):
            converted_amount = safe_decimal(self.amount_usd, field_name="amount_usd")
            if converted_amount is None:
                errors.append("Invalid amount_usd")
            else:
                self.amount_usd = converted_amount
        
        if isinstance(self.amount_usd, Decimal) and self.amount_usd <= Decimal('0'):
            errors.append("amount_usd must be greater than 0")
        
        # Validate transaction_id
        if not self.transaction_id or not self.transaction_id.strip():
            errors.append("transaction_id cannot be empty")
        
        if errors:
            raise ValueError(f"WalletCreditDTO validation failed: {'; '.join(errors)}")
        
        return True
    
    def get_display_amount(self) -> str:
        """Get formatted amount for display"""
        return f"${self.amount_usd:.2f}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage"""
        return {
            'user_id': self.user_id,
            'amount_usd': float(self.amount_usd),
            'transaction_id': self.transaction_id,
            'source_provider': self.source_provider.value,
            'source_transaction_id': self.source_transaction_id,
            'credit_type': self.credit_type,
            'reference_order_id': self.reference_order_id,
            'description': self.description,
            'is_processed': self.is_processed,
            'metadata': self.metadata
        }

@dataclass
class DomainRegistrationDTO:
    """
    Normalized Domain Registration Data Transfer Object
    Standardizes domain registration operations
    """
    
    # Required fields
    domain_name: str
    user_id: int
    registration_years: int = 1
    
    # Payment information
    payment_intent: Optional[PaymentIntentDTO] = None
    total_cost_usd: Decimal = field(default_factory=lambda: Decimal('0.00'))
    
    # Domain details
    tld: Optional[str] = None
    registrar: str = "openprovider"
    nameservers: List[str] = field(default_factory=list)
    
    # Registration status
    registration_status: str = "pending"  # pending, processing, registered, failed
    registration_id: Optional[str] = None
    registry_reference: Optional[str] = None
    
    # Contact information
    registrant_email: Optional[str] = None
    admin_contact: Optional[Dict[str, str]] = None
    
    # Timestamps
    requested_at: Optional[datetime] = None
    registered_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    
    # Additional settings
    auto_renew: bool = True
    privacy_protection: bool = True
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Post-initialization validation"""
        self.validate()
    
    def validate(self) -> bool:
        """Validate domain registration data"""
        errors = []
        
        # Validate domain name
        if not self.domain_name or not self.domain_name.strip():
            errors.append("domain_name cannot be empty")
        else:
            if not validate_domain(self.domain_name):
                errors.append(f"Invalid domain name format: {self.domain_name}")
            
            # Extract TLD if not provided
            if not self.tld and '.' in self.domain_name:
                self.tld = self.domain_name.split('.')[-1].lower()
        
        # Validate user_id
        if not isinstance(self.user_id, int) or self.user_id <= 0:
            converted_user_id = safe_int(self.user_id, field_name="user_id", min_value=1)
            if converted_user_id is None:
                errors.append("Invalid user_id")
            else:
                self.user_id = converted_user_id
        
        # Validate registration years
        if not isinstance(self.registration_years, int) or self.registration_years < 1:
            self.registration_years = safe_int(self.registration_years, field_name="registration_years", min_value=1, max_value=10) or 1
        
        # Validate cost
        if not isinstance(self.total_cost_usd, Decimal):
            self.total_cost_usd = safe_decimal(self.total_cost_usd, field_name="total_cost_usd") or Decimal('0.00')
        
        # Validate email if provided
        if self.registrant_email and not validate_email(self.registrant_email):
            errors.append(f"Invalid registrant email format: {self.registrant_email}")
        
        if errors:
            raise ValueError(f"DomainRegistrationDTO validation failed: {'; '.join(errors)}")
        
        return True
    
    def is_registered(self) -> bool:
        """Check if domain is successfully registered"""
        return self.registration_status == "registered"
    
    def get_domain_parts(self) -> tuple:
        """Get domain name and TLD separately"""
        if '.' in self.domain_name:
            parts = self.domain_name.split('.')
            return '.'.join(parts[:-1]), parts[-1]
        return self.domain_name, self.tld or ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage"""
        return {
            'domain_name': self.domain_name,
            'user_id': self.user_id,
            'registration_years': self.registration_years,
            'total_cost_usd': float(self.total_cost_usd),
            'tld': self.tld,
            'registrar': self.registrar,
            'nameservers': self.nameservers,
            'registration_status': self.registration_status,
            'registration_id': self.registration_id,
            'registry_reference': self.registry_reference,
            'registrant_email': self.registrant_email,
            'admin_contact': self.admin_contact,
            'auto_renew': self.auto_renew,
            'privacy_protection': self.privacy_protection,
            'metadata': self.metadata
        }

# Utility functions for creating DTOs from raw data

def create_payment_intent_from_webhook(
    order_id: str,
    amount_usd: Union[str, int, float, Decimal],
    status: str,
    provider: str = "dynopay",
    **kwargs
) -> PaymentIntentDTO:
    """
    Create PaymentIntentDTO from webhook data with safe conversion
    
    Args:
        order_id: Payment order ID
        amount_usd: Payment amount (will be safely converted)
        status: Payment status
        provider: Payment provider name
        **kwargs: Additional fields
        
    Returns:
        Validated PaymentIntentDTO
    """
    try:
        # Convert amount safely
        safe_amount = safe_decimal(amount_usd, field_name="amount_usd")
        if safe_amount is None:
            logger.error(f"❌ Failed to convert amount for order {order_id}: {amount_usd}")
            safe_amount = Decimal('0.00')
        
        # Create DTO with safe conversions
        payment_intent = PaymentIntentDTO(
            order_id=safe_string(order_id, field_name="order_id") or "",
            amount_usd=safe_amount,
            status=PaymentStatus.PENDING,  # Will be validated in __post_init__
            provider=PaymentProvider.DYNOPAY,  # Will be validated in __post_init__
            provider_payment_id=kwargs.get('provider_payment_id'),
            transaction_id=kwargs.get('transaction_id') or kwargs.get('txid'),
            original_amount=safe_decimal(kwargs.get('original_amount'), field_name="original_amount"),
            original_currency=kwargs.get('original_currency', 'USD'),
            exchange_rate=safe_decimal(kwargs.get('exchange_rate'), field_name="exchange_rate"),
            cryptocurrency=kwargs.get('cryptocurrency') or kwargs.get('coin'),
            wallet_address=kwargs.get('wallet_address'),
            description=kwargs.get('description'),
            customer_email=kwargs.get('customer_email'),
            callback_url=kwargs.get('callback_url'),
            external_reference=kwargs.get('external_reference') or kwargs.get('external_id'),
            confirmations=safe_int(kwargs.get('confirmations'), default=0, field_name="confirmations") or 0,
            required_confirmations=safe_int(kwargs.get('required_confirmations'), default=1, field_name="required_confirmations") or 1,
            network_fee=safe_decimal(kwargs.get('network_fee') or kwargs.get('fee'), field_name="network_fee"),
            metadata=kwargs.get('metadata', {})
        )
        
        # Set status and provider with proper enum conversion
        try:
            payment_intent.status = PaymentStatus(status.lower()) if isinstance(status, str) else status
        except ValueError:
            logger.warning(f"⚠️ Unknown payment status: {status}, using PENDING")
            payment_intent.status = PaymentStatus.PENDING
        
        try:
            payment_intent.provider = PaymentProvider(provider.lower()) if isinstance(provider, str) else provider
        except ValueError:
            logger.warning(f"⚠️ Unknown payment provider: {provider}, using DYNOPAY")
            payment_intent.provider = PaymentProvider.DYNOPAY
        
        payment_intent.validate()  # Final validation
        
        return payment_intent
        
    except Exception as e:
        logger.error(f"❌ Failed to create PaymentIntentDTO for order {order_id}: {e}")
        logger.error(f"   Input data: amount_usd={amount_usd}, status={status}, provider={provider}")
        raise ValueError(f"Failed to create PaymentIntentDTO: {e}")

def create_wallet_credit_from_payment(
    payment_intent: PaymentIntentDTO,
    transaction_id: Optional[str] = None
) -> WalletCreditDTO:
    """
    Create WalletCreditDTO from confirmed payment intent
    
    Args:
        payment_intent: Confirmed payment intent
        transaction_id: Override transaction ID
        
    Returns:
        Validated WalletCreditDTO
    """
    if not payment_intent.user_id:
        raise ValueError("Payment intent must have user_id to create wallet credit")
    
    if not payment_intent.is_confirmed():
        raise ValueError(f"Payment intent not confirmed: {payment_intent.status}")
    
    return WalletCreditDTO(
        user_id=payment_intent.user_id,
        amount_usd=payment_intent.amount_usd,
        transaction_id=transaction_id or payment_intent.transaction_id or payment_intent.order_id,
        payment_intent=payment_intent,
        source_provider=payment_intent.provider,
        source_transaction_id=payment_intent.transaction_id,
        credit_type="payment_confirmed",
        reference_order_id=payment_intent.order_id,
        description=f"Wallet credit from {payment_intent.provider.value} payment {payment_intent.order_id}",
        metadata={
            'original_currency': payment_intent.original_currency,
            'exchange_rate': float(payment_intent.exchange_rate) if payment_intent.exchange_rate else None,
            'payment_method': payment_intent.payment_method.value if payment_intent.payment_method else None
        }
    )

# Test data for DTO validation
TEST_DTO_DATA = {
    "valid_payment": {
        "order_id": "wallet_fund_12345",
        "amount_usd": "10.50",
        "status": "confirmed",
        "provider": "dynopay",
        "transaction_id": "abc123def456"
    },
    "invalid_amount_domain": {
        "order_id": "wallet_fund_67890",
        "amount_usd": "cxh5tph6f3.de",  # This should be safely rejected
        "status": "confirmed",
        "provider": "dynopay"
    },
    "wallet_credit": {
        "user_id": 123,
        "amount_usd": "25.75",
        "transaction_id": "wallet_credit_789"
    }
}

def run_dto_tests():
    """Run DTO validation tests"""
    logger.info("🧪 Running DTO validation tests...")
    
    # Test valid payment intent
    try:
        payment = create_payment_intent_from_webhook(**TEST_DTO_DATA["valid_payment"])
        logger.info(f"✅ Valid payment intent created: {payment.order_id}, amount: {payment.get_display_amount()}")
    except Exception as e:
        logger.error(f"❌ Valid payment intent failed: {e}")
    
    # Test invalid amount with domain name
    try:
        payment = create_payment_intent_from_webhook(**TEST_DTO_DATA["invalid_amount_domain"])
        logger.error(f"❌ Domain name in amount should have been rejected but passed: {payment.amount_usd}")
    except Exception as e:
        logger.info(f"✅ Domain name in amount correctly rejected: {e}")
    
    # Test wallet credit
    try:
        wallet_credit = WalletCreditDTO(**TEST_DTO_DATA["wallet_credit"])
        logger.info(f"✅ Valid wallet credit created: user {wallet_credit.user_id}, amount: {wallet_credit.get_display_amount()}")
    except Exception as e:
        logger.error(f"❌ Valid wallet credit failed: {e}")

if __name__ == "__main__":
    # Run tests when executed directly
    logging.basicConfig(level=logging.INFO)
    run_dto_tests()