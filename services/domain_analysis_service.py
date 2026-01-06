"""
Domain Analysis Service - Phase 1 Foundation
Provides intelligent domain analysis and recommendation for linking strategies

This service handles:
- DNS lookup and nameserver analysis
- Domain ownership conflict detection
- Registrar identification (where possible)
- Current hosting provider detection
- Smart recommendation for optimal linking strategy
"""

import asyncio
import logging
import dns.resolver
import dns.exception
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from services.domain_linking_config import HOSTBAY_NAMESERVERS

logger = logging.getLogger(__name__)

# Thread pool for non-blocking DNS operations
_dns_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="dns_worker")


class DomainAnalysisService:
    """
    Service for analyzing domains and providing linking recommendations.
    
    Phase 1: Basic DNS analysis and structure
    Phase 2: Will add advanced analysis features
    """
    
    def __init__(self):
        self.hostbay_nameservers = HOSTBAY_NAMESERVERS
    
    async def analyze_domain(self, domain_name: str) -> Dict[str, Any]:
        """
        Analyze a domain and provide recommendations for linking strategy.
        
        Args:
            domain_name: Domain to analyze (e.g., "example.com")
            
        Returns:
            Dict containing analysis results and recommendations
        """
        logger.info(f"🔍 DOMAIN ANALYSIS: Starting analysis for {domain_name}")
        
        try:
            # Phase 1: Basic DNS Analysis
            dns_info = await self._analyze_dns(domain_name)
            
            # Phase 1: Basic ownership analysis
            ownership_info = await self._analyze_ownership(domain_name)
            
            # Phase 1: Basic recommendation
            recommendation = await self._generate_basic_recommendation(
                domain_name, dns_info, ownership_info
            )
            
            analysis_result = {
                'success': True,
                'domain_name': domain_name,
                'dns_info': dns_info,
                'ownership_info': ownership_info,
                'recommendation': recommendation,
                'analysis_timestamp': datetime.utcnow().isoformat(),
                'phase': 'phase_1_basic'
            }
            
            logger.info(f"✅ DOMAIN ANALYSIS: Completed for {domain_name}")
            return analysis_result
            
        except Exception as e:
            logger.error(f"💥 DOMAIN ANALYSIS: Failed for {domain_name}: {e}")
            return {
                'success': False,
                'domain_name': domain_name,
                'error': str(e),
                'analysis_timestamp': datetime.utcnow().isoformat()
            }
    
    async def _analyze_dns(self, domain_name: str) -> Dict[str, Any]:
        """Analyze DNS configuration for the domain (non-blocking)"""
        dns_info = {
            'nameservers': [],
            'a_records': [],
            'mx_records': [],
            'dnssec_enabled': False,
            'cloudflare_proxy': False,
            'analysis_status': 'unknown'
        }
        
        def _dns_lookup():
            """Synchronous DNS lookup to run in thread pool"""
            try:
                # Get nameservers
                ns_response = dns.resolver.resolve(domain_name, 'NS')
                dns_info['nameservers'] = [str(ns).rstrip('.') for ns in ns_response]
                
                # Get A records
                try:
                    a_response = dns.resolver.resolve(domain_name, 'A')
                    dns_info['a_records'] = [str(a) for a in a_response]
                except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                    dns_info['a_records'] = []
                
                # Get MX records
                try:
                    mx_response = dns.resolver.resolve(domain_name, 'MX')
                    dns_info['mx_records'] = [{'priority': mx.preference, 'server': str(mx.exchange).rstrip('.')} for mx in mx_response]
                except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                    dns_info['mx_records'] = []
                
                # Check for Cloudflare (basic detection)
                cloudflare_ns = ['cloudflare.com', 'cloudflare.net']
                dns_info['cloudflare_proxy'] = any(
                    any(cf in ns for cf in cloudflare_ns) 
                    for ns in dns_info['nameservers']
                )
                
                dns_info['analysis_status'] = 'success'
                
            except Exception as e:
                logger.warning(f"⚠️ DNS analysis partial failure for {domain_name}: {e}")
                dns_info['analysis_status'] = 'partial_failure'
                dns_info['error'] = str(e)
            
            return dns_info
        
        # Run DNS lookup in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(_dns_executor, _dns_lookup)
        
        logger.debug(f"📊 DNS analysis complete for {domain_name}: {len(result['nameservers'])} NS, {len(result['a_records'])} A records")
        return result
    
    async def _analyze_ownership(self, domain_name: str) -> Dict[str, Any]:
        """Analyze domain ownership and hosting status"""
        ownership_info = {
            'ownership_status': 'unknown',
            'hosting_provider': 'unknown',
            'registrar': 'unknown',
            'conflict_risk': 'low',
            'verification_method': 'dns_txt'
        }
        
        # Phase 1: Basic implementation
        # Phase 2 will add advanced ownership detection
        
        try:
            # For Phase 1, we'll do basic checks
            ownership_info['ownership_status'] = 'needs_verification'
            ownership_info['conflict_risk'] = 'medium'  # Default to medium for safety
            
            logger.debug(f"📋 Ownership analysis complete for {domain_name}")
            
        except Exception as e:
            logger.warning(f"⚠️ Ownership analysis failed for {domain_name}: {e}")
            ownership_info['error'] = str(e)
        
        return ownership_info
    
    async def _generate_basic_recommendation(
        self, 
        domain_name: str, 
        dns_info: Dict[str, Any], 
        ownership_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate basic linking strategy recommendation"""
        
        recommendation = {
            'strategy': 'smart_mode',  # Default for Phase 1
            'confidence': 'medium',
            'estimated_time': '5-15 minutes',
            'steps_required': [],
            'warnings': [],
            'benefits': []
        }
        
        # Check if already using HostBay nameservers
        current_ns = dns_info.get('nameservers', [])
        using_hostbay_ns = any(
            any(hb_ns in ns for hb_ns in self.hostbay_nameservers)
            for ns in current_ns
        )
        
        if using_hostbay_ns:
            recommendation.update({
                'strategy': 'already_linked',
                'confidence': 'high',
                'message': 'Domain already appears to be using HostBay nameservers'
            })
        else:
            # Standard smart mode recommendation
            recommendation['steps_required'] = [
                'Change nameservers to HostBay nameservers',
                'Verify DNS propagation',
                'Configure hosting integration'
            ]
            
            recommendation['benefits'] = [
                'Automatic DNS management',
                'Seamless hosting integration',
                'Optimized performance'
            ]
            
            # Add warnings based on current setup
            if dns_info.get('cloudflare_proxy'):
                recommendation['warnings'].append(
                    'Domain appears to use Cloudflare proxy - may need manual DNS configuration'
                )
                recommendation['strategy'] = 'manual_dns'
            
            if len(dns_info.get('mx_records', [])) > 0:
                recommendation['warnings'].append(
                    'Domain has email (MX) records - email services may be affected'
                )
        
        return recommendation
    
    async def validate_domain_ownership(
        self, 
        domain_name: str, 
        verification_token: str
    ) -> Dict[str, Any]:
        """
        Validate domain ownership using DNS TXT record verification.
        Phase 1: Basic implementation
        """
        try:
            # Look for verification TXT record
            txt_response = dns.resolver.resolve(f"_hostbay-verify.{domain_name}", 'TXT')
            
            for txt_record in txt_response:
                txt_value = str(txt_record).strip('"')
                if txt_value == verification_token:
                    return {
                        'success': True,
                        'verified': True,
                        'method': 'dns_txt',
                        'verification_time': datetime.utcnow().isoformat()
                    }
            
            return {
                'success': True,
                'verified': False,
                'error': 'Verification token not found in DNS TXT record',
                'expected_record': f"_hostbay-verify.{domain_name} TXT {verification_token}"
            }
            
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return {
                'success': True,
                'verified': False,
                'error': 'Verification TXT record not found',
                'expected_record': f"_hostbay-verify.{domain_name} TXT {verification_token}"
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'DNS verification failed: {str(e)}'
            }
    
    async def check_nameserver_changes(self, domain_name: str) -> Dict[str, Any]:
        """Check if nameservers have been changed to HostBay nameservers"""
        try:
            current_dns = await self._analyze_dns(domain_name)
            
            if not current_dns.get('nameservers'):
                return {
                    'success': False,
                    'error': 'Could not retrieve current nameservers'
                }
            
            current_ns = current_dns['nameservers']
            
            # Check if using HostBay nameservers
            using_hostbay = all(
                any(hb_ns in ns for hb_ns in self.hostbay_nameservers)
                for ns in current_ns[:2]  # Check first 2 nameservers
            )
            
            return {
                'success': True,
                'using_hostbay_nameservers': using_hostbay,
                'current_nameservers': current_ns,
                'expected_nameservers': self.hostbay_nameservers,
                'check_timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Nameserver check failed: {str(e)}'
            }