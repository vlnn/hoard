from hoard.contract import Kind


def evidence(entity):
    return entity.title


KIND = Kind(name="empty", keyword="em", storages=(), fields=(), evidence=evidence)
