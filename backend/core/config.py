from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Intelligent Code Analyzer"
    version: str = "0.1.0"
    allow_origins: list[str] = ["http://localhost:3000"]
    allow_credentials: bool = True
    allow_methods: list[str] = ["*"]
    allow_headers: list[str] = ["*"]

    database_url: str = "sqlite:///./analyzer.db"

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = "http://localhost:8000/github/callback"
    frontend_url: str = "http://localhost:3000"

    # Comma-separated emails that are auto-promoted to admin on startup.
    admin_emails: str = ""

    model_config = {"env_file": "backend/.env"}


settings = Settings()
