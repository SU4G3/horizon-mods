"""Minimap in a running modded game: the WebAssembly mod's settings files are read and written as they
were, and the map shows in its corner and moves with the Corner setting."""
import json
import time
from game import Game, difference

DATA = "horizon-mods/.horizon-mod-data/minimap"
# A player's settings from the WebAssembly mod.
FILES = {f"{DATA}/corner": "bottom_right", f"{DATA}/shape": "round", f"{DATA}/zoom": "2"}
TOP_LEFT, OTHER = (0.0, 0.0, 0.3, 0.45), (0.75, 0.55, 1.0, 1.0)


def run(ctl, resources, out):
    with Game(ctl, resources, out, FILES) as g:
        g.run("options", "mods")
        assert "Minimap 2.0.0: ON" in g.labels(), g.labels()
        g.run("click", g.ids()["Settings"])
        page = g.labels()
        assert page[:5] == ["Corner: Bottom right", "Size: Medium", "Shape: Round", "Zoom: 2 blocks per pixel", "Turn with the player: OFF"], page
        g.shot("settings-page")
        g.play()
        g.run("command", "tp @s ~ ~ ~ 0 10")
        time.sleep(2)
        first = g.shot("1-bottom-right")
        g.run("options", "mods")
        g.run("click", g.ids()["Settings"])
        g.run("click", g.ids()["Corner: Bottom right"])
        moved = (g.home / DATA / "corner").read_text()
        g.play()
        time.sleep(2)
        second = g.shot("2-top-left")
        results = {
            "corner_file_after_click": moved,
            "diff_top_left": round(difference(first, second, TOP_LEFT), 1),
            "diff_old_corner": round(difference(first, second, OTHER), 1),
        }
        assert moved == "top_left", results
        assert results["diff_top_left"] > 4 and results["diff_old_corner"] > 4, results
        print(json.dumps({"proof": "minimap", "ok": True, **results}, indent=2))
