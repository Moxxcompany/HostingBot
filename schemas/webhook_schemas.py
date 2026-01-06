#!/usr/bin/env python3
"""
Pydantic Schema Validators for HostBay Webhook Data
Comprehensive validation for DynoPay and BlockBee webhook payloads
Prevents type conversion errors and validates data integrity
"""

import logging
from typing import Optional, Union, Dict, Any, List
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator, model_validator, ValidationInfo
from datetime import datetime
from utils.type_converters import (
    safe_decimal, safe_string, safe_int, safe_uuid,
    validate_currency_code, is_likely_domain_name
)

logger = logging.getLogger(__name__)

class BaseWebhookSchema(BaseModel):
    """Base schema for all webhook data with common validation"""
    
    class Config:
        # Pydantic v2 config
        str_strip_whitespace = True
        validate_assignment = True
        extra = "allow"  # Allow extra fields for compatibility
        arbitrary_types_allowed = True

    @field_validator('*', mode='before')
    @classmethod
    def prevent_domain_names_in_amounts(cls, v, info: ValidationInfo):
        """Global validator to prevent domain names in amount fields"""
        if info.field_name and 'amount' in info.field_name.lower():
            if isinstance(v, str) and is_likely_domain_name(v):
                logger.error(f"❌ SCHEMA VALIDATION: Domain name detected in amount field '{info.field_name}': {v}")
                raise ValueError(f"Domain name not allowed in amount field: {v}")
        return v

class DynoPayMetaData(BaseModel):
    """DynoPay meta_data nested structure"""
    order_id: Optional[str] = Field(None, description="Order ID from meta_data")
    refId: Optional[str] = Field(None, description="Reference ID")
    user_id: Optional[Union[str, int]] = Field(None, description="User ID")
    callback_url: Optional[str] = Field(None, description="Callback URL")
    external_id: Optional[str] = Field(None, description="External reference")
    
    # Additional fields that may appear
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    description: Optional[str] = None

class DynoPayWebhookSchema(BaseWebhookSchema):
    """
    DynoPay webhook schema with comprehensive field validation
    Handles all known field variations and nested structures
    """
    
    # Required fields
    order_id: str = Field(..., description="Payment order ID")
    status: str = Field(..., description="Payment status")
    
    # Amount fields - DynoPay uses various field names
    base_amount: Optional[Union[str, int, float, Decimal]] = Field(None, description="Base amount in USD")
    amount_usd: Optional[Union[str, int, float, Decimal]] = Field(None, description="Amount in USD")
    amount: Optional[Union[str, int, float, Decimal]] = Field(None, description="Payment amount")
    value_usd: Optional[Union[str, int, float, Decimal]] = Field(None, description="USD value")
    final_amount_usd: Optional[Union[str, int, float, Decimal]] = Field(None, description="Final USD amount")
    confirmed_amount_usd: Optional[Union[str, int, float, Decimal]] = Field(None, description="Confirmed USD amount")
    total_usd: Optional[Union[str, int, float, Decimal]] = Field(None, description="Total USD amount")
    
    # Cryptocurrency fields
    crypto_amount: Optional[Union[str, int, float, Decimal]] = Field(None, description="Crypto amount")
    coin_amount: Optional[Union[str, int, float, Decimal]] = Field(None, description="Coin amount")
    paid_amount: Optional[Union[str, int, float, Decimal]] = Field(None, description="Paid crypto amount")
    received_amount: Optional[Union[str, int, float, Decimal]] = Field(None, description="Received amount")
    confirmed_amount: Optional[Union[str, int, float, Decimal]] = Field(None, description="Confirmed amount")
    final_amount: Optional[Union[str, int, float, Decimal]] = Field(None, description="Final amount")
    
    # Currency and transaction fields
    currency: Optional[str] = Field("USD", description="Payment currency")
    txid: Optional[str] = Field(None, description="Transaction ID")
    transaction_id: Optional[str] = Field(None, description="Alternative transaction ID field")
    hash: Optional[str] = Field(None, description="Transaction hash")
    
    # Provider and metadata
    provider: Optional[str] = Field("dynopay", description="Payment provider")
    payment_method: Optional[str] = Field(None, description="Payment method used")
    network: Optional[str] = Field(None, description="Blockchain network")
    
    # Nested structures
    meta_data: Optional[Union[Dict[str, Any], DynoPayMetaData]] = Field(None, description="Metadata object")
    payment_data: Optional[Dict[str, Any]] = Field(None, description="Payment-specific data")
    transaction_data: Optional[Dict[str, Any]] = Field(None, description="Transaction details")
    
    # Timestamps
    created_at: Optional[Union[str, datetime]] = Field(None, description="Creation timestamp")
    updated_at: Optional[Union[str, datetime]] = Field(None, description="Update timestamp")
    confirmed_at: Optional[Union[str, datetime]] = Field(None, description="Confirmation timestamp")
    
    # Additional common fields
    callback_url: Optional[str] = Field(None, description="Webhook callback URL")
    external_id: Optional[str] = Field(None, description="External reference ID")
    customer_email: Optional[str] = Field(None, description="Customer email")
    description: Optional[str] = Field(None, description="Payment description")
    
    # Validation flags
    confirmations: Optional[int] = Field(None, description="Number of confirmations")
    required_confirmations: Optional[int] = Field(None, description="Required confirmations")
    is_confirmed: Optional[bool] = Field(None, description="Confirmation status")
    
    @field_validator('currency')
    @classmethod
    def validate_currency_format(cls, v):
        """Validate currency code format"""
        if v and not validate_currency_code(v):
            logger.warning(f"⚠️ Invalid currency code format: {v}")
        return v.upper() if v else "USD"
    
    @field_validator('order_id')
    @classmethod
    def validate_order_id(cls, v):
        """Ensure order_id is not empty"""
        if not v or not v.strip():
            raise ValueError("order_id cannot be empty")
        return v.strip()
    
    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        """Validate payment status"""
        if not v or not v.strip():
            raise ValueError("status cannot be empty")
        return v.strip().lower()
    
    @model_validator(mode='before')
    @classmethod
    def extract_nested_order_id(cls, values):
        """Extract order_id from nested structures if missing at top level"""
        if not values.get('order_id'):
            # Check meta_data for order_id
            meta_data = values.get('meta_data', {})
            if isinstance(meta_data, dict):
                order_id = meta_data.get('order_id') or meta_data.get('refId')
                if order_id:
                    values['order_id'] = order_id
                    logger.debug(f"🔍 Extracted order_id from meta_data: {order_id}")
        return values
    
    def get_safe_amount(self, field_preference: Optional[List[str]] = None) -> Optional[Decimal]:
        """
        Safely extract amount using field preference order
        
        Args:
            field_preference: Ordered list of field names to try
            
        Returns:
            Decimal amount or None
        """
        if field_preference is None:
            field_preference = [
                'base_amount', 'amount_usd', 'final_amount_usd', 
                'confirmed_amount_usd', 'total_usd', 'amount'
            ]
        
        for field_name in field_preference:
            if hasattr(self, field_name):
                raw_value = getattr(self, field_name)
                if raw_value is not None:
                    amount = safe_decimal(raw_value, field_name=field_name)
                    if amount is not None and amount > 0:
                        logger.debug(f"✅ Using amount from {field_name}: {amount}")
                        return amount
        
        logger.warning("⚠️ No valid amount found in webhook data")
        return None
    
    def get_transaction_id(self) -> Optional[str]:
        """Get transaction ID from available fields"""
        for field_name in ['txid', 'transaction_id', 'hash']:
            if hasattr(self, field_name):
                value = getattr(self, field_name)
                if value:
                    return safe_string(value, field_name=field_name)
        return None

class BlockBeeMetaData(BaseModel):
    """BlockBee meta_data nested structure"""
    order_id: Optional[str] = Field(None, description="Order ID")
    user_id: Optional[Union[str, int]] = Field(None, description="User ID") 
    callback_url: Optional[str] = Field(None, description="Callback URL")

class BlockBeeWebhookSchema(BaseWebhookSchema):
    """
    BlockBee webhook schema with comprehensive validation
    Handles BlockBee-specific field structures
    """
    
    # Required fields
    order_id: Optional[str] = Field(None, description="Order ID (may be in nested data)")
    status: Optional[str] = Field(None, description="Payment status")
    
    # BlockBee uses different field naming patterns
    value: Optional[Union[str, int, float, Decimal]] = Field(None, description="Payment value")
    value_usd: Optional[Union[str, int, float, Decimal]] = Field(None, description="USD value")
    amount: Optional[Union[str, int, float, Decimal]] = Field(None, description="Payment amount")
    amount_usd: Optional[Union[str, int, float, Decimal]] = Field(None, description="Amount in USD")
    coin_amount: Optional[Union[str, int, float, Decimal]] = Field(None, description="Cryptocurrency amount")
    
    # Crypto-specific fields
    coin: Optional[str] = Field(None, description="Cryptocurrency symbol")
    currency: Optional[str] = Field(None, description="Payment currency")
    txid: Optional[str] = Field(None, description="Transaction ID")
    
    # BlockBee specific fields
    address_in: Optional[str] = Field(None, description="Input address")
    address_out: Optional[str] = Field(None, description="Output address") 
    fee: Optional[Union[str, int, float, Decimal]] = Field(None, description="Network fee")
    confirmations: Optional[int] = Field(None, description="Number of confirmations")
    
    # Nested structures
    meta_data: Optional[Union[Dict[str, Any], BlockBeeMetaData]] = Field(None, description="Metadata")
    
    # Timestamps
    timestamp: Optional[Union[str, int, datetime]] = Field(None, description="Event timestamp")
    
    @field_validator('coin', 'currency')
    @classmethod
    def validate_crypto_currency(cls, v):
        """Validate cryptocurrency symbols"""
        if v:
            return v.upper()
        return v
    
    @model_validator(mode='before')
    @classmethod
    def extract_nested_fields(cls, values):
        """Extract fields from nested structures"""
        # Extract order_id from meta_data if needed
        if not values.get('order_id'):
            meta_data = values.get('meta_data', {})
            if isinstance(meta_data, dict) and meta_data.get('order_id'):
                values['order_id'] = meta_data['order_id']
                
        return values
    
    def get_safe_amount(self, field_preference: Optional[List[str]] = None) -> Optional[Decimal]:
        """Safely extract amount for BlockBee"""
        if field_preference is None:
            field_preference = ['value_usd', 'amount_usd', 'value', 'amount', 'coin_amount']
        
        for field_name in field_preference:
            if hasattr(self, field_name):
                raw_value = getattr(self, field_name)
                if raw_value is not None:
                    amount = safe_decimal(raw_value, field_name=field_name)
                    if amount is not None and amount > 0:
                        logger.debug(f"✅ Using BlockBee amount from {field_name}: {amount}")
                        return amount
        
        logger.warning("⚠️ No valid amount found in BlockBee webhook data")
        return None

class GenericWebhookSchema(BaseWebhookSchema):
    """
    Generic webhook schema for unknown providers
    Flexible schema that accepts various field patterns
    """
    
    # Core fields with flexible typing
    order_id: Optional[str] = Field(None, description="Order/payment ID")
    status: Optional[str] = Field(None, description="Payment status")
    amount: Optional[Union[str, int, float, Decimal]] = Field(None, description="Payment amount")
    currency: Optional[str] = Field("USD", description="Currency code")
    txid: Optional[str] = Field(None, description="Transaction ID")
    
    # Flexible nested data
    data: Optional[Dict[str, Any]] = Field(None, description="Generic data object")
    meta_data: Optional[Dict[str, Any]] = Field(None, description="Generic metadata")
    
    def get_safe_amount(self, field_preference: Optional[List[str]] = None) -> Optional[Decimal]:
        """Generic amount extraction"""
        if field_preference is None:
            field_preference = ['amount', 'value', 'total']
            
        # Try direct fields first
        for field_name in field_preference:
            if hasattr(self, field_name):
                raw_value = getattr(self, field_name)
                if raw_value is not None:
                    amount = safe_decimal(raw_value, field_name=field_name)
                    if amount is not None and amount > 0:
                        return amount
        
        # Try nested data
        for nested_field in ['data', 'meta_data']:
            nested_data = getattr(self, nested_field, {})
            if isinstance(nested_data, dict):
                for field_name in field_preference:
                    if field_name in nested_data:
                        raw_value = nested_data[field_name]
                        amount = safe_decimal(raw_value, field_name=f"{nested_field}.{field_name}")
                        if amount is not None and amount > 0:
                            return amount
        
        return None

def validate_webhook_data(data: Dict[str, Any], provider: str = "unknown") -> Union[DynoPayWebhookSchema, BlockBeeWebhookSchema, GenericWebhookSchema]:
    """
    Validate webhook data based on provider type
    
    Args:
        data: Raw webhook data dictionary
        provider: Provider name (dynopay, blockbee, etc.)
        
    Returns:
        Validated webhook schema object
        
    Raises:
        ValueError: If validation fails
    """
    provider_lower = provider.lower()
    
    try:
        if provider_lower == "dynopay":
            return DynoPayWebhookSchema(**data)
        elif provider_lower == "blockbee":
            return BlockBeeWebhookSchema(**data)
        else:
            # Try DynoPay first, then BlockBee, then Generic
            for schema_class in [DynoPayWebhookSchema, BlockBeeWebhookSchema, GenericWebhookSchema]:
                try:
                    return schema_class(**data)
                except Exception:
                    continue
            
            # If all fail, use generic with loose validation
            logger.warning(f"⚠️ Using generic webhook schema for provider: {provider}")
            return GenericWebhookSchema(**data)
            
    except Exception as e:
        logger.error(f"❌ Webhook validation failed for provider {provider}: {e}")
        logger.error(f"   Data: {data}")
        raise ValueError(f"Invalid webhook data: {e}")

# Test data for schema validation
TEST_WEBHOOK_DATA = {
    "dynopay_valid": {
        "order_id": "wallet_fund_12345",
        "status": "confirmed",
        "base_amount": "10.50",
        "currency": "USD",
        "txid": "abc123def456",
        "meta_data": {
            "user_id": 123,
            "callback_url": "https://example.com/webhook"
        }
    },
    "dynopay_with_domain_error": {
        "order_id": "wallet_fund_12345", 
        "status": "confirmed",
        "base_amount": "cxh5tph6f3.de",  # This should be rejected
        "currency": "USD"
    },
    "blockbee_valid": {
        "order_id": "payment_67890",
        "status": "confirmed",
        "value_usd": "25.75",
        "coin": "BTC",
        "txid": "def789ghi012",
        "confirmations": 3
    }
}

def run_schema_tests():
    """Run schema validation tests"""
    logger.info("🧪 Running webhook schema tests...")
    
    for test_name, test_data in TEST_WEBHOOK_DATA.items():
        try:
            if "dynopay" in test_name:
                result = validate_webhook_data(test_data, "dynopay")
                amount = result.get_safe_amount()
                if "domain_error" in test_name:
                    logger.error(f"❌ Test {test_name} should have failed but passed")
                else:
                    logger.info(f"✅ Test {test_name} passed, amount: {amount}")
            else:
                result = validate_webhook_data(test_data, "blockbee")
                amount = result.get_safe_amount()
                logger.info(f"✅ Test {test_name} passed, amount: {amount}")
                
        except Exception as e:
            if "domain_error" in test_name:
                logger.info(f"✅ Test {test_name} correctly rejected: {e}")
            else:
                logger.error(f"❌ Test {test_name} failed: {e}")

if __name__ == "__main__":
    # Run tests when executed directly
    logging.basicConfig(level=logging.INFO)
    run_schema_tests()