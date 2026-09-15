from pydantic_settings import BaseSettings


class FaceSwapSettings(BaseSettings):
    api_base_url: str = "http://127.0.0.1:8001"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_prefix = "FACESWAP_"
        extra = "ignore"


faceswap_settings = FaceSwapSettings()
