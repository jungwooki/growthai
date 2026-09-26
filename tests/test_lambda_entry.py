import asyncio
from types import SimpleNamespace
from backend import server
from backend.web_access import WebAccess


def test_lambda_url_health_and_authenticated_route(monkeypatch):
    from backend.lambda_entry import handler
    monkeypatch.setattr(server, 'ACCESS', WebAccess(True, frozenset({'test.lambda-url.ap-southeast-2.on.aws'}), 'doctor', 'long-test-password-1234'))
    event = dict(version='2.0', routeKey='$default', rawPath='/healthz', rawQueryString='',
                 headers={'host':'test.lambda-url.ap-southeast-2.on.aws','x-forwarded-proto':'https'},
                 requestContext={'http':{'method':'GET','path':'/healthz','sourceIp':'127.0.0.1','protocol':'HTTP/1.1'},
                                 'domainName':'test.lambda-url.ap-southeast-2.on.aws'},
                 isBase64Encoded=False)
    asyncio.set_event_loop(asyncio.new_event_loop())
    try:
        assert handler(event, SimpleNamespace())['statusCode'] == 200
        event['rawPath'] = event['requestContext']['http']['path'] = '/api/budget'
        assert handler(event, SimpleNamespace())['statusCode'] == 401
    finally:
        asyncio.get_event_loop().close()
        asyncio.set_event_loop(None)
