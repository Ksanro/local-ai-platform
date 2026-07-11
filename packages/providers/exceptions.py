"""Provider layer exceptions."""


class ProviderError(Exception):
    """Base provider error."""


class UnknownProviderError(ProviderError):
    """Raised when a provider name is not registered."""


class ProviderConnectionError(ProviderError):
    """Raised when a provider connection fails."""


class ProviderAuthenticationError(ProviderError):
    """Raised when provider authentication fails."""


class ProviderResponseError(ProviderError):
    """Raised when a provider returns an invalid response."""
