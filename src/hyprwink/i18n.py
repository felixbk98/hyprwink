"""Language of the interface (gettext).

Texts are written in English in the code: _("…") translates, N_("…") only
marks a text that is translated where it is shown. Translations are in
po/<language>.po and compiled into hyprwink/locale/ (see README). The
language is the setting "language", else the system's if Hyprwink has it,
else English. Dictation and reading aloud have their own spoken language
("dictate_language", "read_language"); by default the interface's.

To add a language: a new po/<language>.po and its name in NAMES.
"""

import gettext
import os
from importlib import resources

from . import settings

DOMAIN = "hyprwink"
LOCALE_DIR = resources.files("hyprwink") / "locale"
NAMES = {"en": "English", "de": "Deutsch"}   # in their own language
_translation = gettext.NullTranslations()


def available():
    """{code: name} of the languages there are translations for, English first."""
    found = {p.name for p in LOCALE_DIR.iterdir() if (p / "LC_MESSAGES" / f"{DOMAIN}.mo").is_file()} \
        if LOCALE_DIR.is_dir() else set()
    return {code: NAMES.get(code, code) for code in ["en", *sorted(found)]}


def _system():
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var)
        if value:
            code = value.split(":")[0].split("_")[0].split(".")[0]
            return code if code in available() else "en"
    return "en"


def current():
    chosen = settings.get("language")
    return chosen if chosen in available() else _system()


def spoken(setting):
    """Spoken language of dictation ("dictate_language") or reading aloud
    ("read_language")."""
    chosen = settings.get(setting)
    return chosen if chosen in available() else current()


def translate(text, language):
    """text in a given language, e.g. what is read aloud in the spoken one."""
    return gettext.translation(DOMAIN, str(LOCALE_DIR), [language], fallback=True).gettext(text)


def use(language=None):
    """Switch the language (default: the current setting)."""
    global _translation
    _translation = gettext.translation(DOMAIN, str(LOCALE_DIR), [language or current()], fallback=True)


def _(text):
    return _translation.gettext(text)


def ngettext(singular, plural, n):
    return _translation.ngettext(singular, plural, n)


def N_(text):
    return text


use()
