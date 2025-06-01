try:
    import bcrypt
except ImportError:
    pass
else:

    def hash_password(password: bytes, salt: bytes | None = None) -> bytes:
        salt = bcrypt.gensalt() if salt is None else salt
        return bcrypt.hashpw(password, salt)

    def verify_password(password: bytes, hashed: bytes) -> bool:
        return bcrypt.checkpw(password, hashed)
