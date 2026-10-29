"""Coordinates HUD in a running modded game: its row and settings page in Options > Mods, the box in the top
left, /coords hiding and showing it (and keeping that), and /where's line in chat (screenshots)."""
import json
import time
from game import Game, difference

DATA = "horizon-mods/.horizon-mod-data/coords_hud"
TOP_LEFT, CHAT = (0.0, 0.0, 0.25, 0.1), (0.0, 0.7, 0.5, 0.95)


def typed(g, line):
    """As the player types it: T opens the chat box, then the line and Enter."""
    g.run("key", "t", "tap")
    time.sleep(0.5)
    g.run("type", line)
    g.run("key", "enter", "tap")
    time.sleep(1)


def run(ctl, resources, out):
    with Game(ctl, resources, out) as g:
        g.run("options", "mods")
        assert "Coordinates HUD 2.0.0: ON" in g.labels(), g.labels()
        g.run("click", g.ids()["Settings"])
        page = g.labels()
        assert "Shown: ON" in page, page
        g.run("click", g.ids()["Shown: ON"])
        clicked = (g.home / DATA / "shown").read_text()
        g.run("click", g.ids()["Shown: OFF"])
        g.play()
        g.run("command", "tp @s ~ ~ ~ 0 10")
        time.sleep(2)
        shown = g.shot("1-shown")
        typed(g, "/coords")
        hidden_file = (g.home / DATA / "shown").read_text()
        time.sleep(4)
        hidden = g.shot("2-hidden")
        typed(g, "/coords")
        typed(g, "/where")
        where = g.shot("3-where")
        results = {
            "page": page,
            "shown_file_after_click": clicked,
            "shown_file_after_coords": hidden_file,
            "shown_file_at_end": (g.home / DATA / "shown").read_text(),
            "diff_top_left_hidden": round(difference(shown, hidden, TOP_LEFT), 1),
            "diff_top_left_shown_again": round(difference(shown, where, TOP_LEFT), 1),
            "diff_chat_where": round(difference(hidden, where, CHAT), 1),
        }
        print(json.dumps(results, indent=2))
        assert clicked == "false" and hidden_file == "false", results
        assert results["shown_file_at_end"] == "true", results
        assert results["diff_top_left_hidden"] > 4, results
        assert results["diff_top_left_shown_again"] < results["diff_top_left_hidden"], results
        # native_chat lines are the client's; chat-log reads the server's chat here: see 3-where.png.
        print(json.dumps({"proof": "coords_hud", "ok": True, **results}, indent=2))
