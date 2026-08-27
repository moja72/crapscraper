def safe_log(value,*secrets):
    text=str(value)
    for secret in secrets:
        if secret:text=text.replace(secret,"[REDACTED]")
    return text
