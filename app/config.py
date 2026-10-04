from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    wa_provider: str = "meta"

    meta_phone_number_id: str = ""
    meta_access_token: str = ""
    meta_app_secret: str = ""
    meta_verify_token: str = "change-me"
    meta_graph_version: str = "v21.0"

    d360_api_key: str = ""
    # Shared secret for providers that do not sign their webhooks. Sent as
    # ?token=... on the callback URL. Required whenever WA_PROVIDER is not meta.
    webhook_token: str = ""

    # Which model writes the words. The price-safety guarantees are enforced in
    # code, not by the model, so either provider is safe.
    llm_provider: str = "anthropic"  # anthropic | openai
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    # The classifier decides intent, language and confidence — get that wrong and
    # everything downstream is wrong. A stronger model here is worth the few cents;
    # the cheap model still writes the wording (compose).
    openai_classify_model: str = "gpt-4o"

    database_url: str = "sqlite:///./sakan.db"
    db_pool_size: int = 5
    db_max_overflow: int = 10
    admin_user: str = "admin"
    admin_password: str = "change-me"
    timezone: str = "Asia/Dubai"
    # Shown on the public privacy policy, which Meta requires before app review.
    operator_name: str = "the operator of this service"
    operator_email: str = ""
    # The sales/demo contact shown on the public landing page CTA. A WhatsApp
    # number (digits only, no plus) is preferred; the page falls back to the
    # email, then to no link at all. This is Mistri's own number, never a
    # garage's — so a garage number never leaks onto the generic product page.
    operator_whatsapp: str = ""
    # Used to build the owner's edit link inside onboarding nudge messages, where
    # there is no incoming request to read the host from.
    public_base_url: str = "https://mistri.offpageos.com"
    handoff_pause_hours: int = 2
    handoff_auto_release_hours: int = 24
    # Per conversation, per day. A runaway loop or a nuisance sender should cost
    # a capped amount of money and end up with a human, not run all night.
    max_replies_per_day: int = 40
    # Off in tests and in a shell; the running service turns it on.
    enable_scheduler: bool = True


settings = Settings()
