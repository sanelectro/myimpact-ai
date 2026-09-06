from app.config.settings import LLMProvider, get_settings


def test_default_application_settings():

    settings = get_settings()

    assert settings.app_name == "MyImpact AI"
    assert settings.app_version == "0.1.0"
    assert settings.app_env == "development"
    assert settings.ai_service_port == 8000




def test_llm_provider_is_configured():

    settings = get_settings()

    assert settings.llm_provider in [provider.value for provider in LLMProvider]

def test_groq_configuration():

    settings = get_settings()

    assert settings.groq_base_url == "https://api.groq.com/openai/v1"
    assert settings.groq_model != ""