"""Speech to text providers.

Each module has
  LABEL, CLOUD                      name, and whether it runs in the cloud
  ACCOUNT                           cloud: its entry in the keyring (providers.api_key)
  transcribe(pcm, rate, language)   16 bit mono PCM -> text; raises ProviderError
  prepare()                         loads what it needs before the first use (may take long)

To add a provider: a module here and an entry in PROVIDERS.
"""

from . import elevenlabs, whisper

PROVIDERS = {"whisper": whisper, "elevenlabs": elevenlabs}
LOCAL = whisper      # takes over when a cloud provider fails


def get(name):
    return PROVIDERS.get(name, LOCAL)
