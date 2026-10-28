"""Text to speech providers.

Each module has
  LABEL, CLOUD          name, and whether it runs in the cloud
  ACCOUNT               cloud: its entry in the keyring (providers.api_key)
  PACE                  its own pace times this is "1×"
  PIECE_CHARS           text per request (0: sentence by sentence)
  voices(language)      {id: label} to choose from for a spoken language, or
                        None: any voice id
  default_voice(language)  voice when none (or one of another language) is chosen
  BROWSE                a page to find voice ids, or None
  voice_name(voice)     what to show for a voice id
  prepare(voice)        fetches a voice before its first use (may take long)
  speech(voice, language) -> Speech with .rate (Hz), .pace (tempo factor left for
                        the player) and .synthesize(text) yielding 16 bit mono
                        PCM; speech() and synthesize() raise ProviderError

To add a provider: a module here and an entry in PROVIDERS.
"""

from . import fishaudio, piper

PROVIDERS = {"piper": piper, "fish": fishaudio}
LOCAL = piper        # takes over when a cloud provider fails


def get(name):
    return PROVIDERS.get(name, LOCAL)


def voice(name, voices, language):
    """The chosen voice of a provider; voices: settings "read_voices"."""
    provider = get(name)
    chosen = voices.get(name)
    choices = provider.voices(language)
    if not chosen or (choices is not None and chosen not in choices):
        return provider.default_voice(language)
    return chosen
