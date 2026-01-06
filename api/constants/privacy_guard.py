"""
Privacy Guard Contact Information

This contact information is used when WHOIS privacy protection is enabled
for domains with user-provided contact information.
"""

# Flat format matching ContactInfo schema (for API registration)
PRIVACY_GUARD_CONTACT_FLAT = {
    "first_name": "Domain",
    "last_name": "Privacy Guard",
    "email": "cloakhost@tutamail.com",
    "phone": "+354.4212434",
    "company": "Whois Privacy Service",
    "address": "P.O. Box 123, Privacy Dept.",
    "city": "Reykjavik",
    "state": "Capital Region",
    "postal_code": "101",
    "country": "IS"
}

# Nested format for OpenProvider API (legacy)
PRIVACY_GUARD_CONTACT = {
    "name": {
        "first_name": "Domain",
        "last_name": "Privacy Guard",
        "full_name": "Domain Privacy Guard"
    },
    "company_name": "Whois Privacy Service",
    "address": {
        "street": "P.O. Box 123, Privacy Dept.",
        "city": "Reykjavik",
        "state": "Capital Region",
        "zipcode": "101",
        "country": "IS"
    },
    "phone": {
        "country_code": "354",
        "area_code": "421",
        "subscriber_number": "2434"
    },
    "fax": {
        "country_code": "354",
        "area_code": "421",
        "subscriber_number": "2435"
    },
    "email": "cloakhost@tutamail.com"
}

def get_privacy_guard_handle():
    """
    Returns the Privacy Guard contact information in OpenProvider handle format.
    """
    return {
        "firstName": PRIVACY_GUARD_CONTACT["name"]["first_name"],
        "lastName": PRIVACY_GUARD_CONTACT["name"]["last_name"],
        "companyName": PRIVACY_GUARD_CONTACT["company_name"],
        "address": {
            "street": PRIVACY_GUARD_CONTACT["address"]["street"],
            "city": PRIVACY_GUARD_CONTACT["address"]["city"],
            "state": PRIVACY_GUARD_CONTACT["address"]["state"],
            "zipcode": PRIVACY_GUARD_CONTACT["address"]["zipcode"],
            "country": PRIVACY_GUARD_CONTACT["address"]["country"]
        },
        "phone": {
            "countryCode": PRIVACY_GUARD_CONTACT["phone"]["country_code"],
            "areaCode": PRIVACY_GUARD_CONTACT["phone"]["area_code"],
            "subscriberNumber": PRIVACY_GUARD_CONTACT["phone"]["subscriber_number"]
        },
        "fax": {
            "countryCode": PRIVACY_GUARD_CONTACT["fax"]["country_code"],
            "areaCode": PRIVACY_GUARD_CONTACT["fax"]["area_code"],
            "subscriberNumber": PRIVACY_GUARD_CONTACT["fax"]["subscriber_number"]
        },
        "email": PRIVACY_GUARD_CONTACT["email"]
    }
