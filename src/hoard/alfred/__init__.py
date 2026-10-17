"""What any Alfred workflow needs, with or without the kernel.

Light enough for a keystroke: rows and their JSON, folding and word-prefix
matching, settings. The modules that reach the network or the system are
imported by name when needed: hoard.alfred.chat, hoard.alfred.apple,
hoard.alfred.macos.
"""

from hoard.alfred.settings import cache_folder, data_folder, is_on
from hoard.alfred.text import fold, matches, words
from hoard.items import Head, Item, Items, Mod
from hoard.render.alfred import render

__all__ = ["Head", "Item", "Items", "Mod", "cache_folder", "data_folder", "fold", "is_on", "matches", "render", "words"]
