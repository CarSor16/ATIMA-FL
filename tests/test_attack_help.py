"""Every built-in attack has readable, localized mechanism and parameter help."""
from atima_fl.core.attack_taxonomy import ATTACK_GROUPS
from atima_fl.core.attack_help import ATTACK_HELP, attack_help


def test_help_covers_all_built_in_attacks():
    expected = {"none", *(attack for group in ATTACK_GROUPS.values() for attack in group)}
    assert set(ATTACK_HELP) == expected
    for attack in expected:
        help_text = attack_help(attack)
        assert set(help_text) == {"en", "it"}
        for localized in help_text.values():
            assert localized["mechanism"].strip()
            assert localized["intensity"].strip()


def test_external_components_keep_own_descriptions():
    assert attack_help("external_fixture") == {}
