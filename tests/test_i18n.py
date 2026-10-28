from hyprwink import gestures, i18n


def test_languages():
    assert list(i18n.available())[0] == "en"


def test_switching(monkeypatch):
    try:
        i18n.use("en")
        assert gestures.action_label(None) == "no action"
        if "de" in i18n.available():      # compiled from po/de.po
            i18n.use("de")
            assert gestures.action_label(None) == "keine Aktion"
            assert gestures.key_label("CTRL+space") == "Strg+Leertaste"
    finally:
        i18n.use("en")
