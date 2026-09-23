"""
Centralized configuration for DevAgent.
Reads from environment variables / .env file.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # GitHub
    github_token: str = ""              # Personal access token or GitHub App installation token
    github_webhook_secret: str = ""     # Secret configured on the GitHub webhook

    # LLM
    # LLM
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = ""   # leave blank for OpenAI itself; set to
                                 # "https://api.groq.com/openai/v1" to use Groq instead

    # App
    app_env: str = "development"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
