from transcriber.hosted.errors import Forbidden, NotFound, to_response


def test_to_response_maps_status_and_body() -> None:
    assert to_response(NotFound("nope"))["statusCode"] == 404
    assert to_response(Forbidden("no"))["statusCode"] == 403
    body = to_response(NotFound("missing job"))
    assert '"error"' in body["body"] and "missing job" in body["body"]


def test_unknown_error_is_500_without_leaking_message() -> None:
    r = to_response(RuntimeError("secret internals"))
    assert r["statusCode"] == 500
    assert "secret internals" not in r["body"]   # no internal leak (F8)
