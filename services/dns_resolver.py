"""
DNS Resolution Service
Handles DNS queries with proper fallback mechanisms and error handling.
"""

import logging
import asyncio
import socket
from typing import List, Optional, Tuple
import subprocess

logger = logging.getLogger(__name__)

class DNSResolver:
    """Professional DNS resolution service with multiple fallback methods"""
    
    def __init__(self):
        self.timeout = 5
        self.max_retries = 2
        
    async def get_nameservers(self, domain_name: str) -> List[str]:
        """
        Get nameservers for a domain using multiple fallback methods
        
        Args:
            domain_name: Domain to query nameservers for
            
        Returns:
            List of nameserver hostnames
        """
        if not domain_name:
            return []
            
        # Method 1: Try dnspython with external DNS servers
        nameservers = await self._get_nameservers_dnspython(domain_name)
        if nameservers:
            return nameservers
            
        # Method 2: Try system dig command
        nameservers = await self._get_nameservers_dig(domain_name)
        if nameservers:
            return nameservers
            
        # Method 3: Try nslookup as last resort
        nameservers = await self._get_nameservers_nslookup(domain_name)
        if nameservers:
            return nameservers
            
        logger.warning(f"All DNS resolution methods failed for {domain_name}")
        return []
    
    async def _get_nameservers_dnspython(self, domain_name: str) -> List[str]:
        """Get nameservers using dnspython with external DNS servers"""
        try:
            import dns.resolver
            
            # Configure resolver to use reliable external DNS servers
            resolver = dns.resolver.Resolver()
            resolver.nameservers = [
                '8.8.8.8',      # Google DNS
                '1.1.1.1',      # Cloudflare DNS
                '208.67.222.222' # OpenDNS
            ]
            resolver.timeout = self.timeout
            resolver.lifetime = self.timeout
            
            loop = asyncio.get_event_loop()
            
            def _query():
                try:
                    answers = resolver.resolve(domain_name, 'NS')
                    return [str(answer).rstrip('.') for answer in answers]
                except dns.resolver.NXDOMAIN:
                    logger.debug(f"Domain {domain_name} does not exist (NXDOMAIN)")
                    return []
                except dns.resolver.NoAnswer:
                    logger.debug(f"No NS records found for {domain_name}")
                    return []
                except Exception as e:
                    logger.debug(f"DNS resolver error for {domain_name}: {e}")
                    return []
            
            nameservers = await asyncio.wait_for(
                loop.run_in_executor(None, _query),
                timeout=self.timeout
            )
            
            if nameservers:
                logger.debug(f"✅ dnspython resolved {len(nameservers)} nameservers for {domain_name}")
                return nameservers
                
        except ImportError:
            logger.debug("dnspython not available, trying alternative methods")
        except asyncio.TimeoutError:
            logger.debug(f"dnspython timeout for {domain_name}")
        except Exception as e:
            logger.debug(f"dnspython failed for {domain_name}: {e}")
            
        return []
    
    async def _get_nameservers_dig(self, domain_name: str) -> List[str]:
        """Get nameservers using system dig command"""
        try:
            loop = asyncio.get_event_loop()
            
            def _dig_query():
                try:
                    # Use reliable external DNS server
                    result = subprocess.run(
                        ['dig', '+short', f'@8.8.8.8', domain_name, 'NS'],
                        capture_output=True,
                        text=True,
                        timeout=self.timeout
                    )
                    
                    if result.returncode == 0 and result.stdout.strip():
                        nameservers = []
                        for line in result.stdout.strip().split('\n'):
                            ns = line.strip().rstrip('.')
                            if ns and self._is_valid_nameserver(ns):
                                nameservers.append(ns)
                        return nameservers
                except subprocess.TimeoutExpired:
                    logger.debug(f"dig timeout for {domain_name}")
                except FileNotFoundError:
                    logger.debug("dig command not available")
                except Exception as e:
                    logger.debug(f"dig error for {domain_name}: {e}")
                return []
            
            nameservers = await asyncio.wait_for(
                loop.run_in_executor(None, _dig_query),
                timeout=self.timeout + 1
            )
            
            if nameservers:
                logger.debug(f"✅ dig resolved {len(nameservers)} nameservers for {domain_name}")
                return nameservers
                
        except asyncio.TimeoutError:
            logger.debug(f"dig timeout for {domain_name}")
        except Exception as e:
            logger.debug(f"dig failed for {domain_name}: {e}")
            
        return []
    
    async def _get_nameservers_nslookup(self, domain_name: str) -> List[str]:
        """Get nameservers using nslookup as final fallback"""
        try:
            loop = asyncio.get_event_loop()
            
            def _nslookup_query():
                try:
                    result = subprocess.run(
                        ['nslookup', '-type=NS', domain_name, '8.8.8.8'],
                        capture_output=True,
                        text=True,
                        timeout=self.timeout
                    )
                    
                    if result.returncode == 0:
                        nameservers = []
                        for line in result.stdout.split('\n'):
                            if 'nameserver' in line.lower() and '=' in line:
                                ns = line.split('=')[-1].strip().rstrip('.')
                                if ns and self._is_valid_nameserver(ns):
                                    nameservers.append(ns)
                        return nameservers
                except subprocess.TimeoutExpired:
                    logger.debug(f"nslookup timeout for {domain_name}")
                except FileNotFoundError:
                    logger.debug("nslookup command not available")
                except Exception as e:
                    logger.debug(f"nslookup error for {domain_name}: {e}")
                return []
            
            nameservers = await asyncio.wait_for(
                loop.run_in_executor(None, _nslookup_query),
                timeout=self.timeout + 1
            )
            
            if nameservers:
                logger.debug(f"✅ nslookup resolved {len(nameservers)} nameservers for {domain_name}")
                return nameservers
                
        except asyncio.TimeoutError:
            logger.debug(f"nslookup timeout for {domain_name}")
        except Exception as e:
            logger.debug(f"nslookup failed for {domain_name}: {e}")
            
        return []
    
    def _is_valid_nameserver(self, nameserver: str) -> bool:
        """Validate if a string is a valid nameserver hostname"""
        if not nameserver or len(nameserver) > 253:
            return False
        
        # Basic domain name validation
        import re
        pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, nameserver.strip().lower()))

# Global DNS resolver instance
dns_resolver = DNSResolver()