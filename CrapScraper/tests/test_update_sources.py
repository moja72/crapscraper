from app.updates.sources import classify_source_error

def test_explicit_credit_response_is_normalized_per_source():
    error=classify_source_error("PluginTheme",status=403,body='{"credits":0}')
    assert error.code=="insufficient_credits" and "PluginTheme" in error.message and "UltraPack" not in error.message

def test_plain_401_is_authentication_not_credit():
    error=classify_source_error("UltraPackV2",status=401,body="unauthorized")
    assert error.code=="authentication_access" and "UltraPackV2" in error.message
