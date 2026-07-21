"""Provider layer exceptions.

Defines a hierarchy of exceptions for different failure modes
in the provider layer (connection, auth, response, unknown).
"""


class ProviderError(Exception):
    """Base provider error.

    All provider-specific exceptions inherit from this class
    so they can be caught collectively.
    """


class UnknownProviderError(ProviderError):
    """Raised when a provider name is not registered in the registry."""


class ProviderConnectionError(ProviderError):
    """Raised when a provider connection fails.

    Covers network timeouts, connection refused, and similar
    transport-level failures.
    """


class ProviderAuthenticationError(ProviderError):
    """Raised when provider authentication fails.

    Typically triggered by invalid or expired API keys (HTTP 401).
    """


class ProviderResponseError(ProviderError):
    """Raised when a provider returns an invalid response.

    Covers non-2xx HTTP status codes and malformed responses.
    """


class UnknownModelError(ProviderError):
    """Raised when a model is not found in the model registry.

    Attributes:
        model: The model string that was not found.
        available_models: List of available model names.
    """

    def __init__(self, model: str, available_models: list[str]) -> None:
        """Initialize with the unknown model and available models.

        Args:
            model: The model string that was not found.
            available_models: List of available model names.
        """
        super().__init__(f"Unknown model '{model}'")
        self.model = model
        self.available_models = available_models
