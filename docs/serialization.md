# Serialization Layer

## Overview

The Serialization Layer is a first-class platform component responsible for translating
platform models into provider-specific request formats.

It sits between the Context Package (produced by Repository Intelligence) and the
Provider layer (which executes inference).

## Architecture

```
Repository Intelligence
       |
       v
ContextPackage
       |
       v
SerializerFactory
       |
       v
ProviderSerializer
       |
       v
ProviderRequest
       |
       v
Provider
       |
       v
LLM
```

### Data Flow

1. **ContextPackage** — platform model produced by the Context Builder.
   Provider-independent. Contains query, symbols, modules, and metadata.

2. **Serializer** — translates ContextPackage + user messages into
   ProviderRequest. Each serializer owns formatting for one provider.

3. **ProviderRequest** — provider-specific request payload.
   Contains messages, model, and parameters formatted for the target provider.

4. **Provider** — executes inference using ProviderRequest.
   Handles HTTP, streaming, retries, and authentication.

5. **LLM** — the external language model service.

## Why Serialization is Independent of Providers

The platform is provider-agnostic. Internal components must never know how
OpenAI, Anthropic, vLLM, or future providers expect requests to be formatted.

Instead, a dedicated Serialization Layer translates platform models into
provider-specific request models.

This separation provides:

- **Provider independence** — internal components never depend on provider schemas.
- **Extensibility** — new providers require only a new serializer, no changes to
  Context Builder, Repository Intelligence, or existing providers.
- **Testability** — serializers are pure functions, easily testable in isolation.
- **Determinism** — identical input always produces identical output.

## ProviderRequest

`ProviderRequest` is the boundary between the Serialization Layer and the
Provider Layer.

```python
@dataclass(frozen=True)
class ProviderRequest:
    provider_type: ProviderType
    messages: list[dict[str, Any]]
    model: str = "default"
    kwargs: dict[str, Any] = field(default_factory=dict)
```

### Responsibilities

- Carry formatted messages for the target provider.
- Carry model identifier and additional parameters.
- Remain independent of HTTP transport concerns (headers, retries, auth).

### Constraints

- No HTTP headers (transport concern).
- No authentication data (provider concern).
- No retry configuration (provider concern).
- No streaming configuration (provider concern).

### Usage

```python
from packages.serializers.models import ProviderRequest
from packages.serializers.types import ProviderType

request = ProviderRequest(
    provider_type=ProviderType.openai,
    messages=[{"role": "user", "content": "Hello"}],
    model="gpt-4",
    kwargs={"temperature": 0.7},
)

# Convert to flat dict for provider consumption
payload = request.to_dict()
# {"messages": [...], "model": "gpt-4", "temperature": 0.7}
```

## Serializer Lifecycle

```
1. SerializerFactory.create(ProviderType.openai)
       |
       v
2. SerializerRegistry lookup
       |
       v
3. OpenAISerializer instance created
       |
       v
4. serializer.serialize(context_package, messages)
       |
       v
5. ProviderRequest returned
       |
       v
6. Provider consumes ProviderRequest
```

### Step 1: Factory Creation

```python
from packages.serializers.factory import SerializerFactory
from packages.serializers.types import ProviderType

serializer = SerializerFactory.create(ProviderType.openai)
```

The factory looks up the serializer class in the registry and instantiates it.
Each call returns a fresh instance.

### Step 2: Registry Lookup

The registry maintains a global mapping of `ProviderType` to serializer classes.
Serializers are registered automatically when their module is imported.

### Step 3: Serialization

```python
from packages.context.package import ContextPackage

context_package = ContextPackage(
    query="authentication middleware",
    modules=["auth.py"],
    symbols=["auth.AuthenticationMiddleware"],
)

messages = [
    {"role": "user", "content": "How does auth work?"},
]

provider_request = serializer.serialize(
    context_package=context_package,
    messages=messages,
)
```

### Step 4: Provider Consumption

The provider consumes `ProviderRequest` and executes inference.
Providers never consume `ContextPackage`.

## Message Ordering

Serializers follow strict ordering rules:

```
System Message
      |
      v
Repository Context
      |
      v
Original User Messages
```

### Rules

1. **Exactly one platform system message** — describes the platform's role.
2. **Repository context** — included only when `ContextPackage` contains symbols.
3. **User messages** — copied unchanged, preserving order, roles, and content.

### Empty Context

If `ContextPackage is None` or no symbols are selected, repository context
is omitted. A valid `ProviderRequest` is still generated.

## Factory

`SerializerFactory` mirrors the `ProviderFactory` design pattern.

```python
class SerializerFactory:
    @staticmethod
    def create(provider_type: ProviderType) -> ProviderSerializer:
        ...
```

### Responsibilities

- Create serializers by provider type.
- Use the registry for lookup.
- Hide implementation details.
- Raise `UnknownSerializerError` for unregistered types.

## Registry

`SerializerRegistry` maintains the global mapping of provider types to
serializer classes.

```python
from packages.serializers.registry import register, get_registry, has_serializer

register(ProviderType.openai, OpenAISerializer)
registry = get_registry()
has_serializer(ProviderType.openai)  # True
```

### Responsibilities

- Register serializers by provider type.
- Look up serializers by provider type.
- Prevent duplicate registrations (raises `ValueError`).
- Deterministic behaviour.

### Methods

| Method | Description |
|---|---|
| `register(type, class)` | Register a serializer class |
| `get_registry()` | Return a copy of the registry |
| `has_serializer(type)` | Check if registered |
| `unregister(type)` | Remove a serializer |

## Extension Strategy

Adding a new serializer requires:

1. Create a new serializer class inheriting from `ProviderSerializer`.
2. Implement `provider` property and `_serialize()` method.
3. Register at import time: `register(ProviderType.new_type, NewSerializer)`.

No changes to Context Builder, Repository Intelligence, or Providers
should be required.

### Example: Adding AnthropicSerializer

```python
from packages.serializers.base import ProviderSerializer
from packages.serializers.models import ProviderRequest
from packages.serializers.registry import register
from packages.serializers.types import ProviderType

class AnthropicSerializer(ProviderSerializer):
    @property
    def provider(self) -> ProviderType:
        return ProviderType.anthropic

    def _serialize(self, context_package, messages):
        # Convert to Anthropic Messages API format
        ...
        return ProviderRequest(
            provider_type=ProviderType.anthropic,
            messages=anthropic_messages,
        )

register(ProviderType.anthropic, AnthropicSerializer)
```

### Adding a New ProviderType

1. Add a new member to `ProviderType` enum.
2. Create the serializer class.
3. Register it in the registry.

## OpenAI Serializer

The `OpenAISerializer` converts platform models into OpenAI Chat Completions
format.

### Formatting Rules

- System message describes the platform's role.
- Repository context includes symbols and modules.
- User messages are copied unchanged.

### Determinism

Serialization is deterministic:

- No timestamps.
- No UUIDs.
- No random ordering.
- No dynamic metadata.

Identical input always produces identical output.

## Constraints

### Serializers Must Not

- Access repositories.
- Access the filesystem.
- Parse source code.
- Inspect AST.
- Perform ranking.
- Estimate tokens.
- Call providers.
- Perform HTTP.
- Stream responses.

### Providers Must Not

- Format repository context.
- Understand ContextPackage.
- Perform serialization.

## Out of Scope

- Anthropic serializer (future).
- DSPARK serializer (future).
- Gemini serializer (future).
- Ollama serializer (future).
- LM Studio serializer (future).
- Prompt optimization.
- Context compression.
- Memory injection.
- Tool calling.
- Function calling.

## Future Evolution

Future serializers may include:

- `AnthropicSerializer` — Anthropic Messages API format.
- `DSPARKSerializer` — DSPARK format.
- `GeminiSerializer` — Google Gemini format.
- `OllamaSerializer` — Ollama format.
- `LMSerializer` — LM Studio format.

No changes to existing components should be required when introducing
new serializers.
