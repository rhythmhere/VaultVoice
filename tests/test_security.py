"""Fast, service-isolated regression tests for the survivor-facing API."""

import base64
import inspect
import asyncio
import io
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from fastapi.testclient import TestClient
from starlette.datastructures import Headers, UploadFile

from backend import main
from backend.storage import ObjectStorage


class FakeSession:
    def __init__(self, case=None):
        self.case = case

    def get(self, model, identifier):
        return self.case if self.case and identifier == self.case.case_id else None

    def scalar(self, query):
        return None


def test_disallowed_and_mismatched_files_are_rejected_before_storage():
    assert not main.has_valid_file_signature(b"not an image", "image/png")
    assert not main.has_valid_file_signature(b"MZ\x00\x00", "application/pdf")
    assert main.has_valid_file_signature(b"%PDF-1.7\n", "application/pdf")


def test_oversized_file_is_rejected_before_storage():
    class Storage:
        called = False
        def put_encrypted(self, *args, **kwargs): self.called = True
    old_limit = main.settings.max_upload_bytes
    main.settings.max_upload_bytes = 4
    storage = Storage()
    upload = UploadFile(file=io.BytesIO(b"%PDF-1.7\n"), filename="evidence.pdf", headers=Headers({"content-type": "application/pdf"}))
    try:
        request = Request({"type": "http", "method": "POST", "path": "/", "headers": [], "query_string": b"", "client": ("test", 1), "server": ("test", 80), "scheme": "http"})
        with pytest.raises(HTTPException) as exc:
            asyncio.run(main.upload_evidence(request, "VV-TEST", upload, "", None, FakeSession(SimpleNamespace(case_id="VV-TEST", evidence=[])), SimpleNamespace(), storage))
            assert exc.value.status_code == 401
        assert not storage.called
    finally:
        main.settings.max_upload_bytes = old_limit


def test_encrypted_storage_round_trip_without_exposing_key():
    key = base64.urlsafe_b64encode(b"k" * 32).decode()

    class Client:
        objects = {}

        def put_object(self, bucket, object_key, stream, length, **kwargs):
            self.objects[object_key] = stream.read()

        def get_object(self, bucket, object_key):
            class Response:
                def __init__(self, content): self.content = content
                def read(self): return self.content
                def close(self): pass
                def release_conn(self): pass
            return Response(self.objects[object_key])

    settings = SimpleNamespace(minio_endpoint="unused", minio_access_key="a", minio_secret_key="b", minio_secure=False, minio_bucket="vault", encryption_key=key)
    storage = ObjectStorage(settings)
    storage.client = Client()
    plaintext = b"private evidence"
    storage.put_encrypted("VV-TEST/file", plaintext, "text/plain")
    assert storage.client.objects["VV-TEST/file"] != plaintext
    assert storage.get_decrypted("VV-TEST/file") == plaintext
    assert "encryption_key" not in main.evidence_json.__code__.co_names
    assert "VAULTVOICE_ENCRYPTION_KEY" not in inspect.getsource(main.serialize_case)


def test_case_id_is_required_for_evidence_lookup():
    with pytest.raises(HTTPException) as exc:
        main.download_evidence(Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b"", "client": ("test", 1), "server": ("test", 80), "scheme": "http"}), "VV-GUESS", 1, FakeSession(), SimpleNamespace(get_decrypted=lambda _: b""))
        assert exc.value.status_code == 401


def test_case_retrieval_rate_limit_triggers():
    case = SimpleNamespace(case_id="VV-TEST")
    app = main.app
    def db_override():
        yield FakeSession(case)
    app.dependency_overrides[main.get_db] = db_override
    original = main.serialize_case
    original_session_local = main.SessionLocal
    original_seed = main.seed_organizations
    original_storage_service = main.storage_service
    class DBContext:
        def __enter__(self): return FakeSession(case)
        def __exit__(self, *args): pass
    main.SessionLocal = lambda: DBContext()
    main.seed_organizations = lambda session: None
    main.storage_service = lambda: SimpleNamespace(ensure_bucket=lambda: None)
    main.serialize_case = lambda session, value: {"case_id": value.case_id}
    try:
        with TestClient(app) as client:
            responses = [client.get("/api/cases/VV-TEST") for _ in range(31)]
        assert any(response.status_code == 429 for response in responses)
    finally:
        main.serialize_case = original
        main.SessionLocal = original_session_local
        main.seed_organizations = original_seed
        main.storage_service = original_storage_service
        app.dependency_overrides.clear()


def test_report_and_upload_routes_are_rate_limited():
    protected = {
        "/api/cases": "POST",
        "/api/cases/{identifier}": "GET",
        "/api/cases/{identifier}/evidence": "POST",
    }
    routes = {(route.path, method): route for route in main.app.routes for method in getattr(route, "methods", set())}
    for key in protected:
        assert "__wrapped__" in getattr(routes[(key, protected[key])].endpoint, "__dict__", {})


def test_case_token_is_scoped_to_the_requested_case_for_survivor_routes():
    case_a = SimpleNamespace(case_id="VV-AAAA1111")
    case_b = SimpleNamespace(case_id="VV-BBBB2222")
    token_a = "token-a"
    token_b = "token-b"
    records = {
        token_a: SimpleNamespace(case_id=case_a.case_id, case=case_a, is_active=True, expires_at=datetime.now(timezone.utc) + timedelta(hours=1)),
        token_b: SimpleNamespace(case_id=case_b.case_id, case=case_b, is_active=True, expires_at=datetime.now(timezone.utc) + timedelta(hours=1)),
    }

    class Sessions:
        def get(self, model, identifier):
            if model is main.CaseSession:
                return records.get(identifier)
            return {case_a.case_id: case_a, case_b.case_id: case_b}.get(identifier)

    def request(value):
        return Request({"type": "http", "method": "PATCH", "path": "/", "headers": [(b"authorization", value.encode())], "query_string": b"", "client": ("test", 1), "server": ("test", 80), "scheme": "http"})

    assert main.require_survivor_case(request("Bearer token-a"), case_a.case_id, Sessions()) is case_a
    with pytest.raises(HTTPException) as wrong_case:
        main.require_survivor_case(request("Bearer token-a"), case_b.case_id, Sessions())
    assert wrong_case.value.status_code == 401
    with pytest.raises(HTTPException) as missing:
        main.require_survivor_case(request(""), case_a.case_id, Sessions())
    assert missing.value.status_code == 401


def test_sos_token_cannot_access_another_alert():
    first = SimpleNamespace(id="sos-a", access_token_hash=main.token_hash("sos-token-a"))
    second = SimpleNamespace(id="sos-b", access_token_hash=main.token_hash("sos-token-b"))

    class Sessions:
        def get(self, model, identifier):
            return {first.id: first, second.id: second}.get(identifier)

    with pytest.raises(HTTPException) as wrong_owner:
        main.current_sos_owner(second.id, "sos-token-a", Sessions())
    assert wrong_owner.value.status_code == 401
