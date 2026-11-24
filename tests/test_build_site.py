"""생성기 시험. 실행: py -X utf8 -m pytest -q   (가짜 명단 sample/ 만 쓴다 - 실제 이름·번호를 넣지 말 것)"""
import os
import re
import subprocess
import sys
from pathlib import Path

import openpyxl
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import build_site  # noqa: E402

SAMPLE = ROOT / "sample" / "roster.sample.csv"
ORG = "샘플 모임"
PHONE = re.compile(r"01\d[- ]?\d{3,4}[- ]?\d{4}")


def digits(s):
    return re.sub(r"\D", "", str(s))


def sample_rows():
    return [(int(n), name, digits(t)) for n, name, t in build_site.read_table(SAMPLE)]


def cards(raw):
    return [
        {l.split(":", 1)[0].split(";")[0]: l.split(":", 1)[1] for l in blk.split("\r\n") if ":" in l}
        for blk in raw.decode("utf-8").split("BEGIN:VCARD\r\n")[1:]
    ]


@pytest.fixture()
def site(tmp_path):
    slug, n = build_site.build(SAMPLE, tmp_path / "site", org=ORG, note="메모 예시")
    assert n == len(sample_rows())
    return tmp_path / "site", slug


def test_each_file_has_everyone_but_that_person(site):
    root, slug = site
    rows = sample_rows()
    assert len(rows) > 1
    for no, name, tel in rows:
        raw = (root / slug / "m" / f"{no}.vcf").read_bytes()
        assert raw.startswith(b"BEGIN:VCARD\r\nVERSION:3.0\r\n")  # BOM 없음
        assert b"\n" not in raw.replace(b"\r\n", b"")  # CRLF 만
        assert all(len(l) <= 75 for l in raw.split(b"\r\n"))  # 줄 접기 없이 75바이트 이하
        got = cards(raw)
        assert [(c["FN"], digits(c["TEL"])) for c in got] == [(n, t) for k, n, t in rows if k != no], name
        assert all(c["ORG"] == c["CATEGORIES"] == ORG and c["NOTE"] == "메모 예시" for c in got)
        assert all(c["N"] == f";{c['FN']};;;" for c in got)  # 이름은 성/이름으로 쪼개지 않는다
        assert tel not in digits(raw.decode("utf-8")), f"{name} 본인 번호가 들어감"


def test_page_lists_every_name_and_leaks_no_numbers(site):
    root, slug = site
    html = (root / slug / "index.html").read_text(encoding="utf-8")
    for no, name, _ in sample_rows():
        assert f'href="m/{no}.vcf" data-no="{no}">{name}</a>' in html, name
    assert "noindex" in html and 'lang="ko"' in html and "viewport" in html
    assert f"<title>{ORG} 연락처 저장</title>" in html and f"이 링크는 {ORG} 전용이에요" in html
    assert f"연락처에서 “{ORG}”로 검색하면 나와요" in html  # 그룹 대신 모임 이름 검색 안내
    assert "그룹은 웹 페이지로 만들 수 없어서 이름 검색으로 대신해요" in html  # 한계도 페이지에 적는다
    assert html.count(ORG) >= 3  # --org 값이 제목·안내·검색 안내에 들어간다 (다른 단체와 안 섞이는 것은 test_two_groups_… 가 본다)
    assert "kakaotalk://web/openExternal?url=" in html  # 카카오톡 안 브라우저 -> 기본 브라우저
    assert "me=(\\d+)" in html  # ?me=번호 로 이름 고르기를 건너뛴다
    assert "new Blob([picked.join('')]" in html  # 고른 사람만 담은 파일을 만든다
    assert 'id="q"' in html and 'id="save" href="./">저장</a>' in html
    assert "navigator.share" not in html  # 웹 공유 시트에는 연락처가 없다(아이폰 시뮬레이터·실기기 확인)
    # 아이폰 안내 4단계(iOS 18.6·26.5 시뮬레이터에서 누른 순서)와 안드로이드 줄
    assert "<b>오른쪽 위</b> 공유 버튼" in html and "<b>“연락처”</b>" in html and "<b>오른쪽 위 “저장”</b>" in html
    assert "“복사” 아래 목록" in html and "같은 사람이 한 번 더 생겨요" in html
    assert "<b>“열기”</b>를 누르세요" in html and "<b>계정(또는 “기기”)</b>" in html  # 안드로이드(크롬→열기→저장할 곳 고르기, 에뮬레이터에서 누른 순서)
    assert not PHONE.search(html)


def test_only_expected_files_are_published_under_one_folder(site):
    root, slug = site
    assert re.fullmatch(r"[0-9a-f]{16}", slug)  # 기본은 추측할 수 없는 무작위 주소
    files = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    assert files == {f"{slug}/index.html", *(f"{slug}/m/{no}.vcf" for no, _, _ in sample_rows())}


def test_slug_is_kept_on_rebuild_and_can_be_chosen(tmp_path):
    s1, _ = build_site.build(SAMPLE, tmp_path / "a")
    s2, _ = build_site.build(SAMPLE, tmp_path / "a")
    assert s1 == s2  # 이미 뿌린 링크가 죽지 않는다
    assert build_site.build(SAMPLE, tmp_path / "b", slug="demo")[0] == "demo"
    with pytest.raises(SystemExit):
        build_site.build(SAMPLE, tmp_path / "b", slug="other")  # 다른 주소가 이미 있으면 거부
    with pytest.raises(SystemExit):
        build_site.build(SAMPLE, tmp_path / "c", slug="../x")


def test_xlsx_and_cp949_csv_give_the_same_result(tmp_path):
    rows = [("번호", "이름", "전화번호")] + [(n, name, t) for n, name, t in build_site.read_table(SAMPLE)]
    wb = openpyxl.Workbook()
    for r in rows:
        wb.active.append(r)
    wb.active.append([None, None, None])  # 끝의 빈 줄은 건너뛴다
    wb.save(tmp_path / "r.xlsx")
    (tmp_path / "r.csv").write_bytes("\r\n".join(",".join(map(str, r)) for r in rows).encode("cp949"))  # 한국 엑셀 CSV
    a = build_site.parse(build_site.read_table(SAMPLE))
    assert build_site.parse(build_site.read_table(tmp_path / "r.xlsx")) == a
    assert build_site.parse(build_site.read_table(tmp_path / "r.csv")) == a


def test_excel_that_dropped_the_leading_zero_is_repaired():
    rows = build_site.parse([(1, "가", 1_000_000_001.0), (2, "나", "10-0000-" "0002")])
    assert [t for _, _, t in rows] == ["010-0000-0001", "010-0000-0002"]


@pytest.mark.parametrize(
    "table, msg",
    [
        ([(1, "가", "010-0000-0001"), (2, "나", "010-0000-0001")], "같은 전화번호"),
        ([(1, "가", "010-0000-0001"), (1, "나", "010-0000-0002")], "같은 번호"),
        ([(1, "가", "010-0000-0001"), (2, "", "010-0000-0002")], "이름이 비었"),
        ([(1, "가", "010-0000-0001"), (2, "나", "02-123-" "4567")], "휴대폰"),
        ([(1, "가", "010-0000-0001"), ("x", "나", "010-0000-0002")], "숫자가 아니"),
        ([(1, "가", "010-0000-0001")], "두 명 이상"),
    ],
)
def test_bad_roster_is_rejected_without_echoing_numbers(table, msg):
    with pytest.raises(SystemExit) as e:
        build_site.parse(table)
    assert msg in str(e.value) and not PHONE.search(str(e.value))


def test_org_is_escaped_in_html_and_script(tmp_path):
    evil = '<img src=x onerror=alert(1)> "&'
    slug, _ = build_site.build(SAMPLE, tmp_path / "s", org=evil)
    html = (tmp_path / "s" / slug / "index.html").read_text(encoding="utf-8")
    assert "<img src=x" not in html and "onerror=alert(1)>" not in html
    assert html.count("&lt;img src=x onerror=alert(1)&gt;") >= 2  # 제목·태그 모두 이스케이프
    assert "</script><" not in html.replace("</script>\n</body>", "")


def test_too_long_line_is_reported_and_nothing_is_written(tmp_path):  # 모임 이름·메모·사람 이름 어느 것이 길어도
    long_name = tmp_path / "r.csv"
    long_name.write_bytes(("번호,이름,전화번호\r\n1," + "가" * 30 + ",010-0000-0001\r\n2,나,010-0000-0002\r\n3,다,010-0000-0003\r\n").encode("utf-8"))
    for src, kw in ((SAMPLE, {"org": "가" * 40}), (SAMPLE, {"note": "가" * 40}), (long_name, {})):
        with pytest.raises(SystemExit) as e:
            build_site.build(src, tmp_path / "s", **kw)
        assert "75바이트" in str(e.value) and not (tmp_path / "s").exists(), kw  # 파일이 하나도 안 만들어진다
    slug, _ = build_site.build(SAMPLE, tmp_path / "keep")
    m = tmp_path / "keep" / slug / "m"
    before = {p.name: p.read_bytes() for p in m.iterdir()}
    with pytest.raises(SystemExit):
        build_site.build(SAMPLE, tmp_path / "keep", org="가" * 40)  # 실패한 다시 만들기가 이미 만든 사이트를 지우지 않는다
    assert {p.name: p.read_bytes() for p in m.iterdir()} == before


def test_errors_are_listed_together_with_the_real_line_numbers(tmp_path):
    src = tmp_path / "r.csv"  # 3번째 줄은 빈 줄이다: 알려 주는 줄 번호는 파일의 줄 번호와 같아야 한다
    src.write_bytes(  # 바이트로 쓴다(윈도우의 글 쓰기는 \r\n 을 \r\r\n 으로 바꿔 빈 줄이 생긴다)
        "번호,이름,전화번호\r\n1,가,010-0000-0001\r\n\r\n3,,010-0000-0003\r\nx,나,010-0000-0004\r\n5,다,010-0000-0001\r\n5,라,010-0000-0005\r\n".encode("utf-8")
    )
    with pytest.raises(SystemExit) as e:
        build_site.build(src, tmp_path / "s")
    msg = str(e.value)
    for line in ("4번째 줄: 이름이 비었", "5번째 줄: 번호가 숫자가 아니", "6번째 줄(다): 같은 전화번호가 2번째 줄에 이미", "7번째 줄(라): 같은 번호(첫 열)가 6번째 줄에 이미"):
        assert line in msg, (line, msg)  # 문제 4건이 한 번에 나온다
    assert not PHONE.search(msg) and not (tmp_path / "s").exists()


def test_two_folders_in_site_are_refused(tmp_path):
    (tmp_path / "a" / "x").mkdir(parents=True)
    (tmp_path / "a" / "y").mkdir()
    with pytest.raises(SystemExit) as e:
        build_site.build(SAMPLE, tmp_path / "a")
    assert "둘 이상" in str(e.value)


def fake_roster(path, n, prefix, block="0000"):
    """가짜 명단(번호 010-<block>-NNNN)을 쓴다. 실제 이름·번호는 쓰지 않는다."""
    body = "".join(f"{i},{prefix}{i:03d},010-{block}-{i:04d}\r\n" for i in range(1, n + 1))
    path.write_bytes(("번호,이름,전화번호\r\n" + body).encode("utf-8"))
    return path


def test_hundred_people_get_99_cards_each_without_self(tmp_path):  # 100명 규모
    slug, n = build_site.build(fake_roster(tmp_path / "r.csv", 100, "가짜"), tmp_path / "s", org="큰 모임")
    root = tmp_path / "s" / slug
    assert n == 100 and len(list((root / "m").glob("*.vcf"))) == 100
    assert "나를 뺀 99명" in (root / "index.html").read_text(encoding="utf-8")
    for me in range(1, 101):
        raw = (root / "m" / f"{me}.vcf").read_bytes()
        got = cards(raw)
        assert [c["FN"] for c in got] == [f"가짜{k:03d}" for k in range(1, 101) if k != me]
        assert [digits(c["TEL"]) for c in got] == [f"0100000{k:04d}" for k in range(1, 101) if k != me]
        assert all(len(l) <= 75 for l in raw.split(b"\r\n")) and b"\n" not in raw.replace(b"\r\n", b"")


def test_two_groups_get_different_links_and_never_mix(tmp_path):  # 다른 단체는 다른 주소, 서로 섞이지 않는다
    sa, na = build_site.build(fake_roster(tmp_path / "a.csv", 6, "Alpha", "0000"), tmp_path / "a", org="Alpha Club")
    sb, nb = build_site.build(fake_roster(tmp_path / "b.csv", 4, "Bravo", "1111"), tmp_path / "b", org="Bravo Club")
    assert (na, nb) == (6, 4) and sa != sb and all(re.fullmatch(r"[0-9a-f]{16}", s) for s in (sa, sb))

    def blob(d, s):
        return "".join(p.read_text(encoding="utf-8") for p in (d / s).rglob("*") if p.is_file())

    a, b = blob(tmp_path / "a", sa), blob(tmp_path / "b", sb)
    assert "Alpha Club" in a and "Bravo" not in a and "010-1111" not in a
    assert "Bravo Club" in b and "Alpha" not in b and "010-0000" not in b


def test_command_line_builds_the_site(tmp_path):  # README 빠른 시작과 같은 명령
    src = fake_roster(tmp_path / "r.csv", 3, "가짜")
    cmd = [sys.executable, "-X", "utf8", str(ROOT / "build_site.py"), str(src), str(tmp_path / "s"), "--org", "단체 이름"]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
    assert r.returncode == 0, r.stderr
    m = re.fullmatch(r"OK 3명 / 파일 3개 / 경로 /([0-9a-f]{16})/\s*", r.stdout)
    assert m and (tmp_path / "s" / m.group(1) / "index.html").is_file()


def test_rebuild_with_fewer_people_leaves_no_old_files_and_title_is_used(tmp_path):
    s1, _ = build_site.build(fake_roster(tmp_path / "a.csv", 6, "가짜"), tmp_path / "s", title="내 제목")
    s2, n = build_site.build(fake_roster(tmp_path / "b.csv", 4, "가짜"), tmp_path / "s", title="내 제목")
    assert s1 == s2 and n == 4  # 주소는 그대로
    assert sorted(p.name for p in (tmp_path / "s" / s2 / "m").iterdir()) == [f"{i}.vcf" for i in range(1, 5)]  # 5·6번의 옛 파일이 없다
    html = (tmp_path / "s" / s2 / "index.html").read_text(encoding="utf-8")
    assert "<title>내 제목</title>" in html and 'content="내 제목"' in html and "나를 뺀 3명" in html


def plain(s):  # 태그·굵게 표시·따옴표 모양 차이를 없애고 글자만 비교한다
    s = re.sub(r"<[^>]+>|\*\*", "", s).replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s)


def in_order(text, parts):
    pos = 0
    for p in parts:
        pos = text.find(p, pos)
        assert pos >= 0, f"{p!r} 가 이 순서로 없어요"
        pos += len(p)


def test_page_readme_and_verified_notes_tell_the_same_phone_steps(site):  # 기기 확인 기록(docs/VERIFIED.md)과 안내문이 어긋나지 않는다
    root, slug = site
    page = plain((root / slug / "index.html").read_text(encoding="utf-8"))
    readme = plain((ROOT / "README.md").read_text(encoding="utf-8"))
    verified = plain((ROOT / "docs" / "VERIFIED.md").read_text(encoding="utf-8"))
    for text in (page, readme):  # 아이폰 4단계와 안드로이드 순서
        iphone, android = text.split("안드로이드 (크롬)", 1)
        in_order(iphone.rsplit("아이폰 (", 1)[1], ['"저장"을 누르', "오른쪽 위", "공유", '"연락처"', '오른쪽 위 "저장"'])
        in_order(android, ['"저장"을 누르', '"열기"', "계정"])
    in_order(verified, ["사파리 → 공유 → 연락처 → 저장", "Open", "Device"])  # 확인 기록도 같은 순서를 눌렀다고 적는다
    assert "체크를 끄" in page and "체크를 끄" in readme  # 중복은 웹으로 건너뛸 수 없어서 "이미 저장한 사람은 체크 끄기"
    for measured in ("같은 사람을 다시", "Add All", "Android(구글 연락처)"):  # 아이폰·안드로이드 중복 측정값
        assert measured in verified, measured
    assert "그룹은 웹 페이지로 만들 수 없" in page and "그룹을 만들 수 없" in readme  # 그룹 대신 모임 이름 검색, 한계도 적는다
    assert f'"{ORG}"로 검색' in page and "이 이름으로 검색" in readme
    assert "못 한 것" in verified and "미확인" in readme  # 못 한 것을 숨기지 않는다
