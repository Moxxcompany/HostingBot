"""
Test Notifications API - For testing admin notification delivery
"""
from fastapi import APIRouter
from api.utils.responses import success_response
from admin_alerts import send_info_alert, send_error_alert, send_critical_alert

router = APIRouter()


@router.post("/test/admin-notifications", response_model=dict)
async def test_admin_notifications():
    """
    Test admin notification system by sending sample notifications
    This endpoint tests all notification types for both Domain and RDP events
    """
    results = []
    
    # Test 1: Domain Registration Success (API)
    try:
        success = await send_info_alert(
            "TEST_DomainAPI",
            "✅ LIVE TEST: Domain registered via API: test-success-123.com for user 999888",
            "domain_registration",
            {
                "domain_name": "test-success-123.com",
                "user_id": 999888,
                "payment_method": "API (wallet)",
                "amount": 49.99,
                "test_mode": True
            }
        )
        results.append({
            "test": "Domain Registration Success",
            "sent": success,
            "type": "INFO"
        })
    except Exception as e:
        results.append({
            "test": "Domain Registration Success",
            "sent": False,
            "error": str(e),
            "type": "INFO"
        })
    
    # Test 2: Domain Registration Failure (API)
    try:
        success = await send_error_alert(
            "TEST_DomainAPI",
            "❌ LIVE TEST: Domain registration failed via API: test-fail-456.com",
            "domain_registration",
            {
                "domain_name": "test-fail-456.com",
                "user_id": 999888,
                "error": "Domain already registered with OpenProvider"
            }
        )
        results.append({
            "test": "Domain Registration Failure",
            "sent": success,
            "type": "ERROR"
        })
    except Exception as e:
        results.append({
            "test": "Domain Registration Failure",
            "sent": False,
            "error": str(e),
            "type": "ERROR"
        })
    
    # Test 3: RDP Provisioning Start (API)
    try:
        success = await send_info_alert(
            "TEST_RDP_API",
            "✅ LIVE TEST: RDP server provisioning started via API: Performance for user 999777",
            "hosting",
            {
                "user_id": 999777,
                "server_id": 9999,
                "instance_id": "test-vultr-xyz-123",
                "plan": "Performance",
                "region": "ewr",
                "hostname": "test-rdp-999777"
            }
        )
        results.append({
            "test": "RDP Provisioning Start",
            "sent": success,
            "type": "INFO"
        })
    except Exception as e:
        results.append({
            "test": "RDP Provisioning Start",
            "sent": False,
            "error": str(e),
            "type": "INFO"
        })
    
    # Test 4: RDP Provisioning Success (API)
    try:
        success = await send_info_alert(
            "TEST_RDP_API",
            "✅ LIVE TEST: RDP server provisioned successfully via API: Performance for user 999777",
            "hosting",
            {
                "user_id": 999777,
                "server_id": 9999,
                "instance_id": "test-vultr-xyz-123",
                "plan": "Performance",
                "region": "ewr",
                "public_ip": "45.76.200.100"
            }
        )
        results.append({
            "test": "RDP Provisioning Success",
            "sent": success,
            "type": "INFO"
        })
    except Exception as e:
        results.append({
            "test": "RDP Provisioning Success",
            "sent": False,
            "error": str(e),
            "type": "INFO"
        })
    
    # Test 5: RDP Provisioning Failure (API)
    try:
        success = await send_error_alert(
            "TEST_RDP_API",
            "❌ LIVE TEST: RDP provisioning failed via API for user 999666",
            "hosting",
            {
                "user_id": 999666,
                "server_id": 9998,
                "instance_id": "test-vultr-fail-456",
                "error": "Vultr API timeout after 600 seconds"
            }
        )
        results.append({
            "test": "RDP Provisioning Failure",
            "sent": success,
            "type": "ERROR"
        })
    except Exception as e:
        results.append({
            "test": "RDP Provisioning Failure",
            "sent": False,
            "error": str(e),
            "type": "ERROR"
        })
    
    # Calculate summary
    total_tests = len(results)
    successful_sends = sum(1 for r in results if r.get("sent", False))
    
    return success_response({
        "test_results": results,
        "summary": {
            "total_tests": total_tests,
            "successful_sends": successful_sends,
            "failed_sends": total_tests - successful_sends,
            "success_rate": f"{(successful_sends/total_tests*100):.1f}%"
        },
        "message": "Check admin Telegram for 5 test notifications" if successful_sends > 0 else "No notifications sent - check admin configuration"
    })
