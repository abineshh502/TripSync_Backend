class Settings:
    DEBUG: bool = True
    CORS_ORIGINS: list = ["*"]
    FIREBASE_CREDS_PATH: str = "firebase-adminsdk.json"

settings = Settings()
