#!/usr/bin/env python3
"""
BlockBee Webhook Adapter
Converts BlockBee webhook data to standardized DTOs using type-safe converters
Handles all BlockBee-specific field patterns and data structures
"""

import logging
from typing import Dict, Any, Optional, List
from decimal import Decimal
from datetime import datetime

from schemas.webhook_schemas import BlockBeeWebhookSchema, validate_webhook_data
from models.payment_models import (
    PaymentIntentDTO, WalletCreditDTO, PaymentStatus, PaymentProvider, PaymentMethod,
    create_payment_intent_from_webhook, create_wallet_credit_from_payment
)
from utils.type_converters import safe_decimal, safe_string, safe_int, safe_uuid
from services.exchange_rates import ExchangeRateService

logger = logging.getLogger(__name__)

class BlockBeeAdapter:
    """
    Adapter for converting BlockBee webhook data to standardized DTOs
    Handles BlockBee-specific quirks and data formats
    """
    
    def __init__(self):
        self.exchange_service = ExchangeRateService()
        self.provider = PaymentProvider.BLOCKBEE
        
        # BlockBee status mapping (different from DynoPay)
        self.status_mapping = {
            'pending': PaymentStatus.PENDING,
            'sent': PaymentStatus.PROCESSING,
            'confirmed': PaymentStatus.CONFIRMED,
            'paid': PaymentStatus.SUCCESSFUL,
            'complete': PaymentStatus.COMPLETED,
            'failed': PaymentStatus.FAILED,
            'cancelled': PaymentStatus.CANCELLED,
            'expired': PaymentStatus.EXPIRED
        }
        
        # BlockBee field priority for amount extraction
        self.usd_amount_fields = [
            'value_usd', 'amount_usd', 'value_coin_convert', 'usd_value'
        ]
        
        self.crypto_amount_fields = [
            'value', 'amount', 'coin_amount', 'value_coin'
        ]
        
        # Common cryptocurrency mappings
        self.stablecoin_currencies = {'USDT', 'USDC', 'DAI', 'BUSD'}
        
        # BlockBee uses different field naming conventions
        self.currency_field_names = ['coin', 'currency', 'crypto']
        
    async def convert_webhook_to_payment_intent(
        self, 
        webhook_data: Dict[str, Any],
        query_params: Optional[Dict[str, List[str]]] = None,
        validate_schema: bool = True
    ) -> PaymentIntentDTO:
        """
        Convert BlockBee webhook data to PaymentIntentDTO
        
        Args:
            webhook_data: Raw webhook data from BlockBee
            query_params: Query parameters if webhook came via GET request
            validate_schema: Whether to validate with Pydantic schema first
            
        Returns:
            Validated PaymentIntentDTO
            
        Raises:
            ValueError: If conversion fails or data is invalid
        """
        try:
            logger.info(f"🔄 BLOCKBEE ADAPTER: Converting webhook data to PaymentIntentDTO")
            
            # Merge query params into webhook data for unified processing
            combined_data = dict(webhook_data)
            if query_params:
                for key, value_list in query_params.items():
                    if value_list:  # Take first value if multiple
                        combined_data[key] = value_list[0]
            
            # Step 1: Validate with Pydantic schema if requested
            if validate_schema:
                try:
                    validate_webhook_data(combined_data, "blockbee")
                    logger.debug("✅ BlockBee webhook schema validation passed")
                except Exception as e:
                    logger.warning(f"⚠️ BlockBee schema validation failed, proceeding with raw data: {e}")
            
            # Step 2: Extract core fields with safe conversion
            order_id = self._extract_order_id(combined_data)
            if not order_id:
                raise ValueError("No valid order_id found in BlockBee webhook")
            
            status = self._extract_status(combined_data, query_params)
            user_id = self._extract_user_id(combined_data)
            
            # Step 3: Extract amount with comprehensive logic
            amount_data = await self._extract_amount_data(combined_data, query_params)
            
            # Step 4: Extract transaction and payment details
            transaction_details = self._extract_transaction_details(combined_data)
            
            # Step 5: Create PaymentIntentDTO with all extracted data
            payment_intent = PaymentIntentDTO(
                order_id=order_id,
                user_id=user_id,
                amount_usd=amount_data['amount_usd'],
                status=status,
                provider=self.provider,
                provider_payment_id=transaction_details.get('provider_payment_id'),
                transaction_id=transaction_details.get('transaction_id'),
                original_amount=amount_data.get('original_amount'),
                original_currency=amount_data.get('original_currency', 'USD'),
                exchange_rate=amount_data.get('exchange_rate'),
                payment_method=PaymentMethod.CRYPTOCURRENCY,  # BlockBee is always crypto
                cryptocurrency=amount_data.get('cryptocurrency'),
                wallet_address=self._extract_wallet_address(combined_data),
                description=safe_string(combined_data.get('description')),
                customer_email=self._extract_customer_email(combined_data),
                callback_url=safe_string(combined_data.get('callback_url')),
                external_reference=safe_string(combined_data.get('external_id')),
                confirmations=safe_int(combined_data.get('confirmations'), default=0) or 0,
                required_confirmations=safe_int(combined_data.get('required_confirmations'), default=1) or 1,
                network_fee=safe_decimal(combined_data.get('fee'), field_name="network_fee"),
                metadata=self._extract_metadata(combined_data, query_params)
            )
            
            logger.info(f"✅ BLOCKBEE ADAPTER: Successfully converted webhook to PaymentIntentDTO")
            logger.info(f"   Order: {payment_intent.order_id}, Amount: {payment_intent.get_display_amount()}, Status: {payment_intent.status.value}")
            
            return payment_intent
            
        except Exception as e:
            logger.error(f"❌ BLOCKBEE ADAPTER: Failed to convert webhook data: {e}")
            logger.error(f"   Webhook data keys: {list(webhook_data.keys())}")
            if query_params:
                logger.error(f"   Query param keys: {list(query_params.keys())}")
            raise ValueError(f"BlockBee webhook conversion failed: {e}")
    
    def _extract_order_id(self, data: Dict[str, Any]) -> Optional[str]:
        """Extract order_id from BlockBee webhook data"""
        # BlockBee typically uses different field names
        for field_name in ['order_id', 'callback_url', 'custom', 'external_id']:
            value = safe_string(data.get(field_name))
            if value:
                # For callback_url, extract order_id parameter
                if field_name == 'callback_url' and 'order_id=' in value:
                    import re
                    match = re.search(r'order_id=([^&]+)', value)
                    if match:
                        order_id = match.group(1)
                        logger.debug(f"🔍 BLOCKBEE: Extracted order_id from callback_url: {order_id}")
                        return order_id
                else:
                    return value
        
        # Check meta_data if available
        meta_data = data.get('meta_data', {})
        if isinstance(meta_data, dict):
            order_id = safe_string(meta_data.get('order_id'))
            if order_id:
                logger.debug(f"🔍 BLOCKBEE: Extracted order_id from meta_data: {order_id}")
                return order_id
        
        return None
    
    def _extract_status(self, data: Dict[str, Any], query_params: Optional[Dict[str, List[str]]] = None) -> PaymentStatus:
        """Extract and normalize payment status from BlockBee data"""
        # Try direct status field
        raw_status = safe_string(data.get('status'))
        
        # BlockBee often sends status via query param 'result'
        if not raw_status and query_params:
            result_list = query_params.get('result', [])
            if result_list:
                raw_status = safe_string(result_list[0])
        
        # Try other common status field names
        if not raw_status:
            for field in ['result', 'payment_status', 'transaction_status']:
                raw_status = safe_string(data.get(field))
                if raw_status:
                    break
        
        if raw_status:
            normalized_status = raw_status.lower()
            return self.status_mapping.get(normalized_status, PaymentStatus.PENDING)
        
        return PaymentStatus.PENDING
    
    def _extract_user_id(self, data: Dict[str, Any]) -> Optional[int]:
        """Extract user_id from various locations in BlockBee webhook data"""
        # Try direct field
        user_id = safe_int(data.get('user_id'), field_name="user_id")
        if user_id:
            return user_id
        
        # Try meta_data
        meta_data = data.get('meta_data', {})
        if isinstance(meta_data, dict):
            user_id = safe_int(meta_data.get('user_id'), field_name="meta_data.user_id")
            if user_id:
                return user_id
        
        # Try callback_url parameter extraction
        callback_url = safe_string(data.get('callback_url'))
        if callback_url:
            import re
            match = re.search(r'user_id[=:](\d+)', callback_url)
            if match:
                user_id = safe_int(match.group(1), field_name="callback_url_user_id")
                if user_id:
                    logger.debug(f"🔍 BLOCKBEE: Extracted user_id from callback_url: {user_id}")
                    return user_id
        
        return None
    
    async def _extract_amount_data(self, data: Dict[str, Any], query_params: Optional[Dict[str, List[str]]] = None) -> Dict[str, Any]:
        """
        Extract amount data with currency conversion if needed
        Returns dict with amount_usd, original_amount, original_currency, exchange_rate, cryptocurrency
        """
        result = {
            'amount_usd': Decimal('0.00'),
            'original_amount': None,
            'original_currency': None,
            'exchange_rate': None,
            'cryptocurrency': None
        }
        
        # Step 1: Try USD amount fields first (no conversion needed)
        usd_amount = self._extract_usd_amount(data, query_params)
        if usd_amount and usd_amount > 0:
            result['amount_usd'] = usd_amount
            logger.debug(f"💰 BLOCKBEE: Using USD amount: {usd_amount}")
            return result
        
        # Step 2: Try cryptocurrency amounts with conversion
        crypto_data = await self._extract_crypto_amount(data, query_params)
        if crypto_data['amount'] and crypto_data['amount'] > 0:
            result['amount_usd'] = crypto_data['amount_usd']
            result['original_amount'] = crypto_data['amount']
            result['original_currency'] = crypto_data['currency']
            result['exchange_rate'] = crypto_data['exchange_rate']
            result['cryptocurrency'] = crypto_data['currency']
            
            logger.debug(f"💰 BLOCKBEE: Converted {crypto_data['amount']} {crypto_data['currency']} to ${crypto_data['amount_usd']}")
            return result
        
        logger.warning("⚠️ BLOCKBEE: No valid amount found in webhook data")
        return result
    
    def _extract_usd_amount(self, data: Dict[str, Any], query_params: Optional[Dict[str, List[str]]] = None) -> Optional[Decimal]:
        """Extract USD amount from BlockBee fields"""
        # Check direct fields
        for field in self.usd_amount_fields:
            if field in data:
                amount = safe_decimal(data[field], field_name=f"blockbee.{field}")
                if amount is not None and amount > 0:
                    return amount
        
        # Check query parameters (BlockBee often sends via GET)
        if query_params:
            for field in self.usd_amount_fields:
                if field in query_params:
                    value_list = query_params[field]
                    if value_list:
                        amount = safe_decimal(value_list[0], field_name=f"blockbee.query.{field}")
                        if amount is not None and amount > 0:
                            return amount
            
            # Special handling for BlockBee's value_coin_convert field
            if 'value_coin_convert' in query_params:
                value_list = query_params['value_coin_convert']
                if value_list:
                    amount = safe_decimal(value_list[0], field_name="blockbee.query.value_coin_convert")
                    if amount is not None and amount > 0:
                        return amount
        
        return None
    
    async def _extract_crypto_amount(self, data: Dict[str, Any], query_params: Optional[Dict[str, List[str]]] = None) -> Dict[str, Any]:
        """Extract cryptocurrency amount and convert to USD"""
        result = {
            'amount': None,
            'currency': None,
            'amount_usd': Decimal('0.00'),
            'exchange_rate': None
        }
        
        # Extract currency first
        currency = self._extract_currency(data, query_params)
        if not currency:
            return result
        
        result['currency'] = currency
        
        # Extract crypto amount
        crypto_amount = self._extract_crypto_amount_value(data, query_params)
        if not crypto_amount:
            return result
        
        result['amount'] = crypto_amount
        
        # Convert to USD
        try:
            if currency in self.stablecoin_currencies:
                # Stablecoins are 1:1 with USD
                result['amount_usd'] = crypto_amount
                result['exchange_rate'] = Decimal('1.00')
            else:
                # Get exchange rate and convert
                exchange_rate = await self.exchange_service.get_exchange_rate(currency, 'USD')
                result['exchange_rate'] = Decimal(str(exchange_rate))
                result['amount_usd'] = crypto_amount * result['exchange_rate']
                result['amount_usd'] = result['amount_usd'].quantize(Decimal('0.01'))
        except Exception as e:
            logger.error(f"❌ BLOCKBEE: Currency conversion failed for {crypto_amount} {currency}: {e}")
            
        return result
    
    def _extract_currency(self, data: Dict[str, Any], query_params: Optional[Dict[str, List[str]]] = None) -> Optional[str]:
        """Extract cryptocurrency symbol from BlockBee data"""
        # Try direct fields
        for field in self.currency_field_names:
            currency = safe_string(data.get(field))
            if currency:
                return currency.upper()
        
        # Try query parameters
        if query_params:
            for field in self.currency_field_names:
                if field in query_params:
                    value_list = query_params[field]
                    if value_list:
                        currency = safe_string(value_list[0])
                        if currency:
                            return currency.upper()
        
        return None
    
    def _extract_crypto_amount_value(self, data: Dict[str, Any], query_params: Optional[Dict[str, List[str]]] = None) -> Optional[Decimal]:
        """Extract cryptocurrency amount value"""
        # Try direct fields
        for field in self.crypto_amount_fields:
            if field in data:
                amount = safe_decimal(data[field], field_name=f"blockbee.crypto.{field}")
                if amount is not None and amount > 0:
                    return amount
        
        # Try query parameters
        if query_params:
            for field in self.crypto_amount_fields:
                if field in query_params:
                    value_list = query_params[field]
                    if value_list:
                        amount = safe_decimal(value_list[0], field_name=f"blockbee.query.crypto.{field}")
                        if amount is not None and amount > 0:
                            return amount
        
        return None
    
    def _extract_transaction_details(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract transaction-related details"""
        return {
            'provider_payment_id': safe_string(data.get('payment_id')) or safe_string(data.get('id')),
            'transaction_id': (
                safe_string(data.get('txid')) or 
                safe_string(data.get('transaction_id')) or 
                safe_string(data.get('hash'))
            )
        }
    
    def _extract_wallet_address(self, data: Dict[str, Any]) -> Optional[str]:
        """Extract wallet addresses from BlockBee data"""
        # BlockBee provides input and output addresses
        address_in = safe_string(data.get('address_in'))
        address_out = safe_string(data.get('address_out'))
        
        # Prefer address_in (sender) for tracking
        return address_in or address_out
    
    def _extract_customer_email(self, data: Dict[str, Any]) -> Optional[str]:
        """Extract customer email from various locations"""
        # Check direct field
        email = safe_string(data.get('customer_email'))
        if email:
            return email
        
        # Check meta_data
        meta_data = data.get('meta_data', {})
        if isinstance(meta_data, dict):
            email = safe_string(meta_data.get('customer_email')) or safe_string(meta_data.get('email'))
            if email:
                return email
        
        return None
    
    def _extract_metadata(self, data: Dict[str, Any], query_params: Optional[Dict[str, List[str]]] = None) -> Dict[str, Any]:
        """Extract and preserve metadata"""
        metadata = {}
        
        # Preserve original meta_data
        if 'meta_data' in data:
            metadata['blockbee_meta_data'] = data['meta_data']
        
        # Add query parameters if available
        if query_params:
            metadata['blockbee_query_params'] = {k: v for k, v in query_params.items()}
        
        # Add useful debugging information
        metadata['blockbee_original_fields'] = list(data.keys())
        metadata['adapter_version'] = "1.0"
        metadata['provider'] = "blockbee"
        
        # Preserve BlockBee-specific fields
        for field in ['address_in', 'address_out', 'confirmations_required']:
            if field in data:
                metadata[f'blockbee_{field}'] = data[field]
        
        return metadata
    
    async def create_wallet_credit_from_webhook(
        self, 
        webhook_data: Dict[str, Any],
        query_params: Optional[Dict[str, List[str]]] = None
    ) -> Optional[WalletCreditDTO]:
        """
        Create WalletCreditDTO from BlockBee webhook for wallet funding
        
        Args:
            webhook_data: Raw BlockBee webhook data
            query_params: Query parameters if webhook came via GET
            
        Returns:
            WalletCreditDTO if this is a confirmed wallet funding, None otherwise
        """
        try:
            # Convert to payment intent first
            payment_intent = await self.convert_webhook_to_payment_intent(webhook_data, query_params)
            
            # Check if this is confirmed wallet funding
            if (not payment_intent.is_confirmed() or 
                not payment_intent.order_id.startswith('wallet_fund_') or
                not payment_intent.user_id):
                return None
            
            # Create wallet credit DTO
            wallet_credit = create_wallet_credit_from_payment(
                payment_intent=payment_intent,
                transaction_id=payment_intent.transaction_id
            )
            
            logger.info(f"✅ BLOCKBEE: Created wallet credit for user {wallet_credit.user_id}: {wallet_credit.get_display_amount()}")
            return wallet_credit
            
        except Exception as e:
            logger.error(f"❌ BLOCKBEE: Failed to create wallet credit from webhook: {e}")
            return None

# Convenience function for external use
async def convert_blockbee_webhook(
    webhook_data: Dict[str, Any], 
    query_params: Optional[Dict[str, List[str]]] = None
) -> PaymentIntentDTO:
    """
    Convenience function to convert BlockBee webhook data to PaymentIntentDTO
    
    Args:
        webhook_data: Raw BlockBee webhook data
        query_params: Query parameters if webhook came via GET
        
    Returns:
        Validated PaymentIntentDTO
    """
    adapter = BlockBeeAdapter()
    return await adapter.convert_webhook_to_payment_intent(webhook_data, query_params)

if __name__ == "__main__":
    # Test the adapter with sample data
    import asyncio
    
    async def test_adapter():
        logging.basicConfig(level=logging.INFO)
        
        # Test data that should work (BlockBee style)
        test_data = {
            "order_id": "wallet_fund_67890",
            "status": "confirmed",
            "value_usd": "25.75",
            "coin": "BTC",
            "txid": "def789ghi012",
            "confirmations": 3,
            "meta_data": {
                "user_id": 456
            }
        }
        
        try:
            payment = await convert_blockbee_webhook(test_data)
            logger.info(f"✅ Test passed: {payment.order_id}, amount: {payment.get_display_amount()}")
        except Exception as e:
            logger.error(f"❌ Test failed: {e}")
    
    asyncio.run(test_adapter())