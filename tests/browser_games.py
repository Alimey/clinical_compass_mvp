"""Actual pointer, touch, drawing, physics, lifecycle and offline game scenarios."""

import hashlib
import base64
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
ART = Path(tempfile.gettempdir()) / "compass-artifacts"
ART.mkdir(exist_ok=True)

with tempfile.TemporaryDirectory() as temp:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {
        **os.environ,
        "COMPASS_DB": str(Path(temp) / "games.db"),
        "PORT": str(port),
        "COMPASS_DISABLE_WORKER": "1",
        "COMPASS_AI_API_KEY": "",
        "COMPASS_TELEGRAM_BOT_TOKEN": "",
    }
    server = subprocess.Popen(
        [str(ROOT / ".venv/bin/python"), "app.py"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        url = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                urllib.request.urlopen(url + "/api/health", timeout=1).close()
                break
            except OSError:
                if server.poll() is not None:
                    raise RuntimeError("Server exited")
                time.sleep(0.1)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                executable_path=os.environ.get("CHROMIUM_PATH")
                or shutil.which("chromium"),
                args=["--no-sandbox"],
            )
            context = browser.new_context(
                viewport={"width": 1440, "height": 1050},
                reduced_motion="no-preference",
                timezone_id="Europe/Moscow",
            )
            context.add_init_script(
                "window.gameDraws=0;const clear=CanvasRenderingContext2D.prototype.clearRect;CanvasRenderingContext2D.prototype.clearRect=function(...args){if(this.canvas.id==='game-canvas')window.gameDraws++;return clear.apply(this,args)}"
            )
            page = context.new_page()
            errors, csp, external, writes = [], [], [], []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on(
                "console",
                lambda m: (
                    csp.append(m.text) if "Content Security Policy" in m.text else None
                ),
            )
            page.on(
                "request",
                lambda r: external.append(r.url) if not r.url.startswith(url) else None,
            )
            page.goto(url)
            page.get_by_role("button", name="Войти как Александра").click()
            expect(page.locator(".patient-dashboard")).to_be_visible()
            page.on(
                "request",
                lambda r: writes.append(r.url) if r.method == "POST" else None,
            )

            def games(p=page):
                p.wait_for_function("()=>!busy&&state.user?.role==='patient'")
                p.evaluate("()=>navigate('help')")
                p.wait_for_function("()=>!busy&&state.page==='help'")
                p.locator("[data-group=help][data-key=games]").click()

            def choose(key, p=page):
                p.locator(f'[data-game-select="{key}"]').click()
                (
                    expect(p.locator(f'[data-mini-game="{key}"]')).to_be_visible()
                    if key != "bubbles"
                    else None
                )

            def click_world(x, y):
                canvas = page.locator("#game-canvas")
                canvas.scroll_into_view_if_needed()
                box = canvas.bounding_box()
                canvas.click(
                    position={"x": x / 720 * box["width"], "y": y / 500 * box["height"]}
                )

            def drag_world(points, p=page):
                canvas = p.locator("#game-canvas")
                canvas.scroll_into_view_if_needed()
                box = canvas.bounding_box()
                positions = [
                    (
                        box["x"] + x / 720 * box["width"],
                        box["y"] + y / 500 * box["height"],
                    )
                    for x, y in points
                ]
                p.mouse.move(*positions[0])
                p.mouse.down()
                for position in positions[1:]:
                    p.mouse.move(*position, steps=4)
                p.mouse.up()

            def pixels(p=page):
                return hashlib.sha256(
                    p.locator("#game-canvas").evaluate("el=>el.toDataURL()").encode()
                ).hexdigest()

            def status():
                return page.locator("#game-status")

            def snapshot(name):
                data = page.locator("#game-canvas").evaluate(
                    "el=>el.toDataURL().split(',')[1]"
                )
                (ART / f"game-{name}.png").write_bytes(base64.b64decode(data))

            games()
            expect(page.locator(".game-choice")).to_have_count(8)
            canvas = page.locator("#game-canvas")
            canvas.scroll_into_view_if_needed()
            box = canvas.bounding_box()

            def mouse_world(x, y):
                page.mouse.move(
                    box["x"] + x / 720 * box["width"],
                    box["y"] + y / 500 * box["height"],
                    steps=5,
                )

            before = pixels()
            mouse_world(650, 80)
            page.wait_for_timeout(180)
            assert pixels() == before, "Hover must not move the basket"
            page.mouse.down()
            page.wait_for_timeout(80)
            assert pixels() != before, "A held press must move the basket"
            page.mouse.up()
            before = pixels()
            page.wait_for_timeout(180)
            assert pixels() == before, "Release must stop the basket immediately"
            mouse_world(600, 100)
            page.mouse.down()
            page.wait_for_timeout(50)
            page.evaluate("window.dispatchEvent(new Event('blur'))")
            before = pixels()
            page.wait_for_timeout(160)
            assert pixels() == before, "Losing focus must end the gesture"
            page.mouse.up()
            mouse_world(250, 320)
            page.mouse.down()
            expect(status()).to_have_text(re.compile(r"Собрано: [1-9]"), timeout=5000)
            page.mouse.up()
            page.locator("#game-canvas").press("ArrowRight")
            snapshot("meadow")

            choose("balls")
            expect(status()).to_have_text("Шариков: 17 из 48")
            page.locator("[data-game-action=pause]").click()
            click_world(360, 75)
            expect(status()).to_have_text("Шариков: 18 из 48")
            before = pixels()
            drag_world([(360, 75), (430, 140), (510, 200)])
            expect(status()).to_have_text("Шариков: 18 из 48")
            assert pixels() != before
            page.locator("[data-game-action=gravity]").click()
            expect(page.locator("[data-game-action=gravity]")).to_have_attribute(
                "aria-pressed", "true"
            )
            page.locator("[data-game-action=pause]").click()
            before = pixels()
            page.wait_for_timeout(350)
            assert pixels() != before
            page.locator("[data-game-action=pause]").click()
            snapshot("balls")
            page.locator("[data-game-action=clear-balls]").click()
            expect(status()).to_have_text("Шариков: 0 из 48")
            for _ in range(52):
                page.locator("[data-game-action=add-ball]").click()
            expect(status()).to_have_text("Шариков: 48 из 48")

            choose("salon")
            expect(status()).to_have_text("Длина волос: 155")
            page.locator("[data-game-action=trim]").click()
            expect(status()).to_have_text("Длина волос: 135")
            page.locator("[data-game-action=grow]").click()
            expect(status()).to_have_text("Длина волос: 157")
            before = pixels()
            page.get_by_role("button", name="Волосы: сиреневый", exact=True).click()
            page.get_by_role("button", name="Помада: ягодный", exact=True).click()
            page.locator("[data-game-action=bow]").click()
            assert pixels() != before
            before = pixels()
            drag_world([(422, 148), (390, 130), (300, 155)])
            assert pixels() != before
            before = int(status().inner_text().split(": ")[1])
            drag_world([(250, 300), (300, 300), (360, 300), (420, 300), (470, 300)])
            assert int(status().inner_text().split(": ")[1]) < before
            # A straight sweep leaves an even, visible cut on both sides of the face.
            edges = page.locator("#game-canvas").evaluate(
                "el=>{const c=el.getContext('2d');return [270,280,440,450].map(x=>{let last=0;for(let y=270;y<360;y++){const p=c.getImageData(x*2,y*2,1,1).data;if(p[0]<210&&p[1]<190)last=y;}return last;})}"
            )
            assert (
                all(297 <= y <= 302 for y in edges) and max(edges) - min(edges) <= 2
            ), edges
            snapshot("salon")

            choose("cake")
            expect(page.locator(".game-palette legend")).to_have_text("Цвет украшения")
            page.get_by_role(
                "button", name="Цвет украшения: мятный", exact=True
            ).click()
            expect(status()).to_have_text("Украшений: 0")
            click_world(360, 250)
            expect(status()).to_have_text("Украшений: 1")
            page.get_by_role("button", name="Крем", exact=True).click()
            drag_world([(250, 335), (300, 320), (360, 340), (420, 320), (480, 335)])
            expect(status()).to_have_text("Украшений: 2")
            page.get_by_role("button", name="Цветы", exact=True).click()
            click_world(300, 260)
            page.get_by_role("button", name="Свечи", exact=True).click()
            click_world(400, 215)
            snapshot("cake")
            page.locator("[data-game-action=undo]").click()
            expect(status()).to_have_text("Украшений: 3")

            choose("lava")
            before = pixels()
            page.wait_for_timeout(250)
            assert pixels() != before
            page.locator("[data-game-action=pause]").click()
            before = pixels()
            draws = page.evaluate("window.gameDraws")
            page.wait_for_timeout(200)
            assert pixels() == before and page.evaluate("window.gameDraws") == draws
            before = pixels()
            click_world(100, 200)
            assert pixels() == before, "Outside the glass should not grab lava"
            drag_world([(360, 250), (400, 300), (430, 340)])
            assert pixels() != before, "Dragging should move lava even while paused"
            before = pixels()
            page.wait_for_timeout(200)
            assert pixels() == before
            page.get_by_role("button", name="Цвет лавы: сиреневый", exact=True).click()
            assert pixels() != before
            snapshot("lava")

            choose("sand")
            before = pixels()
            drag_world(
                [
                    (190, 250),
                    (240, 210),
                    (310, 190),
                    (390, 200),
                    (440, 250),
                    (410, 310),
                    (330, 330),
                    (260, 310),
                    (220, 265),
                ]
            )
            expect(status()).to_have_text("Штрихов: 1")
            assert pixels() != before
            page.get_by_role("button", name="Палочка", exact=True).click()
            drag_world([(480, 320), (520, 280), (560, 250)])
            expect(status()).to_have_text("Штрихов: 2")
            snapshot("sand")
            page.locator("[data-game-action=undo]").click()
            expect(status()).to_have_text("Штрихов: 1")

            choose("jam")
            page.locator("[data-game-action=pour]").click()
            page.wait_for_function("()=>document.querySelector('#jam-fill').value>=15")
            page.locator("[data-game-action=pour]").click()
            page.locator("[data-game-action=shelf]").click()
            expect(status()).to_have_text("Банка: 0% · На полке: 1 из 6", timeout=4000)
            page.get_by_role("button", name="Варенье: абрикос", exact=True).click()
            page.locator("[data-game-action=pour]").click()
            page.wait_for_function("()=>document.querySelector('#jam-fill').value>=15")
            page.locator("[data-game-action=pour]").click()
            drag_world([(360, 365), (400, 250), (405, 120)])
            expect(status()).to_have_text("Банка: 0% · На полке: 2 из 6", timeout=4000)
            snapshot("jam")

            # Games stay in the current user's session and stop rendering elsewhere.
            choose("cake")
            expect(status()).to_have_text("Украшений: 3")
            page.evaluate("()=>navigate('learn')")
            page.wait_for_function("()=>!busy")
            draws = page.evaluate("window.gameDraws")
            page.wait_for_timeout(200)
            assert page.evaluate("window.gameDraws") == draws
            games()
            choose("cake")
            expect(status()).to_have_text("Украшений: 3")
            for width in (320, 390, 768, 1024, 1440):
                page.set_viewport_size({"width": width, "height": 950})
                for key in (
                    "meadow",
                    "balls",
                    "salon",
                    "cake",
                    "lava",
                    "sand",
                    "jam",
                    "bubbles",
                ):
                    choose(key)
                    assert page.evaluate(
                        "document.documentElement.scrollWidth<=innerWidth"
                    ), (width, key)
                    if key == "salon":
                        groups = page.locator(".game-palette").all()
                        hair, lips = groups[0].bounding_box(), groups[1].bounding_box()
                        assert lips["y"] >= hair["y"] + hair["height"], (
                            width,
                            "palette separation",
                        )
                        if width >= 1024:
                            art = page.locator("#game-canvas").bounding_box()
                            assert hair["x"] >= art["x"] + art["width"], (
                                width,
                                "salon sidebar",
                            )
                        if width in (390, 1440):
                            page.locator(".game-workspace").screenshot(
                                path=str(ART / f"revision5-salon-{width}.png")
                            )
            page.evaluate("navigator.serviceWorker.ready")
            paths = page.evaluate(
                "async()=>{const c=await caches.open('compass-shell-v25');return(await c.keys()).map(r=>new URL(r.url).pathname)}"
            )
            assert "/static/games.js" in paths and "/static/games.css" in paths
            context.set_offline(True)
            choose("cake")
            click_world(320, 230)
            expect(status()).to_have_text("Украшений: 4")
            choose("jam")
            expect(status()).to_contain_text("На полке: 2 из 6")
            context.set_offline(False)
            assert not writes, writes
            page.locator("#logout").click()
            expect(page.locator("#login-form")).to_be_visible()
            page.get_by_role("button", name="Войти как Михаил").click()
            expect(page.locator(".patient-dashboard")).to_be_visible()
            games()
            choose("cake")
            expect(status()).to_have_text("Украшений: 0")

            # Real touch events, pointer cancellation, no accidental page scroll.
            touch = browser.new_context(
                viewport={"width": 390, "height": 844},
                is_mobile=True,
                has_touch=True,
                reduced_motion="reduce",
            )
            mobile = touch.new_page()
            mobile.on("pageerror", lambda e: errors.append(str(e)))
            mobile.goto(url)
            mobile.get_by_role("button", name="Войти как Александра").click()
            expect(mobile.locator(".patient-dashboard")).to_be_visible()
            games(mobile)
            choose("sand", mobile)
            canvas = mobile.locator("#game-canvas")
            canvas.scroll_into_view_if_needed()
            box = canvas.bounding_box()
            scroll = mobile.evaluate("scrollY")
            for x, y in ((35, 35), (685, 35), (35, 465), (685, 465)):
                assert mobile.evaluate(
                    "([x,y])=>document.elementFromPoint(x,y)===document.querySelector('#game-canvas')",
                    [
                        box["x"] + x / 720 * box["width"],
                        box["y"] + y / 500 * box["height"],
                    ],
                ), (x, y, "overlapping game field")
            cdp = touch.new_cdp_session(mobile)
            mobile.evaluate(
                "window.touchLog=[];for(const type of ['pointerdown','pointerup','pointercancel','lostpointercapture'])document.querySelector('#game-canvas').addEventListener(type,event=>window.touchLog.push([type,event.pointerId]))"
            )

            def finger(kind, x=0, y=0):
                cdp.send(
                    "Input.dispatchTouchEvent",
                    {
                        "type": kind,
                        "touchPoints": (
                            []
                            if kind in ("touchEnd", "touchCancel")
                            else [
                                {
                                    "x": box["x"] + x / 720 * box["width"],
                                    "y": box["y"] + y / 500 * box["height"],
                                }
                            ]
                        ),
                    },
                )

            finger("touchStart", 200, 200)
            finger("touchMove", 300, 260)
            finger("touchMove", 430, 300)
            finger("touchEnd")
            expect(mobile.locator("#game-status")).to_have_text("Штрихов: 1")
            assert mobile.evaluate("scrollY") == scroll
            finger("touchStart", 240, 300)
            expect(mobile.locator("#game-status")).to_have_text("Штрихов: 2")
            finger("touchMove", 310, 350)
            finger("touchCancel")
            finger("touchStart", 240, 150)
            finger("touchMove", 320, 150)
            finger("touchEnd")
            expect(
                mobile.locator("#game-status"), str(mobile.evaluate("window.touchLog"))
            ).to_have_text("Штрихов: 3")
            choose("meadow", mobile)
            box = mobile.locator("#game-canvas").bounding_box()
            before = pixels(mobile)
            finger("touchStart", 650, 80)
            mobile.wait_for_timeout(90)
            assert pixels(mobile) != before
            finger("touchEnd")
            before = pixels(mobile)
            mobile.wait_for_timeout(180)
            assert pixels(mobile) == before
            choose("lava", mobile)
            expect(mobile.locator("[data-game-action=pause]")).to_have_text("Запустить")
            before = pixels(mobile)
            mobile.wait_for_timeout(180)
            assert pixels(mobile) == before
            box = mobile.locator("#game-canvas").bounding_box()
            finger("touchStart", 360, 250)
            finger("touchMove", 400, 330)
            finger("touchEnd")
            assert pixels(mobile) != before
            before = pixels(mobile)
            mobile.wait_for_timeout(180)
            assert pixels(mobile) == before
            mobile.locator("[data-game-action=pause]").click()
            before = pixels(mobile)
            mobile.wait_for_timeout(180)
            assert pixels(mobile) != before
            assert not errors, errors
            assert not csp, csp
            assert not external, external
            browser.close()
            print(
                "PASS: all 7 new games, collection, ball creation/drag/zero gravity/limit, salon edits, cake drawing/undo, lava pause/color, rake/stick/undo, jam pouring/shelf/drag, real touch/cancel, offline assets/play, 5 widths, per-user state, stopped background rendering, no game API writes/CSP errors"
            )
    finally:
        server.terminate()
        server.wait(timeout=10)
