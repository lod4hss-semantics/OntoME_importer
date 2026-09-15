from ontome_importer import __version__
from ontome_importer.cli import EXIT_NOT_IMPLEMENTED, main


def test_version(capsys):
    try:
        main(["--version"])
    except SystemExit as error:
        assert error.code == 0
    assert capsys.readouterr().out.strip() == __version__


def test_help(capsys):
    try:
        main(["--help"])
    except SystemExit as error:
        assert error.code == 0
    assert "audit" in capsys.readouterr().out


def test_commands_are_explicitly_unavailable(capsys):
    for command in ("audit", "generate", "validate"):
        assert main([command]) == EXIT_NOT_IMPLEMENTED
        assert f"{command} is not available yet" in capsys.readouterr().err
