import hashlib
from collections.abc import Iterable


def calculate_sha256(chunks: Iterable[bytes]) -> str:
    sha256 = hashlib.sha256()

    for chunk in chunks:
        sha256.update(chunk)

    return sha256.hexdigest()