from __future__ import annotations

import uuid

from hoard.build._workflow import Setting, Workflow

PYTHON = "/usr/bin/python3"
FILTER = "alfred.workflow.input.scriptfilter"
ACTION = "alfred.workflow.action.script"
NOTIFY = "alfred.workflow.output.notification"
BASH = 0
ARGV = 1
ESCAPING = 102


def uid(workflow: Workflow, role: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{workflow.bundleid}/{role}")).upper()


def script_filter(workflow: Workflow, keyword: str) -> dict:
    return {
        "type": FILTER,
        "uid": uid(workflow, "filter"),
        "version": 3,
        "config": {
            "alfredfiltersresults": False,
            "alfredfiltersresultsmatchmode": 0,
            "argumenttreatemptyqueryasnil": False,
            "argumenttrimmode": 0,
            "argumenttype": 1,
            "escaping": ESCAPING,
            "keyword": keyword,
            "queuedelaycustom": 3,
            "queuedelayimmediatelyinitially": True,
            "queuedelaymode": 0,
            "queuemode": 1,
            "runningsubtext": "",
            "script": f'{PYTHON} hoard.py filter "$1"',
            "scriptargtype": ARGV,
            "scriptfile": "",
            "subtext": workflow.description,
            "title": workflow.name,
            "type": BASH,
            "withspace": True,
        },
    }


def action(workflow: Workflow) -> dict:
    return {
        "type": ACTION,
        "uid": uid(workflow, "act"),
        "version": 2,
        "config": {
            "concurrently": False,
            "escaping": ESCAPING,
            "script": f'{PYTHON} hoard.py act "$verb" "$1"',
            "scriptargtype": ARGV,
            "scriptfile": "",
            "type": BASH,
        },
    }


def notification(workflow: Workflow) -> dict:
    return {
        "type": NOTIFY,
        "uid": uid(workflow, "notify"),
        "version": 1,
        "config": {
            "lastpathcomponent": False,
            "onlyshowifquerypopulated": True,
            "removeextension": False,
            "text": "{query}",
            "title": workflow.name,
        },
    }


def link_to(destination: dict) -> dict:
    return {"destinationuid": destination["uid"], "modifiers": 0, "modifiersubtext": "", "vitoclose": False}


def textarea(setting: Setting) -> tuple:
    return "textarea", {"default": setting.default, "required": False, "trim": True, "verticalsize": 3}


def textfield(setting: Setting) -> tuple:
    return "textfield", {"default": setting.default, "placeholder": "", "required": False, "trim": True}


def filepicker(setting: Setting) -> tuple:
    return "filepicker", {"default": setting.default, "filtermode": 1, "placeholder": "", "required": False}


def checkbox(setting: Setting) -> tuple:
    return "checkbox", {"default": bool(setting.default), "required": False, "text": ""}


ALFRED_SETTINGS = {"lines": textarea, "text": textfield, "folder": filepicker, "checkbox": checkbox}


def user_configuration(setting: Setting) -> dict:
    alfred_type, config = ALFRED_SETTINGS[setting.type](setting)
    return {
        "config": config,
        "description": setting.description,
        "label": setting.label,
        "type": alfred_type,
        "variable": setting.variable,
    }


def info_plist(workflow: Workflow, keyword: str, version: str = "") -> dict:
    chain = [script_filter(workflow, keyword), action(workflow), notification(workflow)]
    return {
        "bundleid": workflow.bundleid,
        "category": "Productivity",
        "connections": {source["uid"]: [link_to(target)] for source, target in zip(chain, chain[1:])},
        "createdby": workflow.createdby,
        "description": workflow.description,
        "disabled": False,
        "name": workflow.name,
        "objects": chain,
        "readme": "",
        "uidata": {item["uid"]: {"xpos": 50 + 250 * n, "ypos": 50} for n, item in enumerate(chain)},
        "userconfigurationconfig": [user_configuration(setting) for setting in workflow.configuration],
        "variablesdontexport": [],
        "version": version,
        "webaddress": "",
    }
