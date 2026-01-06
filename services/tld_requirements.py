"""
Comprehensive TLD-specific requirements validation system for OpenProvider domain registration

This module implements TLD-specific validation rules and requirements based on OpenProvider's 
official requirements to prevent domain registration failures by validating requirements upfront.

Supported TLD-specific validations:
- .be: Postal code syntax validation, phone number length validation
- .de: Pre-registration nameserver validation (CRITICAL)  
- .us: US Nexus eligibility validation, additional data fields (C11/C12 codes)
- .ca: Canadian eligibility validation, contact handle requirements, legal form validation
- .it: Italian Fiscal Code (Codice Fiscale) validation, entity type classification

Features:
- Async/await patterns for performance
- DNS resolution checks for nameserver validation
- Country-specific postal code and phone validation
- Integration with OpenProvider's extension_additional_data API
- Comprehensive logging and error handling
- Admin alerts integration for validation failures
"""

import os
import re
import logging
import asyncio
import dns.resolver
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import httpx
from admin_alerts import send_error_alert, send_warning_alert
from performance_monitor import monitor_performance

logger = logging.getLogger(__name__)

# ====================================================================
# TLD-SPECIFIC VALIDATION CONFIGURATION
# ====================================================================

class USNexusCategory(Enum):
    """US Nexus categories for .us domain eligibility"""
    C11 = "C11"  # Natural person US citizen
    C12 = "C12"  # Natural person US permanent resident
    C21 = "C21"  # US entity/organization
    C31 = "C31"  # Foreign entity with presence in US
    C32 = "C32"  # Foreign entity with regular activity in US

class CALegalType(Enum):
    """Canadian legal types for .ca domain eligibility"""
    CCO = "CCO"  # Corporation (Canada or Canadian province/territory)
    CCT = "CCT"  # Canadian citizen
    RES = "RES"  # Permanent resident of Canada
    GOV = "GOV"  # Government or government entity
    EDU = "EDU"  # Educational institution
    ASS = "ASS"  # Unincorporated association
    HOP = "HOP"  # Hospital
    PRT = "PRT"  # Partnership
    TDM = "TDM"  # Trade-mark
    TRD = "TRD"  # Trade union
    PLT = "PLT"  # Political party
    LAM = "LAM"  # Library, archive or museum
    TRS = "TRS"  # Trust
    ABO = "ABO"  # Aboriginal Peoples

class ItalyEntityType(Enum):
    """Italian entity types for .it domain registration"""
    INDIVIDUAL = "1"  # Italian individual
    COMPANY = "2"  # Italian company
    FREELANCER = "3"  # Freelancer/Professional
    NON_ITALIAN_EU = "4"  # Non-Italian EU citizen/company
    NON_EU = "5"  # Non-EU entity (requires trustee)
    OTHER = "7"  # Other entities

@dataclass
class TLDValidationResult:
    """Result of TLD-specific validation"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    additional_data: Optional[Dict[str, Any]] = None

# ====================================================================
# POSTAL CODE VALIDATION BY COUNTRY
# ====================================================================

class PostalCodeValidator:
    """Validates postal codes based on country-specific formats"""
    
    # Country-specific postal code patterns
    POSTAL_PATTERNS = {
        'BE': r'^[1-9]\d{3}$',  # Belgium: 4 digits, no leading zero
        'FR': r'^\d{5}$',       # France: 5 digits
        'DE': r'^\d{5}$',       # Germany: 5 digits
        'NL': r'^\d{4}\s?[A-Z]{2}$',  # Netherlands: 4 digits + 2 letters
        'UK': r'^[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}$',  # UK format
        'US': r'^\d{5}(-\d{4})?$',  # US: 5 digits or 5+4 format
        'CA': r'^[A-Z]\d[A-Z]\s?\d[A-Z]\d$'  # Canada: A1A 1A1 format
    }
    
    @classmethod
    def validate_postal_code(cls, postal_code: str, country_code: str) -> bool:
        """Validate postal code format for specific country"""
        if not postal_code or not country_code:
            return False
        
        country_code = country_code.upper()
        postal_code = postal_code.strip().upper()
        
        pattern = cls.POSTAL_PATTERNS.get(country_code)
        if not pattern:
            # For unsupported countries, accept any non-empty postal code
            return len(postal_code.strip()) > 0
        
        return bool(re.match(pattern, postal_code))

# ====================================================================
# PHONE NUMBER VALIDATION BY COUNTRY
# ====================================================================

class PhoneValidator:
    """Validates phone numbers based on country-specific length requirements"""
    
    # Country code to expected phone number length mapping (excluding country code)
    PHONE_LENGTH_REQUIREMENTS = {
        '+32': {'min': 8, 'max': 9, 'country': 'Belgium'},     # Belgium
        '+33': {'min': 9, 'max': 10, 'country': 'France'},    # France  
        '+49': {'min': 10, 'max': 12, 'country': 'Germany'},  # Germany
        '+31': {'min': 9, 'max': 9, 'country': 'Netherlands'}, # Netherlands
        '+44': {'min': 10, 'max': 10, 'country': 'UK'},       # UK
        '+1': {'min': 10, 'max': 10, 'country': 'US/Canada'}, # US/Canada
    }
    
    @classmethod
    def validate_phone_length(cls, phone: str, country_code: Optional[str] = None) -> Tuple[bool, str]:
        """
        Validate phone number length based on country code
        
        Returns:
            Tuple[bool, str]: (is_valid, error_message)
        """
        if not phone:
            return False, "Phone number is required"
        
        # Extract country code from phone number if not provided
        phone_clean = ''.join(char for char in phone if char.isdigit() or char == '+')
        
        if phone_clean.startswith('+'):
            # Extract country code (1-3 digits after +)
            for code in sorted(cls.PHONE_LENGTH_REQUIREMENTS.keys(), key=len, reverse=True):
                if phone_clean.startswith(code):
                    country_code = code
                    phone_number = phone_clean[len(code):]
                    break
            else:
                return True, ""  # Unknown country code, accept as valid
        else:
            return True, ""  # No country code, accept as valid
        
        if not country_code or country_code not in cls.PHONE_LENGTH_REQUIREMENTS:
            return True, ""  # Unknown country, accept as valid
        
        requirements = cls.PHONE_LENGTH_REQUIREMENTS[country_code]
        phone_length = len(phone_number)
        min_length = requirements['min']
        max_length = requirements['max']
        country_name = requirements['country']
        
        if phone_length < min_length or phone_length > max_length:
            if min_length == max_length:
                expected = f"{min_length} digits"
            else:
                expected = f"{min_length}-{max_length} digits"
            
            return False, f"Invalid phone number length for {country_name}. Expected {expected}, got {phone_length} digits."
        
        return True, ""

# ====================================================================
# NAMESERVER VALIDATION
# ====================================================================

class NameserverValidator:
    """Validates nameserver resolution - critical for .de domains"""
    
    @staticmethod
    async def check_nameserver_resolution(nameservers: List[str], timeout: int = 3) -> Tuple[bool, List[str], List[str]]:
        """
        Check if nameservers are resolving properly
        
        Args:
            nameservers: List of nameserver hostnames
            timeout: DNS resolution timeout in seconds
            
        Returns:
            Tuple[bool, List[str], List[str]]: (all_valid, valid_nameservers, failed_nameservers)
        """
        if not nameservers:
            return False, [], []
        
        valid_nameservers = []
        failed_nameservers = []
        
        # Configure DNS resolver with timeout
        resolver = dns.resolver.Resolver()
        resolver.timeout = timeout
        resolver.lifetime = timeout  # Total query timeout
        
        for ns in nameservers:
            try:
                # Try to resolve the nameserver hostname
                logger.debug(f"🔍 Checking nameserver resolution: {ns}")
                
                # Resolve A record for the nameserver
                answers = resolver.resolve(ns, 'A')
                if answers:
                    ip_addresses = [str(rdata) for rdata in answers]
                    logger.debug(f"✅ Nameserver {ns} resolves to: {ip_addresses}")
                    valid_nameservers.append(ns)
                else:
                    logger.warning(f"⚠️ Nameserver {ns} has no A records")
                    failed_nameservers.append(ns)
                    
            except dns.resolver.NXDOMAIN:
                logger.warning(f"❌ Nameserver {ns} does not exist (NXDOMAIN)")
                failed_nameservers.append(ns)
            except dns.resolver.Timeout:
                logger.warning(f"⏰ Nameserver {ns} resolution timed out after {timeout}s")
                failed_nameservers.append(ns)
            except Exception as e:
                logger.warning(f"❌ Nameserver {ns} resolution failed: {e}")
                failed_nameservers.append(ns)
        
        all_valid = len(failed_nameservers) == 0
        return all_valid, valid_nameservers, failed_nameservers

# ====================================================================
# TLD-SPECIFIC VALIDATORS
# ====================================================================

class BelgiumTLDValidator:
    """Validator for .be domain specific requirements"""
    
    @staticmethod
    async def validate_be_requirements(contact_data: Dict[str, Any]) -> TLDValidationResult:
        """
        Validate .be domain requirements
        
        Requirements:
        - Valid postal code format for country
        - Phone number length validation based on country code
        """
        errors = []
        warnings = []
        
        try:
            # Extract contact information
            postal_code = contact_data.get('postal_code', '').strip()
            country_code = contact_data.get('country', '').strip()
            phone = contact_data.get('phone', '').strip()
            
            # Validate postal code
            if postal_code and country_code:
                if not PostalCodeValidator.validate_postal_code(postal_code, country_code):
                    errors.append(f"Invalid postal code format for {country_code}: {postal_code}")
            elif not postal_code:
                errors.append("Postal code is required for .be domains")
            
            # Validate phone number length
            if phone:
                is_valid_phone, phone_error = PhoneValidator.validate_phone_length(phone)
                if not is_valid_phone:
                    errors.append(f"Phone validation for .be domain: {phone_error}")
            else:
                errors.append("Phone number is required for .be domains")
            
            logger.info(f"🇧🇪 .be domain validation: {len(errors)} errors, {len(warnings)} warnings")
            
        except Exception as e:
            logger.error(f"❌ Error validating .be requirements: {e}")
            errors.append(f"Validation error: {str(e)}")
        
        return TLDValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

class GermanyTLDValidator:
    """Validator for .de domain specific requirements"""
    
    @staticmethod
    async def validate_de_requirements(contact_data: Dict[str, Any], nameservers: List[str]) -> TLDValidationResult:
        """
        Validate .de domain requirements
        
        CRITICAL Requirements:
        - Nameservers must be resolving BEFORE registration attempt
        """
        errors = []
        warnings = []
        
        try:
            logger.info("🇩🇪 Validating .de domain requirements (CRITICAL: nameserver pre-validation)")
            
            # CRITICAL: Pre-registration nameserver validation
            if not nameservers or len(nameservers) == 0:
                errors.append("Nameservers are required for .de domain registration")
            else:
                logger.info(f"🔍 Checking {len(nameservers)} nameservers for .de domain...")
                all_valid, valid_ns, failed_ns = await NameserverValidator.check_nameserver_resolution(nameservers, timeout=4)
                
                if not all_valid:
                    errors.append(f"Nameserver resolution failed for .de domain. Failed nameservers: {failed_ns}")
                    logger.error(f"❌ .de nameserver validation failed: {failed_ns}")
                    
                    # Send admin alert for .de nameserver validation failure
                    await send_error_alert(
                        "TLD_Validation",
                        f".de nameserver validation failed: {failed_ns}",
                        "domain_registration",
                        {
                            "tld": ".de",
                            "nameservers": nameservers,
                            "failed_nameservers": failed_ns,
                            "valid_nameservers": valid_ns
                        }
                    )
                else:
                    logger.info(f"✅ All nameservers valid for .de domain: {valid_ns}")
            
            logger.info(f"🇩🇪 .de domain validation: {len(errors)} errors, {len(warnings)} warnings")
            
        except Exception as e:
            logger.error(f"❌ Error validating .de requirements: {e}")
            errors.append(f"Nameserver validation error: {str(e)}")
        
        return TLDValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

class USTLDValidator:
    """Validator for .us domain specific requirements"""
    
    @staticmethod
    async def validate_us_requirements(contact_data: Dict[str, Any], application_purpose: Optional[str] = None) -> TLDValidationResult:
        """
        Validate .us domain requirements
        
        Requirements:
        - US Nexus eligibility validation
        - Application purpose field (C11/C12 codes)
        """
        errors = []
        warnings = []
        additional_data = {}
        
        try:
            logger.info("🇺🇸 Validating .us domain requirements (US Nexus eligibility)")
            
            # Validate US Nexus category
            if not application_purpose:
                # Default to C12 if not specified (permanent resident)
                application_purpose = "C12"
                warnings.append("No application purpose specified, defaulting to C12 (permanent resident)")
            
            # Validate application purpose is valid US Nexus category
            try:
                nexus_category = USNexusCategory(application_purpose)
                logger.info(f"✅ Valid US Nexus category: {nexus_category.value}")
            except ValueError:
                valid_categories = [cat.value for cat in USNexusCategory]
                errors.append(f"Invalid US Nexus category '{application_purpose}'. Valid options: {valid_categories}")
                nexus_category = None
            
            # Add additional data for OpenProvider API
            if nexus_category:
                additional_data['extension_additional_data'] = {
                    'us': {
                        'application_purpose': nexus_category.value
                    }
                }
            
            # Basic US address validation
            country = contact_data.get('country', '').upper()
            if country and country != 'US':
                warnings.append("Contact address is not in the US, but registering a .us domain")
            
            logger.info(f"🇺🇸 .us domain validation: {len(errors)} errors, {len(warnings)} warnings")
            
        except Exception as e:
            logger.error(f"❌ Error validating .us requirements: {e}")
            errors.append(f"US validation error: {str(e)}")
        
        return TLDValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            additional_data=additional_data
        )

class CanadaTLDValidator:
    """Validator for .ca domain specific requirements"""
    
    @staticmethod
    async def validate_ca_requirements(contact_data: Dict[str, Any], legal_type: Optional[str] = None) -> TLDValidationResult:
        """
        Validate .ca domain requirements
        
        Requirements:
        - Canadian eligibility validation
        - Legal type classification
        - Contact handle requirements
        """
        errors = []
        warnings = []
        additional_data = {}
        
        try:
            logger.info("🇨🇦 Validating .ca domain requirements (Canadian eligibility)")
            
            # Validate legal type
            if not legal_type:
                # Default to CCT (Canadian citizen) if not specified
                legal_type = "CCT"
                warnings.append("No legal type specified, defaulting to CCT (Canadian citizen)")
            
            # Validate legal type is valid CA category
            try:
                ca_legal_type = CALegalType(legal_type)
                logger.info(f"✅ Valid CA legal type: {ca_legal_type.value}")
            except ValueError:
                valid_types = [lt.value for lt in CALegalType]
                errors.append(f"Invalid CA legal type '{legal_type}'. Valid options: {valid_types}")
                ca_legal_type = None
            
            # Add additional data for OpenProvider API
            # .ca domains use direct additional_data format (different from .us domains)
            if ca_legal_type:
                additional_data = {
                    'legal_type': ca_legal_type.value,
                    'cpr_category': ca_legal_type.value  # CIRA category requirement
                }
            
            # Basic Canadian address validation
            country = contact_data.get('country', '').upper()
            if country and country != 'CA':
                warnings.append("Contact address is not in Canada, but registering a .ca domain")
            
            # Postal code validation for Canada
            postal_code = contact_data.get('postal_code', '').strip()
            if postal_code:
                if not PostalCodeValidator.validate_postal_code(postal_code, 'CA'):
                    errors.append(f"Invalid Canadian postal code format: {postal_code}")
            else:
                warnings.append("Postal code recommended for .ca domains")
            
            logger.info(f"🇨🇦 .ca domain validation: {len(errors)} errors, {len(warnings)} warnings")
            
        except Exception as e:
            logger.error(f"❌ Error validating .ca requirements: {e}")
            errors.append(f"CA validation error: {str(e)}")
        
        return TLDValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            additional_data=additional_data
        )

class ItalyTLDValidator:
    """Validator for .it domain specific requirements"""
    
    @staticmethod
    def validate_codice_fiscale(fiscal_code: str, entity_type: str) -> Tuple[bool, Optional[str]]:
        """
        Validate Italian Fiscal Code (Codice Fiscale) format
        
        Args:
            fiscal_code: The fiscal code to validate
            entity_type: Entity type (1=individual, 2=company, etc.)
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not fiscal_code:
            return False, "Codice Fiscale is required for .it domains"
        
        fiscal_code = fiscal_code.strip().upper()
        
        # Individual fiscal code: 16 alphanumeric characters
        if entity_type == "1":  # Italian individual
            if len(fiscal_code) != 16:
                return False, f"Individual Codice Fiscale must be 16 characters (got {len(fiscal_code)})"
            if not re.match(r'^[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]$', fiscal_code):
                return False, "Invalid Codice Fiscale format for individual (expected: ABCDEF12G34H567I)"
        
        # Company fiscal code: 11 digits
        elif entity_type == "2":  # Italian company
            if len(fiscal_code) != 11:
                return False, f"Company Codice Fiscale must be 11 digits (got {len(fiscal_code)})"
            if not re.match(r'^\d{11}$', fiscal_code):
                return False, "Invalid Codice Fiscale format for company (expected: 11 digits)"
        
        # Non-Italian EU: Accept passport/ID number (flexible format)
        elif entity_type == "4":  # Non-Italian EU
            if len(fiscal_code) < 5:
                return False, "Passport/ID number must be at least 5 characters"
        
        return True, None
    
    @staticmethod
    async def validate_it_requirements(
        contact_data: Dict[str, Any], 
        fiscal_code: Optional[str] = None,
        entity_type: Optional[str] = None
    ) -> TLDValidationResult:
        """
        Validate .it domain requirements
        
        Requirements:
        - Italian Fiscal Code (Codice Fiscale)
        - Entity type classification
        - Contact information validation
        """
        errors = []
        warnings = []
        additional_data = {}
        
        try:
            logger.info("🇮🇹 Validating .it domain requirements (Italian Fiscal Code)")
            
            # Default entity type if not provided
            if not entity_type:
                entity_type = "1"  # Default to individual
                warnings.append("No entity type specified, defaulting to Individual (1)")
            
            # Validate entity type
            try:
                it_entity_type = ItalyEntityType(entity_type)
                logger.info(f"✅ Valid IT entity type: {it_entity_type.value} ({it_entity_type.name})")
            except ValueError:
                valid_types = [et.value for et in ItalyEntityType]
                errors.append(f"Invalid IT entity type '{entity_type}'. Valid options: {valid_types}")
                it_entity_type = None
            
            # Validate Codice Fiscale
            if not fiscal_code:
                errors.append("Italian Fiscal Code (Codice Fiscale) is required for .it domain registration")
            else:
                is_valid_fc, fc_error = ItalyTLDValidator.validate_codice_fiscale(fiscal_code, entity_type)
                if not is_valid_fc:
                    errors.append(fc_error)
                else:
                    logger.info(f"✅ Valid Codice Fiscale: {fiscal_code[:4]}...{fiscal_code[-4:]}")
            
            # Build additional data for OpenProvider API
            if it_entity_type and fiscal_code:
                additional_data = {
                    'entity_type': entity_type,
                    'reg_code': fiscal_code.strip().upper()
                }
                logger.info(f"📦 Built .it additional data: entity_type={entity_type}, reg_code={fiscal_code[:4]}...")
            
            # Validate contact has required fields
            if not contact_data.get('company_name') and entity_type == "2":
                errors.append("Company name is required for company entity type")
            
            if not contact_data.get('name'):
                errors.append("Contact name is required for .it domains")
            
            # Check if registrant is in EU (recommended but not required)
            country = contact_data.get('country', '').upper()
            eu_countries = ['IT', 'FR', 'DE', 'ES', 'NL', 'BE', 'AT', 'PT', 'GR', 'IE', 'FI', 
                          'SE', 'DK', 'PL', 'CZ', 'HU', 'RO', 'BG', 'HR', 'SK', 'SI', 'LT', 
                          'LV', 'EE', 'CY', 'MT', 'LU']
            if country and country not in eu_countries:
                warnings.append("Registrant should be in EU/EEA for .it domain eligibility")
            
            logger.info(f"🇮🇹 .it domain validation: {len(errors)} errors, {len(warnings)} warnings")
            
        except Exception as e:
            logger.error(f"❌ Error validating .it requirements: {e}")
            errors.append(f"IT validation error: {str(e)}")
        
        return TLDValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            additional_data=additional_data
        )

# ====================================================================
# MAIN TLD REQUIREMENTS VALIDATOR
# ====================================================================

class TLDRequirementsValidator:
    """Main TLD requirements validation system"""
    
    # TLD to validator mapping (class-level for backward compatibility)
    TLD_VALIDATORS = {
        'be': BelgiumTLDValidator.validate_be_requirements,
        'de': GermanyTLDValidator.validate_de_requirements,
        'us': USTLDValidator.validate_us_requirements,
        'ca': CanadaTLDValidator.validate_ca_requirements,
        'it': ItalyTLDValidator.validate_it_requirements,
    }
    
    def __init__(self):
        """Initialize TLD validator with mapping for .be/.de/.us/.ca/.it"""
        # Instance-level validators mapping
        self._validators = {
            'be': BelgiumTLDValidator.validate_be_requirements,
            'de': GermanyTLDValidator.validate_de_requirements, 
            'us': USTLDValidator.validate_us_requirements,
            'ca': CanadaTLDValidator.validate_ca_requirements,
            'it': ItalyTLDValidator.validate_it_requirements,
        }
        logger.info(f"✅ TLD Requirements Validator initialized with {len(self._validators)} TLD validators")
    
    async def validate(self, tld: str, contact_data: Dict[str, Any], nameservers: Optional[List[str]] = None, extras: Optional[Dict[str, Any]] = None) -> TLDValidationResult:
        """
        Validate TLD-specific requirements for domain registration
        
        Args:
            tld: TLD to validate (without dot, e.g., "be", "de", "us", "ca")
            contact_data: Contact information dictionary
            nameservers: List of nameservers (required for .de validation)
            extras: Additional TLD-specific parameters
            
        Returns:
            TLDValidationResult with validation status and any additional data needed
        """
        if not tld:
            return TLDValidationResult(
                is_valid=False,
                errors=["TLD is required"],
                warnings=[]
            )
        
        # Normalize TLD (remove dot if present, lowercase)
        tld = tld.lower().lstrip('.')
        
        # Check if we have specific validation for this TLD
        if tld not in self._validators:
            logger.info(f"ℹ️ No specific TLD validation required for .{tld} domain")
            return TLDValidationResult(
                is_valid=True,
                errors=[],
                warnings=[f"No specific validation implemented for .{tld} domains"]
            )
        
        logger.info(f"🔍 Running TLD-specific validation for .{tld} domain")
        
        try:
            # Get the appropriate validator
            validator = self._validators[tld]
            extras = extras or {}
            
            # Call TLD-specific validator with appropriate parameters
            if tld == 'de':
                # .de requires nameserver validation
                result = await validator(contact_data, nameservers or [])
            elif tld == 'us':
                # .us requires application purpose
                application_purpose = extras.get('application_purpose')
                result = await validator(contact_data, application_purpose)
            elif tld == 'ca':
                # .ca requires legal type
                legal_type = extras.get('legal_type')
                result = await validator(contact_data, legal_type)
            elif tld == 'it':
                # .it requires fiscal code and entity type
                fiscal_code = extras.get('fiscal_code')
                entity_type = extras.get('entity_type')
                result = await validator(contact_data, fiscal_code, entity_type)
            else:
                # Default case (.be and others)
                result = await validator(contact_data)
            
            # Log validation results
            if result.is_valid:
                logger.info(f"✅ TLD validation passed for .{tld} domain")
            else:
                logger.error(f"❌ TLD validation failed for .{tld} domain")
                logger.error(f"   Errors: {result.errors}")
                
                # Send admin alert for TLD validation failure
                await send_warning_alert(
                    "TLD_Validation", 
                    f"TLD validation failed for .{tld} domain",
                    "domain_registration",
                    {
                        "tld": tld,
                        "errors": result.errors,
                        "warnings": result.warnings,
                        "contact_data": contact_data
                    }
                )
            
            if result.warnings:
                logger.warning(f"⚠️ TLD validation warnings for .{tld} domain: {result.warnings}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error during TLD validation for .{tld} domain: {e}")
            return TLDValidationResult(
                is_valid=False,
                errors=[f"TLD validation error: {str(e)}"],
                warnings=[]
            )
    
    @classmethod
    @monitor_performance("tld_validation")
    async def validate_tld_requirements(
        cls, 
        domain_name: str, 
        contact_data: Dict[str, Any], 
        nameservers: Optional[List[str]] = None,
        additional_params: Optional[Dict[str, Any]] = None
    ) -> TLDValidationResult:
        """
        Validate TLD-specific requirements for domain registration
        
        Args:
            domain_name: Full domain name (e.g., "example.com")
            contact_data: Contact information dictionary
            nameservers: List of nameservers (required for .de validation)
            additional_params: Additional TLD-specific parameters
            
        Returns:
            TLDValidationResult with validation status and any additional data needed
        """
        if not domain_name or '.' not in domain_name:
            return TLDValidationResult(
                is_valid=False,
                errors=["Invalid domain name format"],
                warnings=[]
            )
        
        # Extract TLD from domain name
        tld = domain_name.split('.')[-1].lower()
        
        # Check if we have specific validation for this TLD
        if tld not in cls.TLD_VALIDATORS:
            logger.info(f"ℹ️ No specific TLD validation required for .{tld} domain")
            return TLDValidationResult(
                is_valid=True,
                errors=[],
                warnings=[f"No specific validation implemented for .{tld} domains"]
            )
        
        logger.info(f"🔍 Running TLD-specific validation for .{tld} domain: {domain_name}")
        
        try:
            # Get the appropriate validator
            validator = cls.TLD_VALIDATORS[tld]
            additional_params = additional_params or {}
            
            # Call TLD-specific validator with appropriate parameters
            if tld == 'de':
                # .de requires nameserver validation
                result = await validator(contact_data, nameservers or [])
            elif tld == 'us':
                # .us requires application purpose
                application_purpose = additional_params.get('application_purpose')
                result = await validator(contact_data, application_purpose)
            elif tld == 'ca':
                # .ca requires legal type
                legal_type = additional_params.get('legal_type')
                result = await validator(contact_data, legal_type)
            else:
                # Default case (.be and others)
                result = await validator(contact_data)
            
            # Log validation results
            if result.is_valid:
                logger.info(f"✅ TLD validation passed for .{tld} domain: {domain_name}")
            else:
                logger.error(f"❌ TLD validation failed for .{tld} domain: {domain_name}")
                logger.error(f"   Errors: {result.errors}")
                
                # Send admin alert for TLD validation failure
                await send_warning_alert(
                    "TLD_Validation", 
                    f"TLD validation failed for .{tld} domain: {domain_name}",
                    "domain_registration",
                    {
                        "domain": domain_name,
                        "tld": tld,
                        "errors": result.errors,
                        "warnings": result.warnings,
                        "contact_data": contact_data
                    }
                )
            
            if result.warnings:
                logger.warning(f"⚠️ TLD validation warnings for .{tld} domain: {result.warnings}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error during TLD validation for .{tld} domain {domain_name}: {e}")
            return TLDValidationResult(
                is_valid=False,
                errors=[f"TLD validation error: {str(e)}"],
                warnings=[]
            )
    
    @classmethod
    def get_supported_tlds(cls) -> List[str]:
        """Get list of TLDs with specific validation requirements"""
        return list(cls.TLD_VALIDATORS.keys())
    
    @classmethod
    def has_specific_requirements(cls, tld: str) -> bool:
        """Check if a TLD has specific validation requirements"""
        return tld.lower() in cls.TLD_VALIDATORS

# ====================================================================
# UTILITY FUNCTIONS
# ====================================================================

async def get_tld_requirements_info(tld: str) -> Dict[str, Any]:
    """
    Get information about TLD-specific requirements
    
    Args:
        tld: TLD to get info for (without dot, e.g., 'be')
        
    Returns:
        Dictionary with TLD requirements information
    """
    tld = tld.lower()
    
    requirements_info = {
        'be': {
            'name': 'Belgium',
            'requirements': [
                'Valid postal code format for registrant country',
                'Phone number length validation based on country code',
                'Contact information must be complete'
            ],
            'additional_data': False,
            'critical_checks': ['postal_code_format', 'phone_length']
        },
        'de': {
            'name': 'Germany', 
            'requirements': [
                'CRITICAL: Nameservers must be resolving before registration',
                'Pre-registration DNS validation required',
                'Nameserver resolution timeout: 8 seconds'
            ],
            'additional_data': False,
            'critical_checks': ['nameserver_resolution']
        },
        'us': {
            'name': 'United States',
            'requirements': [
                'US Nexus eligibility required',
                'Application purpose code (C11=US citizen, C12=permanent resident)',
                'Valid US Nexus category must be specified'
            ],
            'additional_data': True,
            'critical_checks': ['nexus_eligibility', 'application_purpose']
        },
        'ca': {
            'name': 'Canada',
            'requirements': [
                'Canadian eligibility required',
                'Legal type classification (CCT, CCO, RES, etc.)',
                'Contact handle requirements',
                'Valid Canadian postal code format'
            ],
            'additional_data': True,
            'critical_checks': ['legal_type', 'postal_code_format']
        },
        'it': {
            'name': 'Italy',
            'requirements': [
                'Italian Fiscal Code (Codice Fiscale) required',
                'Entity type classification (1=Individual, 2=Company, 4=Non-Italian EU)',
                'Individuals: 16 alphanumeric characters (e.g., RSSMRA80A01H501X)',
                'Companies: 11 digits (e.g., 12345678901)',
                'EU/EEA residency or citizenship required'
            ],
            'additional_data': True,
            'critical_checks': ['fiscal_code_format', 'entity_type']
        }
    }
    
    return requirements_info.get(tld, {
        'name': f'.{tld} domain',
        'requirements': ['No specific validation requirements'],
        'additional_data': False,
        'critical_checks': []
    })

# ====================================================================
# BACKWARD-COMPATIBLE SYNC WRAPPER FUNCTION
# ====================================================================

# Global validator instance for backward compatibility
_global_validator = None

def _get_global_validator() -> TLDRequirementsValidator:
    """Get or create global validator instance"""
    global _global_validator
    if _global_validator is None:
        _global_validator = TLDRequirementsValidator()
    return _global_validator

def validate_tld_requirements(
    domain_name: str, 
    contact_data: Dict[str, Any], 
    nameservers: Optional[List[str]] = None,
    additional_params: Optional[Dict[str, Any]] = None
) -> TLDValidationResult:
    """
    Backward-compatible sync wrapper for TLD requirements validation
    
    This function maintains compatibility with existing code that expects
    a synchronous function call with domain_name parameter.
    
    Args:
        domain_name: Full domain name (e.g., "example.com")
        contact_data: Contact information dictionary
        nameservers: List of nameservers (required for .de validation)
        additional_params: Additional TLD-specific parameters
        
    Returns:
        TLDValidationResult with validation status and any additional data needed
    """
    if not domain_name or '.' not in domain_name:
        return TLDValidationResult(
            is_valid=False,
            errors=["Invalid domain name format"],
            warnings=[]
        )
    
    # Extract TLD from domain name
    tld = domain_name.split('.')[-1].lower()
    
    # Get global validator instance
    validator = _get_global_validator()
    
    # Run async validation in sync context
    try:
        import asyncio
        # Try to get existing event loop
        try:
            loop = asyncio.get_running_loop()
            # We're already in an async context, create a task
            logger.warning("⚠️ validate_tld_requirements called from async context, consider using async validate() method directly")
            # Use create_task to avoid blocking the current event loop
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, validator.validate(tld, contact_data, nameservers, additional_params))
                result = future.result(timeout=30)  # 30 second timeout
                return result
        except RuntimeError:
            # No event loop running, safe to use asyncio.run
            result = asyncio.run(validator.validate(tld, contact_data, nameservers, additional_params))
            return result
    except Exception as e:
        logger.error(f"❌ Error in sync wrapper for TLD validation: {e}")
        return TLDValidationResult(
            is_valid=False,
            errors=[f"Sync validation wrapper error: {str(e)}"],
            warnings=[]
        )

# Export main validator class for easy import
__all__ = [
    'TLDRequirementsValidator',
    'TLDValidationResult', 
    'get_tld_requirements_info',
    'USNexusCategory',
    'CALegalType',
    'validate_tld_requirements'  # Backward-compatible sync wrapper
]