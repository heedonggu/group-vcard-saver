"""생성기 시험. 실행: py -X utf8 -m pytest -q   (가짜 명단 sample/ 만 쓴다 - 실제 이름·번호를 넣지 말 것)"""
import json
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
ENGLAND = chr(0x1F3F4) + "".join(chr(0xE0000 + ord(c)) for c in "gbeng") + chr(0xE007F)  # 검은 깃발 + 태그 글자 gbeng + 태그 끝 = 영국 깃발(태그 글자는 눈에 안 보이는 서식 글자 Cf)


def digits(s):
    return re.sub(r"\D", "", str(s))


def sample_rows():
    return [(int(n), name, digits(t)) for n, name, t in build_site.read_table(SAMPLE)]


def cards(raw):
    """vCard 바이트를 [{필드: 값}, ...] 로 읽는다. 줄 전체가 BEGIN:VCARD / END:VCARD 인 것만 카드 경계다(메모·이름 안의 같은 글자는 값일 뿐)."""
    lines = raw.decode("utf-8").split("\r\n")
    assert lines[-1] == "", "마지막 줄도 CRLF 로 끝나야 한다"
    out, cur = [], None
    for l in lines[:-1]:
        if l == "BEGIN:VCARD":
            assert cur is None, "카드 안에서 또 시작"
            cur = {}
        elif l == "END:VCARD":
            out.append(cur)
            cur = None
        else:
            assert cur is not None, f"카드 밖의 줄: {l!r}"
            k, v = l.split(":", 1)
            cur[k.split(";")[0]] = v
    assert cur is None, "끝나지 않은 카드"
    return out


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
    assert "new URLSearchParams(location.search).get('me')" in html and "/^\\d+$/.test(me || '')" in html  # ?me=번호 로 이름 고르기를 건너뛴다(값 전체가 숫자일 때만)
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
    for bad in ("../x", "a b", "a/b", "한글", "x" * 65, "NUL", "con", "Com1", "LPT9"):  # 허용 문자(영문·숫자·-_)와 길이(64자). 윈도 예약 이름은 폴더로 못 만든다
        with pytest.raises(SystemExit) as e:
            build_site.build(SAMPLE, tmp_path / "c", slug=bad)
        assert "64자" in str(e.value), bad
        assert not (tmp_path / "c").exists()  # 아무것도 만들지 않는다
    assert build_site.build(SAMPLE, tmp_path / "c", slug="x" * 64)[0] == "x" * 64
    for ok in ("COM0", "COM10", "CONSOLE", "nul1"):  # 예약 이름과 닮았어도 예약이 아닌 이름은 된다
        assert build_site.build(SAMPLE, tmp_path / f"d-{ok}", slug=ok)[0] == ok


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


def other_digits(base, s):
    return "".join(chr(base + int(c)) for c in s)


@pytest.mark.parametrize(
    "table, msg",
    [
        ([(1, "가", "010-0000-0001"), (2, "나", other_digits(0xFF10, "01000000002"))], "휴대폰"),  # 전각 숫자: 전화로 못 거니 010 번호로 받지 않는다
        ([(1, "가", "010-0000-0001"), (2, "나", other_digits(0x660, "01000000002"))], "휴대폰"),  # 아라비아-인도 숫자
        ([(1, "가", "010-0000-0001"), (2, "나", other_digits(0x966, "01000000002"))], "휴대폰"),  # 데바나가리 숫자
        ([(1, "가", "010-0000-0001"), (2, "나", "010-0000-0001")], "같은 전화번호"),
        ([(1, "가", "010-0000-0001"), (1, "나", "010-0000-0002")], "같은 번호"),
        ([(1, "가", "010-0000-0001"), (2, "", "010-0000-0002")], "이름이 비었"),
        ([(1, "가", "010-0000-0001"), (2, "나", "02-123-" "4567")], "휴대폰"),
        ([(1, "가", "010-0000-0001"), ("x", "나", "010-0000-0002")], "숫자가 아니"),
        ([(1, "가", "010-0000-0001"), (1.5, "나", "010-0000-0002")], "숫자가 아니"),  # 소수·음수는 ?me=번호 로 열 수 없다
        ([(1, "가", "010-0000-0001"), (-2, "나", "010-0000-0002")], "숫자가 아니"),
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


def errors_of(src, tmp_path):
    with pytest.raises(SystemExit) as e:
        build_site.build(src, tmp_path / "s")
    assert not PHONE.search(str(e.value)) and not (tmp_path / "s").exists()  # 번호는 안 찍고, 아무것도 안 만든다
    return str(e.value)


@pytest.mark.parametrize(
    "text, want",
    [
        # 따옴표 안 줄바꿈: 2~3번째 줄이 한 행이라 틀린 행은 파일의 4번째 줄이다
        ('번호,이름,전화번호\r\n1,"김\r\n하나",010-0000-0001\r\nx,나,010-0000-0002\r\n3,다,010-0000-0003\r\n', ["4번째 줄: 번호가 숫자가 아니"]),
        # 제목줄이 두 줄에 걸쳐도 첫 사람은 3번째 줄
        ('"번호\r\n(숫자)",이름,전화번호\r\n1,,010-0000-0001\r\n2,나,010-0000-0002\r\n', ["3번째 줄: 이름이 비었"]),
        # 줄 끝이 \r 뿐인 옛 맥 엑셀 CSV
        ("번호,이름,전화번호\r1,가,010-0000-0001\r2,,010-0000-0002\r3,다,010-0000-0003\r", ["3번째 줄: 이름이 비었"]),
        # 줄 끝이 \n 뿐인 파일
        ("번호,이름,전화번호\n1,가,010-0000-0001\n\n3,나,02-123-" "4567\n", ["4번째 줄(나): 전화번호가 010"]),
    ],
)
def test_error_line_numbers_are_physical_file_lines(tmp_path, text, want):
    src = tmp_path / "r.csv"
    src.write_bytes(text.encode("utf-8"))
    msg = errors_of(src, tmp_path)
    for w in want:
        assert w in msg, (w, msg)
    assert msg.count("번째 줄") == len(want)  # 다른 줄을 잘못 탓하지 않는다


def test_cell_with_a_line_break_reads_as_one_name(tmp_path):
    src = tmp_path / "r.csv"
    src.write_bytes('번호,이름,전화번호\r\n1,"김\r\n하나",010-0000-0001\r\n2,둘,010-0000-0002\r\n'.encode("utf-8"))
    assert [n for _, n, _ in build_site.parse(build_site.read_table(src))] == ["김 하나", "둘"]


def test_every_problem_of_one_line_is_reported_together():
    table = [
        (1, "가", "010-0000-0001"),
        ("x", "", "02-123-" "4567"),  # 3번째 줄: 번호·이름·전화 셋 다 틀림
        (1.5, "다", "010-0000-0001"),  # 4번째 줄: 번호 소수 + 앞 줄과 같은 전화
        (5, "", "010-0000-0005"),  # 5번째 줄: 이름이 비었다. 그래도 번호 5 는 쓴 것으로 센다
        (5, "마", "010-0000-0006"),  # 6번째 줄: 5번째 줄과 같은 번호
    ]
    with pytest.raises(SystemExit) as e:
        build_site.parse(table)
    msg = str(e.value)
    for want in (
        "3번째 줄: 번호가 숫자가 아니",
        "3번째 줄: 이름이 비었",
        "3번째 줄: 전화번호가 010",
        "4번째 줄: 번호가 숫자가 아니",
        "4번째 줄(다): 같은 전화번호가 2번째 줄에 이미",
        "5번째 줄: 이름이 비었",
        "6번째 줄(마): 같은 번호(첫 열)가 5번째 줄에 이미",
        "쓸 수 있는 사람이 두 명 이상",  # 쓸 수 있는 줄이 1번 하나뿐이라는 것도 같이
    ):
        assert want in msg, (want, msg)
    assert msg.count("\n- ") == 8 and not PHONE.search(msg)  # 위 8건이 전부다(한 건도 빠지거나 겹치지 않는다)


@pytest.mark.parametrize(
    "table, bullets",
    [
        ([("x", "", "")], 4),  # 한 줄뿐인데 그 줄이 틀림: 줄의 오류 3건 + 사람 수 부족
        ([(1, "", "")], 3),
        ([(1, "가", "010-0000-0001"), ("x", "", "")], 4),  # 쓸 수 있는 사람이 하나뿐
        ([(1, "가", "010-0000-0001"), (2, "나", "010-0000-0001")], 2),  # 같은 전화번호라 하나만 쓸 수 있다
        ([], 1),
    ],
)
def test_too_few_people_is_reported_together_with_the_row_errors(table, bullets):
    with pytest.raises(SystemExit) as e:
        build_site.parse(table)
    msg = str(e.value)
    assert "두 명 이상" in msg and msg.count("\n- ") == bullets and not PHONE.search(msg), msg


def test_one_bad_row_file_reports_the_row_and_the_count_and_builds_nothing(tmp_path):
    src = tmp_path / "r.csv"
    src.write_bytes("번호,이름,전화번호\r\nx,,\r\n".encode("utf-8"))
    msg = errors_of(src, tmp_path)
    assert "2번째 줄: 이름이 비었" in msg and "두 명 이상" in msg


@pytest.mark.parametrize(
    "org, fname",
    [
        ("샘플 모임", "샘플 모임.vcf"),  # 공백·한글은 그대로
        ("Alpha Club", "Alpha Club.vcf"),
        ('a/b:c?"d', "a-b-c-d.vcf"),  # 파일 이름에 못 쓰는 글자만 -
        ("모임<1>", "모임-1-.vcf"),
        ("  .. ", "contacts.vcf"),  # 남는 게 없으면 기본 이름
        ("A B~C&D'E%F#G", "A B~C&D'E%F#G.vcf"),  # 쓸 수 없는 글자가 아니면 그대로(브라우저가 ~ 를 _ 로 바꾸는 것은 브라우저 몫)
        ("CON", "CON.vcf"),  # 윈도 예약 이름도 그대로 둔다(윈도 크롬이 받을 때 앞에 _ 를 붙이는 것은 브라우저 몫)
        ("nul.txt", "nul.txt.vcf"),
        (f"A{chr(0xA0)}B{chr(0x1F600)}C{chr(0xE000)}D", f"A{chr(0xA0)}B{chr(0x1F600)}C{chr(0xE000)}D.vcf"),  # 줄 안 바뀌는 공백·그림 문자·사용자 정의 글자도 그대로
        ("A\x00B", "A-B.vcf"),  # 제어문자
        ("A\tB", "A-B.vcf"),
        ("A\x7fB", "A-B.vcf"),  # DEL
        ("A\x85B", "A-B.vcf"),  # C1 제어문자(NEL)
        ("A\x9fB", "A-B.vcf"),
        ("A\u2028B", "A-B.vcf"),  # 줄·문단 구분
        ("A\u2029B", "A-B.vcf"),
        ("A\r\nB", "A-B.vcf"),  # 줄바꿈 둘이 이어져도 하나
        ("A\u200BB", "A-B.vcf"),  # 눈에 안 보이는 서식 글자: 폭 없는 공백
        ("A\u200DB", "A-B.vcf"),  # 폭 없는 연결 글자
        ("A\u202EB", "A-B.vcf"),  # 방향 바꾸기(파일 이름 속이기에 쓰인다)
        ("A\uFEFFB", "A-B.vcf"),  # BOM
        ("A\xadB", "A-B.vcf"),  # 소프트 하이픈
        ("A\x7f\u200B\x85B", "A-B.vcf"),  # 이어진 것은 하나로
        ("A\uFDD0B", "A-B.vcf"),  # 비문자: 글자로 쓰지 않는 코드 포인트(브라우저가 _ 로 바꾼다)
        ("A\uFDEFB", "A-B.vcf"),
        ("A\uFFFEB", "A-B.vcf"),
        ("A\uFFFFB", "A-B.vcf"),
        ("A\U0001fffeB", "A-B.vcf"),
        ("A\U0010ffffB", "A-B.vcf"),
        (f"A{chr(0xFDCF)}B{chr(0xFDF0)}", f"A{chr(0xFDCF)}B{chr(0xFDF0)}.vcf"),  # 비문자 범위 바로 옆(FDCF·FDF0)은 그대로
        (f"A{chr(0xFFFD)}B", f"A{chr(0xFFFD)}B.vcf"),  # U+FFFD(대체 글자)는 비문자가 아니다
        (f"{chr(0xA0)}모임{chr(0xA0)}", "모임.vcf"),  # 앞뒤의 공백은 유니코드 공백도 뗀다(브라우저가 맨 앞의 줄 안 바뀌는 공백을 _ 로 바꾼다)
        (f"{chr(0x3000)}모임{chr(0x3000)}", "모임.vcf"),  # 전각 공백
        (f"{chr(0x2003)}모임", "모임.vcf"),
        (f"{chr(0xA0)}{chr(0x3000)}", "contacts.vcf"),  # 유니코드 공백뿐이면 기본 이름
        (" . 모임 . ", "모임.vcf"),  # 공백과 점이 섞여도 앞뒤에서 모두 뗀다
        (f"가{chr(0x3164)}나", "가-나.vcf"),  # 채움 글자·점자 빈칸 같은 눈에 안 보이는 글자도 -
        (f"A{chr(0x2800)}B", "A-B.vcf"),
        (f"A{chr(0x34F)}B", "A-B.vcf"),  # 결합 이음표
        (f"A{chr(0x115F)}{chr(0x1160)}B", "A-B.vcf"),
        (f"A{chr(0x17B4)}B", "A-B.vcf"),
        (f"A{chr(0x2065)}B", "A-B.vcf"),
        (f"A{chr(0xFFA0)}B", "A-B.vcf"),
        (f"A{chr(0xFFF0)}B", "A-B.vcf"),
        (f"{chr(0x3164)}모임{chr(0x3164)}", "-모임-.vcf"),  # 앞뒤에 있으면 공백이 아니라 - 로 남는다
        (f"하나{chr(0x2764)}{chr(0xFE0F)}", f"하나{chr(0x2764)}{chr(0xFE0F)}.vcf"),  # 이모지에 붙은 변이 선택자는 글자의 일부라 그대로
        (f"A{chr(0xFE00)}B{chr(0xE0100)}", f"A{chr(0xFE00)}B{chr(0xE0100)}.vcf"),  # 다른 변이 선택자도 그대로(브라우저도 그대로 둔다)
        (chr(0xFE0F), "contacts.vcf"),  # 변이 선택자뿐이면 보이는 이름이 없으니 기본 이름
        (f" {chr(0xE0100)}{chr(0xFE00)}. ", "contacts.vcf"),
        (f"{chr(0xFE0F)} 모임", f"{chr(0xFE0F)} 모임.vcf"),  # 보이는 글자가 있으면 그대로
        (f"A{chr(0xE0067)}B", f"A{chr(0xE0067)}B.vcf"),  # 이모지 태그 글자(서식 글자 Cf)도 이모지의 일부라 그대로(크롬이 받을 때 _ 로 바꾸는 것은 브라우저 몫)
        (f"A{chr(0xE007F)}B", f"A{chr(0xE007F)}B.vcf"),  # 태그 끝 표시
        (f"A{chr(0xE0001)}B", f"A{chr(0xE0001)}B.vcf"),  # 언어 태그
        (ENGLAND, f"{ENGLAND}.vcf"),  # 깃발은 통째로(🏴 만 남기고 태그를 - 로 바꾸지 않는다)
        (f"{ENGLAND} 모임", f"{ENGLAND} 모임.vcf"),
        (chr(0xE007F), "contacts.vcf"),  # 태그뿐이면 보이는 이름이 없으니 기본 이름
        (f" {chr(0xE0067)}{chr(0xE007F)}. ", "contacts.vcf"),
        (f"A{chr(0x180E)}B", "A-B.vcf"),  # 180E(몽골어 모음 구분자)는 변이 선택자가 아니라 서식 글자라 -
        (f"A{chr(0x180B)}B{chr(0x180D)}C{chr(0x180F)}", f"A{chr(0x180B)}B{chr(0x180D)}C{chr(0x180F)}.vcf"),  # 몽골어 변이 선택자는 그대로
    ],
)
def test_downloaded_file_is_named_after_the_group(tmp_path, org, fname):
    slug, _ = build_site.build(SAMPLE, tmp_path / "s", org=org)
    html = (tmp_path / "s" / slug / "index.html").read_text(encoding="utf-8")
    names = [json.loads(m) for m in re.findall(r"(?:download', |a\.download = )(\".*?\")[);]", html)]
    assert names == [fname, fname]  # 전원 받기(올려 둔 파일)와 일부 받기(즉석 파일) 둘 다 같은 이름


def test_two_folders_in_site_are_refused(tmp_path):
    (tmp_path / "a" / "x").mkdir(parents=True)
    (tmp_path / "a" / "y").mkdir()
    with pytest.raises(SystemExit) as e:
        build_site.build(SAMPLE, tmp_path / "a")
    assert "둘 이상" in str(e.value)


def test_a_folder_this_tool_did_not_make_is_never_deleted(tmp_path):
    git = tmp_path / "repo" / ".git"  # 깃 저장소 폴더에 만들면 안의 폴더가 .git 하나뿐이라 그 이름이 주소로 잡힌다
    git.mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    with pytest.raises(SystemExit) as e:
        build_site.build(SAMPLE, tmp_path / "repo")
    assert "만든 폴더가 아니" in str(e.value) and (git / "HEAD").read_text() == "ref: refs/heads/main\n"
    other = tmp_path / "docs"  # --slug 로 이름을 정해도, 파일이 든 남의 폴더는 지우지 않는다
    (other / "keep").mkdir(parents=True)
    (other / "keep" / "note.txt").write_text("내 글")
    with pytest.raises(SystemExit):
        build_site.build(SAMPLE, other, slug="keep")
    assert (other / "keep" / "note.txt").read_text() == "내 글"
    (tmp_path / "f").mkdir()
    (tmp_path / "f" / "x").write_text("파일")  # 같은 이름이 파일이면 그것도 그대로 둔다
    with pytest.raises(SystemExit):
        build_site.build(SAMPLE, tmp_path / "f", slug="x")
    assert (tmp_path / "f" / "x").read_text() == "파일"
    (tmp_path / "e" / "mine").mkdir(parents=True)  # 빈 폴더는 주소로 쓴다
    assert build_site.build(SAMPLE, tmp_path / "e")[0] == "mine"


def test_nothing_is_changed_when_a_check_fails_before_writing(tmp_path):
    slug, _ = build_site.build(SAMPLE, tmp_path / "s", org=ORG)
    before = {p.relative_to(tmp_path).as_posix(): p.read_bytes() for p in (tmp_path / "s").rglob("*") if p.is_file()}
    for kw in ({"org": "\ud800"}, {"note": "a\udfffb"}, {"title": "\ud800\ud800"}):  # 파일로 쓸 수 없는 글자(짝 잃은 서로게이트)
        with pytest.raises(SystemExit) as e:
            build_site.build(SAMPLE, tmp_path / "s", **kw)
        assert "서로게이트" in str(e.value), kw
    assert {p.relative_to(tmp_path).as_posix(): p.read_bytes() for p in (tmp_path / "s").rglob("*") if p.is_file()} == before
    with pytest.raises(SystemExit):
        build_site.build(SAMPLE, tmp_path / "t", org="\ud800")
    assert not (tmp_path / "t").exists()


BREAKS = ["\r", "\n", "\r\n", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"]


@pytest.mark.parametrize("br", BREAKS, ids=lambda s: "+".join(f"U{ord(c):04X}" for c in s))
def test_every_kind_of_line_break_becomes_one_escaped_newline(tmp_path, br):
    slug, n = build_site.build(SAMPLE, tmp_path / "s", org=f"모임{br}이름", note=f"가{br}나{br}{br}다")
    files = list((tmp_path / "s" / slug / "m").glob("*.vcf"))
    assert len(files) == n
    for p in files:
        raw = p.read_bytes()
        assert not re.search(rb"\r(?!\n)|(?<!\r)\n", raw)  # 줄 끝은 CRLF 뿐: 홑 CR·홑 LF 가 없다
        got = cards(raw)
        assert len(got) == n - 1
        assert all(c["NOTE"] == "가\\n나\\n\\n다" and c["ORG"] == c["CATEGORIES"] == "모임\\n이름" for c in got)  # 줄바꿈 하나 = \n 하나(CRLF 는 하나)
        assert all(len(l) <= 75 for l in raw.split(b"\r\n"))
    html = (tmp_path / "s" / slug / "index.html").read_text(encoding="utf-8")
    assert '"모임-이름.vcf"' in html  # 받는 파일 이름에는 줄바꿈이 들어가지 않는다


@pytest.mark.parametrize(
    "text, want",
    [
        ("a\r\nb", "a\\nb"),
        ("a\n\rb", "a\\n\\nb"),  # LF 다음 CR 은 CRLF 가 아니라 줄바꿈 둘
        ("a\r\rb", "a\\n\\nb"),
        ("a\\b;c,d", "a\\\\b\\;c\\,d"),  # 역슬래시·세미콜론·쉼표
        ("a\tb", "a\tb"),  # 탭은 그대로
    ],
)
def test_vcard_text_escaping(text, want):
    assert build_site.esc(text) == want


def test_control_characters_become_spaces_but_tab_stays(tmp_path):
    slug, n = build_site.build(SAMPLE, tmp_path / "s", note="a\x00b\x07c\x1fd\x7fe\x80f\x9fg\th")
    for p in (tmp_path / "s" / slug / "m").glob("*.vcf"):
        raw = p.read_bytes()
        assert not re.search("[\x00-\x08\x0b-\x1f\x7f-\x9f\u2028\u2029]", raw.decode("utf-8").replace("\r\n", ""))  # 탭 말고는 제어문자가 하나도 없다
        assert all(c["NOTE"] == "a b c d e f g\th" for c in cards(raw))


def test_names_lose_control_characters_and_line_breaks():
    rows = build_site.parse([(1, "가\x00나\x7f다", "010-0000-0001"), (2, "라\u2028마\x85바", "010-0000-0002")])
    assert [n for _, n, _ in rows] == ["가 나 다", "라 마 바"]
    with pytest.raises(SystemExit) as e:
        build_site.parse([(1, "가", "010-0000-0001"), (2, "\x00\x7f", "010-0000-0002"), (3, "다", "010-0000-0003")])
    assert "3번째 줄: 이름이 비었" in str(e.value)  # 제어문자뿐인 이름은 빈 이름이다
    with pytest.raises(SystemExit) as e:  # 폭 없는 공백·BOM·방향 표시처럼 눈에 안 보이는 글자뿐인 이름도 빈 이름이다
        build_site.parse([(1, "가", "010-0000-0001"), (2, "\u200B\uFEFF \u202E", "010-0000-0002"), (3, "다", "010-0000-0003")])
    assert "3번째 줄: 이름이 비었" in str(e.value) and "3번째 줄(" not in str(e.value)
    assert build_site.parse([(1, "가\u200D나", "010-0000-0001"), (2, "다", "010-0000-0002")])[0][1] == "가\u200D나"  # 글자 사이의 것은 지키지 않고 그대로


GHOSTS = (  # 눈에 안 보이는 글자 27가지: 채움 글자·점자 빈칸·결합 이음표·변이 선택자·태그·서식 글자·비문자. chr() 로 쓴다(글자를 그대로 적으면 눈에 안 보인다)
    0x3164, 0x2800, 0x34F, 0x115F, 0x1160, 0x17B4, 0x17B5, 0x180B, 0x180E, 0x180F, 0x2065, 0xFE00, 0xFE0F, 0xFFA0, 0xFFF0, 0xFFF8,
    0xE0001, 0xE0100, 0xE0FFF, 0x200B, 0xAD, 0x61C, 0x2060, 0xFEFF, 0xFDD0, 0xFFFE, 0x1FFFF,
)


def second_name(name):
    return build_site.parse([(1, "가", "010-0000-0001"), (2, name, "010-0000-0002"), (3, "다", "010-0000-0003")])[1][1]


@pytest.mark.parametrize("cp", GHOSTS, ids=lambda cp: f"U{cp:04X}")
def test_a_name_of_only_invisible_characters_is_an_empty_name(cp):
    for name in (chr(cp), f" {chr(cp)} ", chr(cp) * 3, chr(cp) + chr(0x3164)):
        with pytest.raises(SystemExit) as e:
            second_name(name)
        assert "3번째 줄: 이름이 비었" in str(e.value) and "3번째 줄(" not in str(e.value), (hex(cp), name)


def test_a_name_with_real_letters_keeps_the_invisible_ones_between_them():
    for name in ("가" + chr(0x200D) + "나", "가" + chr(0x3164) + "나", "하나" + chr(0x2764) + chr(0xFE0F), "가" + chr(0x34F)):
        assert second_name(name) == name


@pytest.mark.parametrize("br", BREAKS, ids=lambda s: "+".join(f"U{ord(c):04X}" for c in s))
def test_every_kind_of_line_break_in_a_name_becomes_one_space(tmp_path, br):
    assert second_name(f"가{br}나{br}{br}다") == "가 나 다"  # 이름 칸은 한 줄이다: 줄바꿈 하나도 이어진 것도 공백 하나
    src = tmp_path / "r.csv"
    src.write_bytes(f'번호,이름,전화번호\r\n1,"가{br}나",010-0000-0001\r\n2,다,010-0000-0002\r\n'.encode("utf-8"))
    slug, n = build_site.build(src, tmp_path / "s")
    assert n == 2
    for p in (tmp_path / "s" / slug / "m").glob("*.vcf"):
        raw = p.read_bytes()
        assert not re.search(rb"\r(?!\n)|(?<!\r)\n", raw)  # 줄 끝은 CRLF 뿐
        assert [c["FN"] for c in cards(raw)] == (["가 나"] if p.stem == "2" else ["다"]), p.name  # 이름 값에 \n 이 들어가지 않는다


def test_text_that_looks_like_vcard_lines_cannot_add_or_hide_cards(tmp_path):
    evil = "x\r\nEND:VCARD\r\nBEGIN:VCARD\r\nFN:Evil\r\nTEL:010-0000-9999"  # 줄 하나가 75바이트를 넘지 않는 길이로
    slug, n = build_site.build(SAMPLE, tmp_path / "s", org="BEGIN:VCARD", note=evil)
    for p in (tmp_path / "s" / slug / "m").glob("*.vcf"):
        raw = p.read_bytes()
        lines = raw.split(b"\r\n")
        assert lines.count(b"BEGIN:VCARD") == lines.count(b"END:VCARD") == n - 1  # 메모·모임 이름 안의 글자는 카드가 아니다
        got = cards(raw)
        assert len(got) == n - 1 and all(c["FN"] != "Evil" and "9999" not in digits(c["TEL"]) for c in got)
        assert all(c["NOTE"] == evil.replace("\r\n", "\\n") and c["ORG"] == "BEGIN:VCARD" for c in got)


def run_cli(*args):
    cmd = [sys.executable, "-X", "utf8", str(ROOT / "build_site.py"), *map(str, args)]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})


def test_missing_or_broken_inputs_get_a_plain_message_not_a_traceback(tmp_path):
    (tmp_path / "bad.xlsx").write_bytes(b"not a zip")
    (tmp_path / "dir.csv").mkdir()
    (tmp_path / "file").write_text("x")
    (tmp_path / "empty.csv").write_bytes(b"")
    (tmp_path / "long.csv").write_bytes(("번호,이름,전화번호\n1," + "가" * 200000 + ",010-0000-0001\n2,나,010-0000-0002\n").encode())  # csv 한 칸 한도(131072자)를 넘는다
    (tmp_path / "big.csv").write_bytes("번호,이름,전화번호\n1e300,가,010-0000-0001\n2,나,010-0000-0002\n".encode())  # 300자리 번호 = 윈도 경로 길이를 넘는 파일 이름
    for args, want in (
        ((tmp_path / "없는파일.csv", tmp_path / "s1"), "못 찾았어요"),
        ((tmp_path / "dir.csv", tmp_path / "s2"), "못 찾았어요"),  # 폴더를 명단으로 준 경우
        ((tmp_path / "bad.xlsx", tmp_path / "s3"), "xlsx 명단을 못 열었어요"),
        ((SAMPLE, tmp_path / "file"), "자리에 파일이 있어요"),
        ((tmp_path / "empty.csv", tmp_path / "s4"), "두 명 이상"),
        ((tmp_path / "long.csv", tmp_path / "s5"), "한 칸이 너무 길어요"),
        ((tmp_path / "big.csv", tmp_path / "s6"), "번호가 숫자가 아니에요"),
        ((SAMPLE, tmp_path / "s7", "--slug", "NUL"), "64자까지"),  # 윈도에서 NUL 폴더는 못 만든다
        ((SAMPLE, tmp_path / "file" / "s8"), "쓰지 못했어요"),  # 파일 아래에는 폴더를 못 만든다(운영체제가 거부하는 경우)
    ):
        r = run_cli(*args)
        assert r.returncode == 1 and want in r.stderr and "Traceback" not in r.stderr, (args, r.stderr)
        assert not (tmp_path / args[1].name).exists() or args[1].name == "file"  # 아무것도 만들지 않는다


def test_roster_numbers_are_whole_and_at_most_nine_digits():
    ok = build_site.parse([("999999999", "가", "010-0000-0001"), ("1e2", "나", "010-0000-0002")])
    assert [no for no, _, _ in ok] == [999999999, 100]
    for bad in ("1000000000", "1e300", "99999999999999999999", "1e400"):  # 받는 파일 이름이 길어져 윈도에서 못 만든다
        with pytest.raises(SystemExit) as e:
            build_site.parse([(bad, "가", "010-0000-0001"), ("2", "나", "010-0000-0002")])
        assert "2번째 줄: 번호가 숫자가 아니에요" in str(e.value), bad


def test_xlsx_without_openpyxl_gets_an_install_hint(tmp_path, monkeypatch):
    (tmp_path / "r.xlsx").write_bytes(b"x")
    monkeypatch.setitem(sys.modules, "openpyxl", None)  # 설치 안 된 것처럼
    with pytest.raises(SystemExit) as e:
        build_site.read_table(tmp_path / "r.xlsx")
    assert "pip install openpyxl" in str(e.value)


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
    assert "그룹·라벨" in readme and "확인하지 못" in readme and "그룹·라벨" in verified  # 파일 안 모임 이름이 그룹이 되는지는 미확인이라고 적는다(#8)
    assert f'"{ORG}"로 검색' in page and "이 이름으로 검색" in readme
    assert "못 한 것" in verified and "미확인" in readme  # 못 한 것을 숨기지 않는다
