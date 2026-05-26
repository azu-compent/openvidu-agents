# speech-processing

AI services for transcribing, translating and summarizing video conference conversations. See [https://openvidu.io/latest/docs/agents/speech-processing/].

## STT Provider Implementation Guide

This guide explains how to add a new STT provider to the speech-processing agent.

### Overview

The STT provider system uses a **centralized registry pattern** that ensures:
- Single source of truth for all providers
- Automatic validation at boot time
- No duplication of provider lists across the codebase

### Architecture

#### 1. Registry (`STT_PROVIDERS`)

Located at the top of `stt_impl.py`, this dictionary defines all supported providers:

```python
STT_PROVIDERS = {
    "provider_name": STTProviderConfig(
        impl_function=None,  # Set during initialization
        plugin_module="livekit.plugins.provider",
        plugin_class="STT",
    ),
}
```

#### 2. Implementation Functions

Each provider requires a `get_<provider>_stt_impl(agent_config)` function that:
- Validates configuration
- Creates and returns the STT instance

#### 3. Automatic Validation

At module load time, `_initialize_stt_registry()` validates that:
- Every registry entry has an implementation function
- Every implementation function has a registry entry

**If validation fails, the application won't start.**

### Adding a New Provider

#### Step 1: Add to Registry

Add your provider to the `STT_PROVIDERS` dictionary in `stt_impl.py`:

```python
STT_PROVIDERS = {
    # ... existing providers ...
    "newprovider": STTProviderConfig(
        impl_function=None,
        plugin_module="livekit.plugins.newprovider",
        plugin_class="STT",  # or custom class name
    ),
}
```

**Configuration:**
- `plugin_module`: The Python module path for the plugin
- `plugin_class`: The class name (usually "STT", but can vary like "WizperSTT" for FAL)

#### Step 2: Implement the Function

Create the implementation function in `stt_impl.py`:

```python
def get_newprovider_stt_impl(agent_config) -> stt.STT:
    from livekit.plugins import newprovider

    config_manager = ConfigManager(agent_config, "live_captions.newprovider")
    
    # Validate required credentials
    api_key = config_manager.mandatory_value(
        "api_key",
        "Wrong NewProvider credentials. live_captions.newprovider.api_key must be set"
    )
    
    # Get optional parameters
    language = config_manager.configured_string_value("language")
    model = config_manager.configured_string_value("model")
    
    # Build kwargs, excluding NOT_PROVIDED values
    kwargs = {
        k: v
        for k, v in {
            "language": language,
            "model": model,
        }.items()
        if v is not NOT_PROVIDED
    }
    
    # Return configured STT instance
    return newprovider.STT(api_key=api_key, **kwargs)
```

#### Step 3: Update Registry Initialization

Add your implementation function to the `provider_impl_map` in `_initialize_stt_registry()`:

```python
def _initialize_stt_registry():
    provider_impl_map = {
        # ... existing providers ...
        "newprovider": get_newprovider_stt_impl,
    }
    # ... rest of function ...
```

#### Step 4: Add Configuration Schema

Add the configuration section to `agent-speech-processing.yaml`:

```yaml
live_captions:
  provider: # ... existing providers or newprovider
  
  # ... existing provider configs ...
  
  newprovider:
    # API key for NewProvider. See https://newprovider.com/api-keys
    api_key:
    # The language code to use for transcription (e.g., "en" for English)
    language:
    # The model to use for transcription
    model:
```

#### Step 5: Install Dependencies

Add the plugin to `requirements.txt`:

```txt
livekit-agents[silero,turn_detector,...,newprovider]==1.5.8
```

Or install separately:

```bash
pip install livekit-plugins-newprovider
```

#### Step 6: Test

Run the validation script:

```bash
python3 test_stt_registry.py
```

This will verify:
- Registry is properly initialized
- All providers have implementation functions
- No orphaned implementations

### What Happens if You Forget Something?

#### If you add to registry but forget the implementation:

```
RuntimeError: Missing implementation functions for STT providers: newprovider. 
Please implement get_{provider}_stt_impl() functions for these providers.
```

#### If you add implementation but forget the registry:

```
RuntimeError: Implementation functions exist for unregistered STT providers: newprovider. 
Please add these providers to the STT_PROVIDERS registry.
```

#### If you use an unknown provider at runtime:

```
ValueError: Unknown STT provider: newprovider. 
Supported providers: assemblyai, aws, azure, ...
```

### Benefits of This Approach

1. **Single Source of Truth**: Provider list is defined once in `STT_PROVIDERS`
2. **Boot-time Validation**: Errors are caught immediately when the module loads
3. **Type Safety**: Registry includes plugin module and class information
4. **Maintainability**: Adding a provider is a clear, documented process. Upgrading livekit-plugins is safe, as breaking changes will be caught
5. **Auto-discovery**: Language defaults are automatically discovered from plugin constructors
6. **No Duplication**: No need for long if-elif chains or multiple provider lists

### Example: Real Implementation

See any existing provider like `get_aws_stt_impl()`, `get_openai_stt_impl()`, etc. for complete examples.

## Per-room language override (Azure)

When the agent is dispatched in **manual** mode
(`live_captions.processing: manual`), the dispatching application can override
`live_captions.azure.language` per room by passing a JSON object in the
LiveKit Agent Dispatch `metadata` field.

### Metadata contract

The `metadata` string must parse as a JSON object. The agent reads the
`language` key and ignores everything else.

| Value of `language` | Effect |
|---|---|
| Non-empty string (e.g. `"es-ES"`) | Override Azure STT with this language. |
| Non-empty list of strings (e.g. `["en-US", "es-ES"]`) | Override with this candidate list (Azure auto-detects within it). |
| Missing, `null`, or omitted entirely | Fall back to `live_captions.azure.language` from the YAML. |
| Any other type, empty string, or empty list | Logged as a warning and treated as if `language` were omitted. |

Invalid JSON in `metadata` is also treated as omitted (logged as a warning).
The session always starts; metadata is purely additive.

### Example

Python backend (using `livekit-api`):

```python
from livekit import api

dispatch = await lk_api.agent_dispatch.create_dispatch(
    api.CreateAgentDispatchRequest(
        agent_name="speech-processing",
        room="room-123",
        metadata='{"language": "es-ES"}',
    )
)
```

### Scope

Only the Azure provider's `language` is overridable today. Other providers
and other config keys still come exclusively from the YAML. See the
[`live_captions.azure.language` reference](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=stt#supported-languages)
for valid Azure language codes.

## Building & publishing the cloud image to your own Docker Hub

This is the exact flow for building the **cloud** STT image from this fork and
publishing it under your own Docker Hub account. The cloud image is built in two
stages: a shared `base` image, then the `cloud` image on top of it.

Replace these two values with your own throughout:

| Placeholder | Example used below |
|---|---|
| `<DOCKER_USER>` — your Docker Hub username | `azucompent` |
| `<TAG>` — the image tag you want to publish | `3.7.0` |

All commands are run from the `speech-processing/` directory:

```bash
cd speech-processing
```

### Step 1 — Log in to Docker Hub

```bash
docker login
```

### Step 2 — Build the base image (local only, not pushed)

The base image is the parent of the cloud image. It gets baked into the cloud
image's layers, so it does **not** need to be pushed — building it locally is
enough.

```bash
docker buildx build \
  --platform linux/amd64 \
  --load \
  -f Dockerfile.base \
  -t azucompent/agent-speech-processing-base:3.7.0 \
  .
```

### Step 3 — Build the cloud image on top of your base

The cloud Dockerfile defaults its `BASE_IMAGE` to the upstream
`openvidu/agent-speech-processing-base:main`. Override it with `--build-arg` so
it builds on the base you just made:

```bash
docker buildx build \
  --platform linux/amd64 \
  --load \
  -f Dockerfile.cloud \
  --build-arg BASE_IMAGE=azucompent/agent-speech-processing-base:3.7.0 \
  -t azucompent/agent-speech-processing-cloud:3.7.0 \
  .
```

### Step 4 — Push the cloud image

```bash
docker push azucompent/agent-speech-processing-cloud:3.7.0
```

Then pull/deploy it with:

```bash
docker pull azucompent/agent-speech-processing-cloud:3.7.0
```

### Notes

- **Architecture:** the commands above build for `linux/amd64` only. To produce a
  multi-arch image (e.g. for ARM servers like AWS Graviton or Apple Silicon),
  build and push in one step with buildx instead of `--load`:

  ```bash
  docker buildx build \
    --platform linux/amd64,linux/arm64 \
    -f Dockerfile.cloud \
    --build-arg BASE_IMAGE=azucompent/agent-speech-processing-base:3.7.0 \
    -t azucompent/agent-speech-processing-cloud:3.7.0 \
    --push \
    .
  ```

  Multi-arch images cannot be `--load`ed into the local Docker daemon; they must
  be pushed directly. The base image would also need a multi-arch build in that
  case.
- **Transient push errors:** `docker push` is idempotent — if it fails partway
  with `unexpected EOF` or a daemon-connection error, just rerun the same push
  command. Already-uploaded layers report `Layer already exists` and are skipped.
- **Vosk (offline) images** are built separately via `./build-vosk.sh` (run
  `./download-models.sh` first). See that script's `--help` for options.