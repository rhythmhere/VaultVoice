import base64
import hashlib
import io
import secrets
from datetime import timedelta

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from minio import Minio

from .config import Settings


class ObjectStorage:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = Minio(settings.minio_endpoint, access_key=settings.minio_access_key, secret_key=settings.minio_secret_key, secure=settings.minio_secure)

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.settings.minio_bucket):
            self.client.make_bucket(self.settings.minio_bucket)

    def key(self) -> bytes:
        if not self.settings.encryption_key:
            raise RuntimeError("VAULTVOICE_ENCRYPTION_KEY is required")
        decoded = base64.urlsafe_b64decode(self.settings.encryption_key.encode())
        if len(decoded) != 32:
            raise RuntimeError("VAULTVOICE_ENCRYPTION_KEY must decode to 32 bytes")
        return decoded

    def put_encrypted(self, object_key: str, content: bytes, content_type: str) -> str:
        nonce = secrets.token_bytes(12)
        encrypted = nonce + AESGCM(self.key()).encrypt(nonce, content, None)
        self.client.put_object(self.settings.minio_bucket, object_key, io.BytesIO(encrypted), len(encrypted), content_type="application/octet-stream", metadata={"X-Amz-Meta-Integrity-Hash": hashlib.sha256(content).hexdigest()})
        return object_key

    def get_decrypted(self, object_key: str) -> bytes:
        response = self.client.get_object(self.settings.minio_bucket, object_key)
        try:
            encrypted = response.read()
        finally:
            response.close()
            response.release_conn()
        return AESGCM(self.key()).decrypt(encrypted[:12], encrypted[12:], None)

    def presigned_url(self, object_key: str) -> str:
        """Return a short-lived URL for the encrypted object.

        The object remains ciphertext; normal survivor-facing downloads use
        the API decrypt-and-stream endpoint above.
        """
        return self.client.presigned_get_object(self.settings.minio_bucket, object_key, expires=timedelta(minutes=5))
