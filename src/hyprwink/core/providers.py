"""What the speech providers share: their error and the API keys.

A provider is a module in core/stt (speech to text) or core/tts (text to
speech); the package docstrings list what each module provides. Cloud
providers keep their API key in the Secret Service keyring
(service=hyprwink, account=ACCOUNT).
"""

import subprocess

SERVICE = "hyprwink"


class ProviderError(Exception):
    """A provider failed; the message is shown to the user ("nicht erreichbar")."""


def api_key(account):
    try:
        return subprocess.run(["secret-tool", "lookup", "service", SERVICE, "account", account],
                              capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def store_key(account, label, key):
    subprocess.run(["secret-tool", "store", f"--label=Hyprwink: {label} API", "service", SERVICE, "account", account],
                   input=key.strip(), text=True, check=True, timeout=10)
