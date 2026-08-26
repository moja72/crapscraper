from app.updates.sources import classify_source_error
def test_credits_and_auth_are_not_confused():
    credit=classify_source_error("PluginTheme",status=403,body='{"credits":0}');auth=classify_source_error("UltraPackV2",status=401,body="unauthorized")
    assert credit.code=="insufficient_credits" and "PluginTheme" in credit.message
    assert auth.code=="authentication_access" and auth.code!="insufficient_credits" and "UltraPackV2" in auth.message
