from app.security import generate_api_key, hash_api_key


def test_generate_api_key_shape():
    full_key, prefix, key_hash = generate_api_key()
    assert full_key.startswith(prefix)
    assert prefix.startswith("al_live_")
    assert key_hash == hash_api_key(full_key)


def test_generate_api_key_is_unique_each_call():
    key1, prefix1, _ = generate_api_key()
    key2, prefix2, _ = generate_api_key()
    assert key1 != key2
    assert prefix1 != prefix2


def test_hash_api_key_is_deterministic():
    assert hash_api_key("same-secret") == hash_api_key("same-secret")


def test_hash_api_key_differs_for_different_input():
    assert hash_api_key("secret-a") != hash_api_key("secret-b")
