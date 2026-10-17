import pytest

from hoard.alfred import macos


@pytest.mark.parametrize(
    "call, argv, why",
    [
        (lambda: macos.open("/b/x.epub"), ["open", "/b/x.epub"], "open hands the file to its app"),
        (lambda: macos.reveal("/b/x.epub"), ["open", "-R", "/b/x.epub"], "reveal selects it in Finder"),
    ],
)
def test_open_and_reveal_go_through_open(mocker, call, argv, why):
    run = mocker.patch("subprocess.run")
    call()
    assert run.call_args.args[0] == argv, why


def test_trash_asks_finder_so_put_back_works(mocker):
    run = mocker.patch("subprocess.run")
    macos.trash('/b/say "hi".md')
    script = run.call_args.args[0][2]
    assert script == 'tell application "Finder" to delete POSIX file "/b/say \\"hi\\".md"', "the path is quoted for AppleScript"


def test_copy_feeds_pbcopy(mocker):
    run = mocker.patch("subprocess.run")
    macos.copy("hello")
    assert run.call_args.args[0] == ["pbcopy"] and run.call_args.kwargs["input"] == "hello", "the text goes on stdin"


def test_notify_is_best_effort(mocker):
    mocker.patch("subprocess.run", side_effect=FileNotFoundError)
    macos.notify("done", "Kobold")


def test_notify_names_the_workflow(mocker):
    run = mocker.patch("subprocess.run")
    macos.notify("Finished Dhalgren", "Kobold")
    assert run.call_args.args[0][2] == 'display notification "Finished Dhalgren" with title "Kobold"', "title and text, both quoted"
