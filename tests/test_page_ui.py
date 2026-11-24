"""페이지를 실제 브라우저(크롬 계열)에서 눌러 보는 시험. 실행: py -X utf8 -m pytest -q tests/test_page_ui.py

- 가짜 명단(sample/)으로 만든 페이지를 로컬 서버로 띄우고, 폰 크기 화면에서 이름 검색·선택·체크·저장을 누른다.
- 브라우저가 없으면 건너뛴다. CI 처럼 꼭 돌려야 할 때는 환경변수 REQUIRE_BROWSER=1 (없으면 실패로 처리).
- 준비: pip install playwright  (+ 크롬이나 엣지가 깔려 있거나 `python -m playwright install chromium`)
"""
import csv
import functools
import http.server
import io
import os
import re
import sys
import threading
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import build_site  # noqa: E402

SAMPLE = ROOT / "sample" / "roster.sample.csv"
ORG = "샘플 모임"
PHONE = re.compile(r"01\d[- ]?\d{3,4}[- ]?\d{4}")
KAKAO_UA = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36 KAKAOTALK/10.9.0"


def people():
    return [(int(n), name, tel) for n, name, tel in build_site.parse(build_site.read_table(SAMPLE))]


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(tmp_path_factory, src, org=ORG):
    """src 명단으로 페이지를 만들어 로컬 서버로 띄운다. (서버, {origin,url,dir}) 를 돌려준다."""
    out = tmp_path_factory.mktemp("ui") / "site"
    slug, _ = build_site.build(src, out, org=org)
    handler = functools.partial(Quiet, directory=str(out))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    origin = f"http://127.0.0.1:{srv.server_address[1]}"
    return srv, {"origin": origin, "url": f"{origin}/{slug}/", "dir": out / slug}


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    srv, info = serve(tmp_path_factory, SAMPLE)
    yield info
    srv.shutdown()


# 모서리 이름: 안에 공백, 허용되는 가장 긴 한글(23자: 연락처 N: 줄이 75바이트), 띄어쓰기 없는 긴 영문, 영문 공백, 쉼표
LONG_KO = "가나다라마바사아자차카타파하거너더러머버서어고"
LONG_EN = "Abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz"
LONG_ORG = "가나다라마바사아자차카타파하거너더러머버서"  # 21자: CATEGORIES: 줄이 74바이트
EDGE_NAMES = ["김 하나", LONG_KO, LONG_EN, "Kim Ha", "Lee, Jr", "이둘"]


@pytest.fixture(scope="module")
def edge_site(tmp_path_factory):
    src = tmp_path_factory.mktemp("edge") / "roster.csv"
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(["번호", "이름", "전화번호"])
    for i, name in enumerate(EDGE_NAMES, 1):
        w.writerow([i, name, f"010-0000-{i:04d}"])
    src.write_bytes(buf.getvalue().encode("utf-8"))
    srv, info = serve(tmp_path_factory, src, org=LONG_ORG)
    yield info
    srv.shutdown()


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        b, errors = None, []
        for kw in ({}, {"channel": "chrome"}, {"channel": "msedge"}):  # 받아 둔 크롬 → 설치된 크롬 → 엣지
            try:
                b = p.chromium.launch(**kw)
                break
            except Exception as e:
                errors.append(str(e).strip().splitlines()[0])
        if b is None:
            msg = "실행할 크롬/엣지가 없어요: " + " | ".join(errors)
            if os.environ.get("REQUIRE_BROWSER"):
                pytest.fail(msg)
            pytest.skip(msg)
        yield b
        b.close()


@pytest.fixture()
def page(browser):
    ctx = browser.new_context(viewport={"width": 375, "height": 812}, accept_downloads=True, locale="ko-KR")
    pg = ctx.new_page()
    pg.set_default_timeout(30000)
    yield pg
    ctx.close()


def open_page(pg, url):
    pg.goto(url)
    pg.wait_for_selector("a.name")


def pick(pg, name):
    pg.click(f'a.name:text-is("{name}")')
    pg.wait_for_selector("#picks label.pick")


def visible_names(pg):
    return [a.inner_text() for a in pg.query_selector_all("a.name") if a.is_visible()]


def download_text(pg):
    with pg.expect_download() as dl:
        pg.click("#save")
    return Path(dl.value.path()).read_bytes(), dl.value.suggested_filename


def test_search_filters_names(page, site):
    rows = people()
    open_page(page, site["url"])
    assert visible_names(page) == [n for _, n, _ in rows]
    page.fill("#q", rows[1][1])
    assert visible_names(page) == [rows[1][1]]
    page.fill("#q", f" {rows[1][1][0]} {rows[1][1][1:]} ")  # 사이 공백은 무시한다
    assert visible_names(page) == [rows[1][1]]
    page.fill("#q", "없는이름")
    assert visible_names(page) == [] and page.is_visible("#nomatch")
    page.fill("#q", "")
    assert len(visible_names(page)) == len(rows) and page.is_hidden("#nomatch")


def test_pick_name_shows_everyone_else_checked(page, site):
    rows = people()
    open_page(page, site["url"])
    pick(page, rows[0][1])
    assert page.is_visible("#mine") and page.is_hidden("#list")
    assert page.inner_text("#who") == rows[0][1]
    labels = page.eval_on_selector_all("#picks label.pick", "els => els.map(e => e.innerText.trim())")
    assert labels == [n for _, n, _ in rows[1:]]  # 본인은 없다
    assert page.eval_on_selector_all("#picks input", "els => els.every(e => e.checked)")
    n = len(rows) - 1
    assert page.inner_text("#cnt") == f"{n}명 선택" and page.inner_text("#save") == f"{n}명 저장"
    assert page.get_attribute("#save", "href").endswith(f"/m/{rows[0][0]}.vcf")


def test_uncheck_all_none_update_count_and_button(page, site):
    rows = people()
    open_page(page, site["url"])
    pick(page, rows[0][1])
    n = len(rows) - 1
    page.locator("#picks input").nth(0).uncheck()
    assert page.inner_text("#cnt") == f"{n - 1}명 선택" and page.inner_text("#save") == f"{n - 1}명 저장"
    page.click("#none")
    assert page.inner_text("#save") == "고른 사람이 없어요" and page.get_attribute("#save", "aria-disabled") == "true"
    page.click("#all")
    assert page.inner_text("#save") == f"{n}명 저장" and page.get_attribute("#save", "aria-disabled") == "false"


def test_zero_selected_downloads_nothing(page, site):
    rows = people()
    open_page(page, site["url"])
    pick(page, rows[0][1])
    page.click("#none")
    downloads = []
    page.on("download", lambda d: downloads.append(d))  # 내장 메서드는 playwright 가 감쌀 수 없어서 람다로
    page.evaluate("document.getElementById('save').click()")  # 눌러도 파일이 받아지거나 이동하지 않는다
    page.wait_for_timeout(1000)
    assert downloads == [] and page.is_visible("#mine") and page.url.startswith(site["url"])


def test_everyone_selected_downloads_the_uploaded_file(page, site):
    rows = people()
    open_page(page, site["url"])
    pick(page, rows[0][1])
    data, filename = download_text(page)
    assert filename == "샘플-모임.vcf"
    assert data == (site["dir"] / "m" / f"{rows[0][0]}.vcf").read_bytes()


def test_partial_selection_builds_a_file_with_only_the_chosen(page, site):
    rows = people()
    open_page(page, site["url"])
    pick(page, rows[0][1])
    page.locator("#picks input").nth(0).uncheck()  # rows[1] 뺌
    page.locator("#picks input").nth(2).uncheck()  # rows[3] 뺌
    data, filename = download_text(page)
    raw = data.decode("utf-8")
    assert filename == "샘플-모임.vcf"
    assert re.findall(r"^FN:(.*)\r$", raw, re.M) == [rows[2][1], rows[4][1], rows[5][1]]
    assert raw.count("BEGIN:VCARD") == raw.count("END:VCARD") == 3
    assert raw.startswith("BEGIN:VCARD\r\nVERSION:3.0\r\n") and "\n" not in raw.replace("\r\n", "")
    for gone in (rows[0], rows[1], rows[3]):  # 본인과 뺀 사람은 이름도 번호도 없다
        assert gone[1] not in raw and gone[2] not in raw


def test_me_parameter_opens_the_list_directly(page, site):
    rows = people()
    page.goto(site["url"] + f"?me={rows[1][0]}")
    page.wait_for_selector("#picks label.pick")
    assert page.is_visible("#mine") and page.is_hidden("#list") and page.inner_text("#who") == rows[1][1]
    page.goto(site["url"] + "?me=99999")  # 없는 번호는 처음 화면
    page.wait_for_selector("a.name")
    assert page.is_visible("#list") and page.is_hidden("#mine")


def test_not_me_link_returns_to_the_name_list(page, site):
    rows = people()
    page.goto(site["url"] + f"?me={rows[1][0]}")
    page.wait_for_selector("#picks label.pick")
    page.click("text=내 이름이 아니에요")
    page.wait_for_selector("a.name")
    assert page.is_visible("#list") and page.is_hidden("#mine") and "?me=" not in page.url


def test_kakaotalk_browser_shows_notice_and_tries_external_browser(browser, site):
    ctx = browser.new_context(user_agent=KAKAO_UA, viewport={"width": 375, "height": 812})
    pg = ctx.new_page()
    asked = []
    cdp = ctx.new_cdp_session(pg)
    cdp.send("Page.enable")
    cdp.on("Page.frameRequestedNavigation", lambda e: asked.append(e["url"]))
    pg.goto(site["url"], wait_until="commit")  # 카카오톡이면 페이지가 바로 kakaotalk:// 로 넘어가려 해서 load 가 끝나지 않는다
    pg.wait_for_function("document.documentElement.classList.contains('kakao')")
    pg.wait_for_timeout(800)
    assert pg.is_visible(".kakao-note")
    assert any(u.startswith("kakaotalk://web/openExternal?url=") and "127.0.0.1" in u for u in asked), asked
    ctx.close()


def test_no_outside_requests_no_numbers_in_page_and_noindex(page, site):
    rows = people()
    seen = []
    page.on("request", lambda r: seen.append(r.url))
    open_page(page, site["url"])
    pick(page, rows[0][1])
    download_text(page)
    assert seen and all(u.startswith(site["origin"]) or u.startswith(("blob:", "data:")) for u in seen), seen
    assert not PHONE.search((site["dir"] / "index.html").read_text(encoding="utf-8"))  # 번호는 연락처 파일에만 있다
    assert "noindex" in page.get_attribute('meta[name="robots"]', "content")


def test_phone_instructions_are_on_the_page(page, site):
    rows = people()
    open_page(page, site["url"])
    pick(page, rows[0][1])
    text = page.inner_text(".after")
    for must in ("아이폰", "오른쪽 위", "공유", "연락처", "저장", "안드로이드", "열기", "계정"):
        assert must in text, must


@pytest.mark.parametrize("width", [320, 375])
def test_no_horizontal_scroll_on_phone_widths(browser, site, width):
    rows = people()
    ctx = browser.new_context(viewport={"width": width, "height": 740})
    pg = ctx.new_page()
    pg.set_default_timeout(30000)
    open_page(pg, site["url"])
    assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    pick(pg, rows[0][1])
    assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    ctx.close()


def test_search_ignores_spaces_and_case_inside_names(page, edge_site):
    open_page(page, edge_site["url"])
    for q, want in (("김하나", ["김 하나"]), ("김 하나", ["김 하나"]), ("KIMHA", ["Kim Ha"]), ("kim ha", ["Kim Ha"])):
        page.fill("#q", q)
        assert visible_names(page) == want, q


@pytest.mark.parametrize("width", [320, 375])
def test_longest_names_fit_phone_width(browser, edge_site, width):
    ctx = browser.new_context(viewport={"width": width, "height": 740})
    pg = ctx.new_page()
    pg.set_default_timeout(30000)
    fits = (
        "document.documentElement.scrollWidth <= window.innerWidth && "
        "[...document.querySelectorAll('.tag,a.name,.pick')].every(e => e.getBoundingClientRect().right <= window.innerWidth)"
    )
    open_page(pg, edge_site["url"])
    assert pg.evaluate(fits)
    pick(pg, "이둘")  # 다른 사람들(긴 이름 포함)이 체크 목록으로 나온다
    assert pg.evaluate(fits)
    pg.click("text=내 이름이 아니에요")
    pg.wait_for_selector("a.name")
    pick(pg, LONG_KO)  # 가장 긴 이름이 '나'일 때도
    assert pg.evaluate(fits)
    ctx.close()


def test_checklist_shows_names_with_commas_as_typed(page, edge_site):
    open_page(page, edge_site["url"])
    pick(page, "이둘")
    labels = page.eval_on_selector_all("#picks label.pick", "els => els.map(e => e.innerText.trim())")
    assert "Lee, Jr" in labels and not any("\\" in label for label in labels)


def test_dark_mode_changes_background(browser, site):
    colors = {}
    for scheme in ("light", "dark"):
        ctx = browser.new_context(color_scheme=scheme, viewport={"width": 375, "height": 812})
        pg = ctx.new_page()
        pg.goto(site["url"])
        colors[scheme] = pg.evaluate("getComputedStyle(document.body).backgroundColor")
        ctx.close()
    assert colors["light"] != colors["dark"] and colors["dark"] == "rgb(14, 16, 19)"
