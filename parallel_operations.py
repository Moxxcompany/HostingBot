"""
Parallel Operations Module for High-Performance Processing
Implements asyncio.gather() patterns for 20+ ops/sec target
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Callable, Awaitable
from concurrent.futures import ThreadPoolExecutor
import time

logger = logging.getLogger(__name__)

class ParallelProcessor:
    """
    High-performance parallel operation processor
    Optimized for concurrent domain registration, DNS, and payment operations
    """
    
    def __init__(self, max_concurrent_operations: int = 10):
        self.max_concurrent = max_concurrent_operations
        self.semaphore = asyncio.Semaphore(max_concurrent_operations)
        self.operation_count = 0
        self.success_count = 0
        self.error_count = 0
        
        logger.info(f"✅ Parallel processor initialized (max concurrent: {max_concurrent_operations})")
    
    async def execute_parallel_operations(
        self, 
        operations: List[Dict[str, Any]], 
        operation_handler: Callable[[Dict[str, Any]], Awaitable[Any]]
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple operations in parallel with concurrency control
        
        Args:
            operations: List of operation configs
            operation_handler: Async function to handle each operation
        
        Returns:
            List of results with success/error status
        """
        if not operations:
            return []
        
        logger.info(f"🚀 Starting parallel execution of {len(operations)} operations")
        start_time = time.time()
        
        # Create semaphore-controlled tasks
        async def controlled_operation(operation_config: Dict[str, Any]) -> Dict[str, Any]:
            async with self.semaphore:
                operation_id = operation_config.get('id', f"op_{self.operation_count}")
                self.operation_count += 1
                
                try:
                    result = await operation_handler(operation_config)
                    self.success_count += 1
                    return {
                        'id': operation_id,
                        'success': True,
                        'result': result,
                        'operation': operation_config
                    }
                except Exception as e:
                    self.error_count += 1
                    logger.warning(f"⚠️ Operation {operation_id} failed: {str(e)}")
                    return {
                        'id': operation_id,
                        'success': False,
                        'error': str(e),
                        'error_type': type(e).__name__,
                        'operation': operation_config
                    }
        
        # Execute all operations in parallel
        tasks = [controlled_operation(op) for op in operations]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        
        # Calculate performance metrics
        total_time = time.time() - start_time
        ops_per_second = len(operations) / total_time if total_time > 0 else 0
        success_rate = (self.success_count / len(operations) * 100) if operations else 0
        
        logger.info(f"✅ Parallel execution completed:")
        logger.info(f"   • Operations: {len(operations)}")
        logger.info(f"   • Success rate: {success_rate:.1f}%")
        logger.info(f"   • Total time: {total_time:.2f}s")
        logger.info(f"   • Throughput: {ops_per_second:.1f} ops/sec")
        
        return results
    
    async def execute_domain_operations_batch(
        self, 
        domain_operations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Execute domain-related operations in parallel (availability checks, registrations)
        
        Args:
            domain_operations: List of domain operation configs
        
        Returns:
            List of results for each domain operation
        """
        
        async def domain_operation_handler(operation_config: Dict[str, Any]) -> Any:
            operation_type = operation_config.get('type')
            domain_name = operation_config.get('domain')
            
            if operation_type == 'availability_check':
                from services.openprovider import OpenProviderService
                service = OpenProviderService()
                if not domain_name or not isinstance(domain_name, str):
                    raise ValueError(f"Invalid domain name for availability check: {domain_name}")
                return await service.check_domain_availability(domain_name)
            
            elif operation_type == 'pricing_check':
                from services.openprovider import OpenProviderService
                service = OpenProviderService()
                if not domain_name or not isinstance(domain_name, str):
                    raise ValueError(f"Invalid domain name for pricing check: {domain_name}")
                return await service.get_domain_pricing(domain_name)
            
            elif operation_type == 'dns_setup':
                from services.cloudflare import CloudflareService
                service = CloudflareService()
                if not domain_name or not isinstance(domain_name, str):
                    raise ValueError(f"Invalid domain name for DNS setup: {domain_name}")
                zone_data = operation_config.get('zone_data', {})
                return await service.create_zone(domain_name, **zone_data)
            
            else:
                raise ValueError(f"Unknown domain operation type: {operation_type}")
        
        return await self.execute_parallel_operations(domain_operations, domain_operation_handler)
    
    async def execute_payment_operations_batch(
        self, 
        payment_operations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Execute payment-related operations in parallel
        
        Args:
            payment_operations: List of payment operation configs
        
        Returns:
            List of results for each payment operation
        """
        
        async def payment_operation_handler(operation_config: Dict[str, Any]) -> Any:
            operation_type = operation_config.get('type')
            
            if operation_type == 'create_address':
                from services.payment_provider import create_payment_address
                currency = operation_config.get('currency')
                order_id = operation_config.get('order_id')
                value = operation_config.get('value')
                user_id = operation_config.get('user_id')
                
                # Validate parameters
                if not currency or not isinstance(currency, str):
                    raise ValueError(f"Invalid currency for payment address: {currency}")
                if not order_id or not isinstance(order_id, str):
                    raise ValueError(f"Invalid order_id for payment address: {order_id}")
                if value is None or not isinstance(value, (int, float)):
                    raise ValueError(f"Invalid value for payment address: {value}")
                if user_id is None or not isinstance(user_id, int):
                    raise ValueError(f"Invalid user_id for payment address: {user_id}")
                
                return await create_payment_address(currency, order_id, float(value), user_id)
            
            elif operation_type == 'check_status':
                from services.payment_provider import check_payment_status
                currency = operation_config.get('currency')
                address = operation_config.get('address')
                
                # Validate parameters
                if not currency or not isinstance(currency, str):
                    raise ValueError(f"Invalid currency for payment status check: {currency}")
                if not address or not isinstance(address, str):
                    raise ValueError(f"Invalid payment address: {address}")
                
                return await check_payment_status(currency, address)
            
            else:
                raise ValueError(f"Unknown payment operation type: {operation_type}")
        
        return await self.execute_parallel_operations(payment_operations, payment_operation_handler)
    
    async def execute_hosting_operations_batch(
        self, 
        hosting_operations: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Execute hosting-related operations in parallel
        
        Args:
            hosting_operations: List of hosting operation configs
        
        Returns:
            List of results for each hosting operation
        """
        
        async def hosting_operation_handler(operation_config: Dict[str, Any]) -> Any:
            operation_type = operation_config.get('type')
            
            if operation_type == 'create_account':
                from services.cpanel import CPanelService
                service = CPanelService()
                domain = operation_config.get('domain')
                email = operation_config.get('email')
                plan = operation_config.get('plan', 'default')
                
                # Validate parameters
                if not domain or not isinstance(domain, str):
                    raise ValueError(f"Invalid domain for hosting account: {domain}")
                if not email or not isinstance(email, str):
                    raise ValueError(f"Invalid email for hosting account: {email}")
                if not plan or not isinstance(plan, str):
                    raise ValueError(f"Invalid plan for hosting account: {plan}")
                
                return await service.create_hosting_account(domain, plan, email)
            
            elif operation_type == 'test_connection':
                from services.cpanel import CPanelService
                service = CPanelService()
                return await service.test_connection()
            
            else:
                raise ValueError(f"Unknown hosting operation type: {operation_type}")
        
        return await self.execute_parallel_operations(hosting_operations, hosting_operation_handler)
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for this processor"""
        total_operations = self.success_count + self.error_count
        success_rate = (self.success_count / total_operations * 100) if total_operations > 0 else 0
        
        return {
            'total_operations': total_operations,
            'successful_operations': self.success_count,
            'failed_operations': self.error_count,
            'success_rate_percent': success_rate,
            'max_concurrent_operations': self.max_concurrent
        }

# Global parallel processor instance
_parallel_processor = ParallelProcessor(max_concurrent_operations=15)

# Convenience functions for external use
async def execute_parallel_domain_operations(operations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Execute domain operations in parallel"""
    return await _parallel_processor.execute_domain_operations_batch(operations)

async def execute_parallel_payment_operations(operations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Execute payment operations in parallel"""
    return await _parallel_processor.execute_payment_operations_batch(operations)

async def execute_parallel_hosting_operations(operations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Execute hosting operations in parallel"""
    return await _parallel_processor.execute_hosting_operations_batch(operations)

def get_parallel_processor_stats() -> Dict[str, Any]:
    """Get parallel processor performance statistics"""
    return _parallel_processor.get_performance_stats()

logger.info("✅ Parallel operations module loaded - ready for high-throughput processing")