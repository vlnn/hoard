import json
import subprocess
import sys
from pathlib import Path

from hoard import alfred

PACKAGE = Path(alfred.__file__).resolve().parents[1]


def test_the_toolkit_renders_rows_without_the_kernel():
    rows = alfred.Items((alfred.Head("log", 'Log "api"', verb="keep"), alfred.Item("1", "testing api", "14:31 today")))
    document = json.loads(alfred.render(rows))
    assert [item["title"] for item in document["items"]] == ['Log "api"', "testing api"], "a workflow can build rows and print them itself"


def test_importing_the_toolkit_stays_off_the_network_and_the_system():
    probe = "import json, sys, hoard.alfred; print(json.dumps(sorted(sys.modules)))"
    finished = subprocess.run([sys.executable, "-I", "-c", probe], capture_output=True, text=True, check=True, env={"PYTHONPATH": str(PACKAGE.parent)})
    loaded = json.loads(finished.stdout)
    heavy = [name for name in loaded if name.split(".")[0] in {"urllib", "subprocess", "sqlite3", "dataclasses", "http"} or name.startswith("hoard._")]
    assert heavy == [], "import hoard.alfred should cost a keystroke nothing"
