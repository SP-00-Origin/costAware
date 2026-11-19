"""Record provider status without copying response bodies or credentials into logs."""
from http import HTTPStatus


def error_details(exc):
    code = getattr(exc, "code", None)
    if type(code) is not int:
        code = getattr(exc, "status_code", None)
    if type(code) is not int or not 400 <= code <= 599:
        return None
    try:
        reason = HTTPStatus(code).phrase
    except ValueError:
        reason = "Provider HTTP error"
    return {"http_status": code, "reason": reason}


def public_error(name, details):
    if details:
        return f'{name} (HTTP {details["http_status"]} {details["reason"]})'
    return name
