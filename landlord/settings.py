from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="LANDLORD_")

    db_backend: str = "sqlite"
    db_path: str = "landlord.db"
    db_url: str = ""

    storage_backend: str = "local"
    storage_local_path: str = "./invoices"

    s3_bucket: str = ""
    s3_region: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_endpoint_url: str = ""
    s3_presigned_expiry: int = 604800  # 7 days in seconds

    pix_key: str = ""
    pix_merchant_name: str = ""
    pix_merchant_city: str = ""

    secret_key: str = "change-me-in-production"


settings = Settings()
