#!/usr/bin/env python3
"""
Payment Timeout Configuration Module
Manages cryptocurrency-specific timeout periods for payment addresses
Supports configurable timeouts with safety checks and grace periods
"""

import os
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class CryptocurrencyCategory(Enum):
    """Categories for cryptocurrency timeout behavior"""
    BITCOIN = "bitcoin"           # Bitcoin and Bitcoin-based currencies (longer confirmation times)
    ETHEREUM = "ethereum"         # Ethereum and ERC-20 tokens (medium confirmation times)  
    STABLECOIN = "stablecoin"     # Stablecoins (faster but need time for verification)
    FAST_CRYPTO = "fast_crypto"   # Fast cryptocurrencies like Litecoin, Dogecoin
    DEFAULT = "default"           # Default category for unknown currencies

@dataclass
class TimeoutConfiguration:
    """Configuration for payment timeouts"""
    # Base timeout periods (in minutes)
    bitcoin_timeout_minutes: int = 60        # Bitcoin: 1 hour (longer due to confirmation times)
    ethereum_timeout_minutes: int = 45       # Ethereum: 45 minutes
    stablecoin_timeout_minutes: int = 30     # Stablecoins: 30 minutes
    fast_crypto_timeout_minutes: int = 30    # Fast cryptos: 30 minutes  
    default_timeout_minutes: int = 30        # Default: 30 minutes
    
    # Safety and grace periods
    minimum_timeout_minutes: int = 10        # Never expire before 10 minutes
    grace_period_minutes: int = 5            # 5-minute grace period after expiration
    
    # Provider-specific adjustments (in minutes)
    dynopay_buffer_minutes: int = 5          # Extra buffer for DynoPay
    blockbee_buffer_minutes: int = 3         # Extra buffer for BlockBee
    
    @classmethod
    def from_env(cls) -> 'TimeoutConfiguration':
        """Load timeout configuration from environment variables"""
        return cls(
            bitcoin_timeout_minutes=int(os.getenv('PAYMENT_TIMEOUT_BITCOIN_MINUTES', '60')),
            ethereum_timeout_minutes=int(os.getenv('PAYMENT_TIMEOUT_ETHEREUM_MINUTES', '45')),
            stablecoin_timeout_minutes=int(os.getenv('PAYMENT_TIMEOUT_STABLECOIN_MINUTES', '30')),
            fast_crypto_timeout_minutes=int(os.getenv('PAYMENT_TIMEOUT_FAST_CRYPTO_MINUTES', '30')),
            default_timeout_minutes=int(os.getenv('PAYMENT_TIMEOUT_DEFAULT_MINUTES', '30')),
            minimum_timeout_minutes=int(os.getenv('PAYMENT_MINIMUM_TIMEOUT_MINUTES', '10')),
            grace_period_minutes=int(os.getenv('PAYMENT_GRACE_PERIOD_MINUTES', '5')),
            dynopay_buffer_minutes=int(os.getenv('PAYMENT_DYNOPAY_BUFFER_MINUTES', '5')),
            blockbee_buffer_minutes=int(os.getenv('PAYMENT_BLOCKBEE_BUFFER_MINUTES', '3'))
        )
    
    def validate(self) -> bool:
        """Validate timeout configuration"""
        # Ensure minimum timeout is reasonable
        if self.minimum_timeout_minutes < 5:
            logger.warning("⚠️ TIMEOUT CONFIG: Minimum timeout is less than 5 minutes, adjusting to 5")
            self.minimum_timeout_minutes = 5
        
        # Ensure all timeouts are at least the minimum
        timeouts = [
            self.bitcoin_timeout_minutes, self.ethereum_timeout_minutes,
            self.stablecoin_timeout_minutes, self.fast_crypto_timeout_minutes,
            self.default_timeout_minutes
        ]
        
        for timeout in timeouts:
            if timeout < self.minimum_timeout_minutes:
                logger.warning(f"⚠️ TIMEOUT CONFIG: Found timeout ({timeout}min) less than minimum ({self.minimum_timeout_minutes}min)")
                return False
        
        logger.info("✅ TIMEOUT CONFIG: Validation passed")
        return True

class PaymentTimeoutManager:
    """
    Manages payment timeout logic for different cryptocurrencies
    Provides timeout calculation, categorization, and expiration logic
    """
    
    def __init__(self, config: Optional[TimeoutConfiguration] = None):
        self.config = config or TimeoutConfiguration.from_env()
        self.config.validate()
        
        # Cryptocurrency categorization mapping
        self.crypto_categories = {
            # Bitcoin family
            'btc': CryptocurrencyCategory.BITCOIN,
            'bitcoin': CryptocurrencyCategory.BITCOIN,
            'bch': CryptocurrencyCategory.BITCOIN,
            
            # Ethereum family
            'eth': CryptocurrencyCategory.ETHEREUM,
            'ethereum': CryptocurrencyCategory.ETHEREUM,
            
            # Stablecoins
            'usdt': CryptocurrencyCategory.STABLECOIN,
            'usdt_trc20': CryptocurrencyCategory.STABLECOIN,
            'usdt_erc20': CryptocurrencyCategory.STABLECOIN,
            'usdc': CryptocurrencyCategory.STABLECOIN,
            'dai': CryptocurrencyCategory.STABLECOIN,
            'busd': CryptocurrencyCategory.STABLECOIN,
            
            # Fast cryptocurrencies
            'ltc': CryptocurrencyCategory.FAST_CRYPTO,
            'litecoin': CryptocurrencyCategory.FAST_CRYPTO,
            'doge': CryptocurrencyCategory.FAST_CRYPTO,
            'dogecoin': CryptocurrencyCategory.FAST_CRYPTO,
            'xrp': CryptocurrencyCategory.FAST_CRYPTO,
            'xlm': CryptocurrencyCategory.FAST_CRYPTO,
        }
        
        logger.info("🕐 TIMEOUT MANAGER: Initialized with crypto-specific timeout periods")
        self._log_configuration()
    
    def _log_configuration(self):
        """Log current timeout configuration for transparency"""
        logger.info("📋 TIMEOUT CONFIGURATION:")
        logger.info(f"   • Bitcoin timeout: {self.config.bitcoin_timeout_minutes} minutes")
        logger.info(f"   • Ethereum timeout: {self.config.ethereum_timeout_minutes} minutes")
        logger.info(f"   • Stablecoin timeout: {self.config.stablecoin_timeout_minutes} minutes")
        logger.info(f"   • Fast crypto timeout: {self.config.fast_crypto_timeout_minutes} minutes")
        logger.info(f"   • Default timeout: {self.config.default_timeout_minutes} minutes")
        logger.info(f"   • Minimum timeout: {self.config.minimum_timeout_minutes} minutes")
        logger.info(f"   • Grace period: {self.config.grace_period_minutes} minutes")
    
    def get_cryptocurrency_category(self, currency: str) -> CryptocurrencyCategory:
        """
        Determine the category of a cryptocurrency for timeout purposes
        
        Args:
            currency: Cryptocurrency code (e.g., 'btc', 'eth', 'usdt')
            
        Returns:
            CryptocurrencyCategory enum value
        """
        if not currency:
            return CryptocurrencyCategory.DEFAULT
        
        currency_lower = currency.lower().strip()
        category = self.crypto_categories.get(currency_lower, CryptocurrencyCategory.DEFAULT)
        
        if category == CryptocurrencyCategory.DEFAULT:
            logger.debug(f"🔍 TIMEOUT: Unknown cryptocurrency '{currency}', using default timeout")
        
        return category
    
    def calculate_timeout_minutes(
        self, 
        currency: str, 
        provider: Optional[str] = None,
        payment_amount_usd: Optional[float] = None
    ) -> int:
        """
        Calculate timeout period in minutes for a specific cryptocurrency and context
        
        Args:
            currency: Cryptocurrency code
            provider: Payment provider ('dynopay', 'blockbee', etc.)
            payment_amount_usd: Payment amount in USD (for amount-based adjustments)
            
        Returns:
            Timeout period in minutes
        """
        # Get base timeout from cryptocurrency category
        category = self.get_cryptocurrency_category(currency)
        
        if category == CryptocurrencyCategory.BITCOIN:
            base_timeout = self.config.bitcoin_timeout_minutes
        elif category == CryptocurrencyCategory.ETHEREUM:
            base_timeout = self.config.ethereum_timeout_minutes
        elif category == CryptocurrencyCategory.STABLECOIN:
            base_timeout = self.config.stablecoin_timeout_minutes
        elif category == CryptocurrencyCategory.FAST_CRYPTO:
            base_timeout = self.config.fast_crypto_timeout_minutes
        else:
            base_timeout = self.config.default_timeout_minutes
        
        # Apply provider-specific buffer
        if provider:
            provider_lower = provider.lower()
            if provider_lower == 'dynopay':
                base_timeout += self.config.dynopay_buffer_minutes
            elif provider_lower == 'blockbee':
                base_timeout += self.config.blockbee_buffer_minutes
        
        # Ensure minimum timeout
        final_timeout = max(base_timeout, self.config.minimum_timeout_minutes)
        
        logger.debug(f"💰 TIMEOUT: {currency.upper()} ({category.value}) = {final_timeout} minutes (provider: {provider})")
        
        return final_timeout
    
    def calculate_expires_at(
        self, 
        currency: str, 
        provider: Optional[str] = None,
        payment_amount_usd: Optional[float] = None,
        created_at: Optional[datetime] = None
    ) -> datetime:
        """
        Calculate the expiration timestamp for a payment intent
        
        Args:
            currency: Cryptocurrency code
            provider: Payment provider name
            payment_amount_usd: Payment amount in USD
            created_at: Creation timestamp (defaults to now)
            
        Returns:
            Expiration datetime in UTC
        """
        if created_at is None:
            created_at = datetime.utcnow()
        
        timeout_minutes = self.calculate_timeout_minutes(currency, provider, payment_amount_usd)
        expires_at = created_at + timedelta(minutes=timeout_minutes)
        
        logger.debug(f"⏰ EXPIRATION: Payment for {currency.upper()} expires at {expires_at} UTC ({timeout_minutes} minutes)")
        
        return expires_at
    
    def is_payment_expired(
        self, 
        expires_at: datetime, 
        include_grace_period: bool = True,
        current_time: Optional[datetime] = None
    ) -> Tuple[bool, str]:
        """
        Check if a payment has expired, optionally including grace period
        
        Args:
            expires_at: Payment expiration timestamp
            include_grace_period: Whether to include grace period
            current_time: Current time (defaults to now)
            
        Returns:
            Tuple of (is_expired, reason)
        """
        if current_time is None:
            current_time = datetime.utcnow()
        
        # Check hard expiration
        if current_time > expires_at:
            if include_grace_period:
                grace_deadline = expires_at + timedelta(minutes=self.config.grace_period_minutes)
                if current_time > grace_deadline:
                    return True, f"expired {(current_time - grace_deadline).total_seconds() / 60:.1f} minutes ago (after grace period)"
                else:
                    return False, f"within grace period (expires at {grace_deadline})"
            else:
                return True, f"expired {(current_time - expires_at).total_seconds() / 60:.1f} minutes ago"
        
        return False, f"expires in {(expires_at - current_time).total_seconds() / 60:.1f} minutes"
    
    def is_recently_created(
        self, 
        created_at: datetime, 
        current_time: Optional[datetime] = None
    ) -> bool:
        """
        Check if a payment was created recently (within minimum timeout period)
        This prevents premature expiration of new payments
        
        Args:
            created_at: Payment creation timestamp
            current_time: Current time (defaults to now)
            
        Returns:
            True if payment is too recent to expire
        """
        if current_time is None:
            current_time = datetime.utcnow()
        
        minimum_age = timedelta(minutes=self.config.minimum_timeout_minutes)
        age = current_time - created_at
        
        is_recent = age < minimum_age
        if is_recent:
            logger.debug(f"🛡️ SAFETY: Payment created {age.total_seconds() / 60:.1f} minutes ago, too recent to expire")
        
        return is_recent
    
    def get_timeout_summary(self) -> Dict[str, int]:
        """
        Get a summary of all timeout configurations
        
        Returns:
            Dictionary mapping categories to timeout minutes
        """
        return {
            'bitcoin': self.config.bitcoin_timeout_minutes,
            'ethereum': self.config.ethereum_timeout_minutes,
            'stablecoin': self.config.stablecoin_timeout_minutes,
            'fast_crypto': self.config.fast_crypto_timeout_minutes,
            'default': self.config.default_timeout_minutes,
            'minimum': self.config.minimum_timeout_minutes,
            'grace_period': self.config.grace_period_minutes
        }

# Global timeout manager instance
_timeout_manager: Optional[PaymentTimeoutManager] = None

def get_timeout_manager() -> PaymentTimeoutManager:
    """Get global timeout manager instance (singleton)"""
    global _timeout_manager
    if _timeout_manager is None:
        _timeout_manager = PaymentTimeoutManager()
    return _timeout_manager

def calculate_payment_expires_at(
    currency: str, 
    provider: Optional[str] = None,
    payment_amount_usd: Optional[float] = None,
    created_at: Optional[datetime] = None
) -> datetime:
    """
    Convenience function to calculate payment expiration time
    
    Args:
        currency: Cryptocurrency code
        provider: Payment provider name
        payment_amount_usd: Payment amount in USD  
        created_at: Creation timestamp (defaults to now)
        
    Returns:
        Expiration datetime in UTC
    """
    manager = get_timeout_manager()
    return manager.calculate_expires_at(currency, provider, payment_amount_usd, created_at)

def is_payment_expired_now(
    expires_at: datetime, 
    include_grace_period: bool = True
) -> Tuple[bool, str]:
    """
    Convenience function to check if payment is expired now
    
    Args:
        expires_at: Payment expiration timestamp
        include_grace_period: Whether to include grace period
        
    Returns:
        Tuple of (is_expired, reason)
    """
    manager = get_timeout_manager()
    return manager.is_payment_expired(expires_at, include_grace_period)

# Export public interface
__all__ = [
    'PaymentTimeoutManager',
    'TimeoutConfiguration', 
    'CryptocurrencyCategory',
    'get_timeout_manager',
    'calculate_payment_expires_at',
    'is_payment_expired_now'
]