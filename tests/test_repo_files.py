"""저장소 점검 시험 — 문서·이슈 양식·워크플로·라벨·개인정보. 실행: py -X utf8 -m pytest -q tests/test_repo_files.py

- git 이 필요한 시험(D11·D12)은 git 저장소가 아니면 건너뛴다. CI 처럼 꼭 돌려야 할 때는 REQUIRE_GIT=1 (없으면 실패).
- GitHub 에서만 알 수 있는 것(CI 성공·라벨이 실제로 있는지·이슈 처리 기록·공개 설정)은 `gh` 로 따로 본다 — docs/TRIAGE.md 의 조회 명령.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
REPO = "heedonggu/group-vcard-saver"
LABELS = {"needs-triage", "accepted", "declined", "needs-info", "bug", "enhancement", "device-report", "commercial-collab", "question"}
GITHUB_PAGES = ("issues", "discussions", "security", "pulls", "actions")  # ../../issues/... 처럼 GitHub 화면을 가리키는 상대 주소
FORM_TYPES = {"markdown", "input", "textarea", "dropdown", "checkboxes"}


def read(rel):
    return (ROOT / rel).read_text("utf-8")


def headings(path):
    text = re.sub(r"```.*?```", "", path.read_text("utf-8"), flags=re.S)
    return [m.group(1).strip() for m in re.finditer(r"^#{1,6}\s+(.*)$", text, re.M)]


def slug(h):  # GitHub 목차 주소: 소문자, 글자·숫자·밑줄·하이픈·공백만 남기고 공백은 하이픈으로
    return re.sub(r"\s", "-", re.sub(r"[^\w\- ]", "", h.lower()))


def git(*args):
    if not shutil.which("git") or not (ROOT / ".git").exists():
        msg = "git 저장소가 아니에요"
        if os.environ.get("REQUIRE_GIT"):
            pytest.fail(msg)
        pytest.skip(msg)
    r = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=ROOT, capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", "replace")


# ---- 문서 (D01~D09) -------------------------------------------------------

def test_relative_links_in_docs_point_to_real_files_and_headings():  # D01
    bad = []
    for md in sorted([*ROOT.glob("*.md"), *(ROOT / "docs").glob("*.md")]):
        text = re.sub(r"```.*?```", "", md.read_text("utf-8"), flags=re.S)
        for target in re.findall(r"\]\(([^)\s]+)\)", text):
            if re.match(r"[a-z][a-z0-9+.-]*:", target):  # https: mailto: 등
                continue
            path, _, frag = target.partition("#")
            dest = (md.parent / path).resolve() if path else md
            if not dest.is_relative_to(ROOT):  # ../../issues/new/choose 같은 GitHub 화면 주소
                if not path.replace("../", "").startswith(GITHUB_PAGES):
                    bad.append(f"{md.name}: {target}")
            elif not dest.exists():
                bad.append(f"{md.name}: {target}")
            elif frag and dest.suffix == ".md" and frag not in {slug(h) for h in headings(dest)}:
                bad.append(f"{md.name}: {target}")
    assert not bad, bad


def test_readme_has_the_required_sections_and_the_notices_at_the_top():  # D01 D03
    heads = " | ".join(headings(ROOT / "README.md"))
    for need in ["무엇을 하나", "빠른 시작", "폰에서 저장하는 법", "확인한 것과 못 한 것", "한계", "개인정보", "이슈·기여", "English", "라이선스"]:
        assert need in heads, need
    readme = read("README.md")
    top = "\n".join(readme.splitlines()[:12])
    assert "COMMERCIAL.md" in top and "LICENSE" in top and "OSI" in top  # 상업 안내·라이선스·"오픈소스는 아님"이 맨 위에 있다
    assert "https://heedonggu.github.io/group-vcard-saver/demo/" in readme  # D13 이 여는 데모 주소


def test_license_is_polyform_noncommercial_with_required_notice():  # D02
    lic = read("LICENSE")
    assert "# PolyForm Noncommercial License 1.0.0" in lic
    assert "https://polyformproject.org/licenses/noncommercial/1.0.0" in lic
    assert re.search(r"^Required Notice: Copyright .+", lic, re.M)


def test_commercial_page_invites_co_development_through_the_issue_form():  # D03
    text = read("COMMERCIAL.md")
    form = yaml.safe_load(read(".github/ISSUE_TEMPLATE/commercial_collab.yml"))
    assert "같이" in text and "개발" in text
    assert form["name"] in text  # 안내가 가리키는 양식 이름이 실제 양식과 같다
    assert "../../issues/new/choose" in text


def test_contributing_commands_match_the_dev_setup():  # D04
    text = read("CONTRIBUTING.md")
    assert "pip install -r requirements-dev.txt" in text and "python -m pytest -q" in text
    assert "playwright install" in text and "playwright" in read("requirements-dev.txt")
    assert "기여물의 라이선스" in text and "PR" in text


def test_conduct_security_and_pr_template_have_what_they_promise():  # D05 D06 D08
    coc = read("CODE_OF_CONDUCT.md")
    assert "개인정보" in coc and "전화번호" in coc
    sec = read("SECURITY.md")
    assert "security/advisories/new" in sec  # 신고 경로
    for need in ["범위", "응답 목표", "3일"]:
        assert need in sec, need
    pr = read(".github/PULL_REQUEST_TEMPLATE.md")
    assert "pytest" in pr and "전화번호" in pr


def test_issue_forms_follow_the_github_schema():  # D07
    forms = sorted((ROOT / ".github/ISSUE_TEMPLATE").glob("*.yml"))
    assert {f.stem for f in forms} == {"bug_report", "device_report", "feature_request", "commercial_collab", "config"}
    for f in forms:
        d = yaml.safe_load(f.read_text("utf-8"))
        if f.stem == "config":
            assert d["blank_issues_enabled"] is False
            assert d["contact_links"] and all({"name", "url", "about"} <= set(c) and c["url"].startswith("https://") for c in d["contact_links"])
            continue
        assert {"name", "description", "body", "labels"} <= set(d), f.name
        assert "needs-triage" in d["labels"] and set(d["labels"]) <= LABELS, f.name
        required = 0
        for b in d["body"]:
            assert b["type"] in FORM_TYPES, f.name
            if b["type"] == "markdown":
                assert b["attributes"]["value"], f.name
                continue
            assert b["attributes"].get("label"), f.name
            if b["type"] == "checkboxes":
                required += sum(bool(o.get("required")) for o in b["attributes"]["options"])
            elif b.get("validations", {}).get("required"):
                required += 1
            if b["type"] == "dropdown":
                assert len(b["attributes"]["options"]) >= 2, f.name
        assert required >= 1, f.name  # 필수 항목이 있다


def test_changelog_and_roadmap_have_what_issue_triage_needs():  # D09 E02
    assert re.search(r"^## \[\d+\.\d+\.\d+\] - \d{4}-\d{2}-\d{2}", read("CHANGELOG.md"), re.M)
    heads = headings(ROOT / "ROADMAP.md")
    for need in ["목표", "원칙", "지금", "다음 후보", "하지 않는 것"]:
        assert any(need in h for h in heads), need
    text = read("ROADMAP.md")
    assert len(re.findall(r"^\d+\. \*\*", text.split("## 지금")[0], re.M)) >= 5  # 원칙
    skipped = [ln for ln in text.split("## 하지 않는 것")[1].splitlines() if ln.startswith("- ")]
    assert len(skipped) >= 4 and all("—" in ln for ln in skipped), skipped  # 하지 않는 것마다 이유가 붙는다


# ---- 이슈 처리 절차 (E01, E03, E04, E06) -----------------------------------

def test_triage_doc_has_the_whole_procedure():  # E01
    text = read("docs/TRIAGE.md")
    heads = " | ".join(headings(ROOT / "docs/TRIAGE.md"))
    for need in ["접수", "분류", "판단 기준", "적용해 보기", "결과를 이슈에 올리기", "지키는 것", "메인테이너용 명령"]:
        assert need in heads, need
    judge = text.split("## 3.")[1].split("## 4.")[0]
    assert len(re.findall(r"^\d\. \*\*", judge, re.M)) == 5  # 다섯 질문
    for word in ["수용", "보류", "거절"]:
        assert word in judge, word
    assert "**결과: 수용(적용함) / 보류 / 거절**" in text


def test_triage_workflow_labels_and_comments_with_working_links():  # E03
    wf = yaml.safe_load(read(".github/workflows/triage.yml"))
    on = wf.get("on", wf.get(True))  # PyYAML 은 키 on 을 True 로 읽는다
    assert on["issues"]["types"] == ["opened"]
    assert wf["permissions"] == {"issues": "write"}
    run = "\n".join(s.get("run", "") for j in wf["jobs"].values() for s in j["steps"])
    assert "--add-label needs-triage" in run and "gh issue comment" in run
    links = re.findall(r"\]\(([^)]+)\)", run)
    assert links and all(link.startswith("https://github.com/${REPO}/blob/main/") for link in links)  # 이메일 알림에서도 열리는 절대 주소
    for link in links:
        assert (ROOT / link.split("/blob/main/")[1]).exists(), link


def test_labels_file_matches_triage_doc_and_issue_forms():  # E04
    labels = yaml.safe_load(read(".github/labels.yml"))
    assert {lab["name"] for lab in labels} == LABELS
    assert all(re.fullmatch(r"[0-9a-f]{6}", str(lab["color"])) and lab["description"] for lab in labels)
    triage = read("docs/TRIAGE.md")
    for name in LABELS:
        assert f"`{name}`" in triage, name
    assert "'label', 'create'" in triage and ".github/labels.yml" in triage  # 라벨을 만드는 명령이 문서에 있다


def test_triage_commands_are_well_formed_gh_commands_for_this_repo():  # E06
    text = read("docs/TRIAGE.md")
    cmds = [ln.split("  #")[0].strip() for b in re.findall(r"```bash\n(.*?)```", text, re.S) for ln in b.splitlines() if ln.startswith("gh ")]
    for c in cmds:
        assert f"--repo {REPO}" in c, c
        assert re.match(r"gh (issue (list|view|edit|comment|close)|run list|label list) ", c), c
    reads = [c for c in cmds if re.match(r"gh (issue (list|view)|run list|label list) ", c)]
    assert len(reads) >= 5 and len(cmds) >= 8
    assert "<" not in " ".join(reads)  # 조회 명령은 그대로 붙여 넣어 돌릴 수 있다
    assert REPO in read("README.md")  # 명령의 저장소가 README 가 말하는 저장소와 같다


def test_ci_and_demo_workflows_run_the_tests_and_build_the_sample():  # D10 D13
    ci = yaml.safe_load(read(".github/workflows/ci.yml"))
    assert {"push", "pull_request"} <= set(ci.get("on", ci.get(True)))
    job = ci["jobs"]["test"]
    runs = "\n".join(s.get("run", "") for s in job["steps"])
    assert "python -m pytest" in runs and "playwright install" in runs and "build_site.py sample/roster.sample.csv" in runs
    assert job["env"]["REQUIRE_BROWSER"] == "1" and job["env"]["REQUIRE_GIT"] == "1"  # 시험이 조용히 건너뛰어지지 않는다
    assert any(s.get("with", {}).get("fetch-depth") == 0 for s in job["steps"])  # git 기록 전체
    demo = read(".github/workflows/demo-pages.yml")
    assert "build_site.py sample/roster.sample.csv" in demo and "--slug demo" in demo and "deploy-pages" in demo


# ---- 개인정보·git (D11, D12) -----------------------------------------------
# D12 의 범위 = 저장소에 올라가는 것: git 이 추적하는 파일 전부(`git ls-files`) + 모든 브랜치·태그의 커밋 내용.
# 추적하지 않는 파일(실제 명단·만든 사이트·도구 폴더)은 올라가지 않는다. 명단·사이트가 올라가지 않게 막는 것은 D11 이다.

PHONE = re.compile(r"(?<!\d)01[016789][-\s.]?\d{3,4}[-\s.]?\d{4}(?!\d)")
FAKE = re.compile(r"0100000\d{4}")  # 010-0000-xxxx
EMAIL = re.compile(r"\b\w[\w.+-]*@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}")  # 글자로 시작 — 변경 기록의 "+@pytest.fixture" 는 주소가 아니다
HOME = re.compile(r"(?i)\b[a-z]:[\\/]+users[\\/]+[^\\/\s]+|(?<![\w.:/-])/(?:Users|home)/[^/\s]+")  # 내 컴퓨터의 사용자 폴더 경로(사용자 이름이 드러난다)


def leaks(text):  # 어디(줄 번호)인지만 돌려준다 — 찾은 번호·주소·경로는 출력에 찍지 않는다
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        out += [f"{n}행: 가짜가 아닌 번호꼴" for m in PHONE.finditer(line) if not FAKE.fullmatch(re.sub(r"\D", "", m.group()))]
        out += [f"{n}행: 이메일 주소" for e in EMAIL.findall(line) if "noreply" not in e and "example." not in e]
        out += [f"{n}행: 내 컴퓨터의 사용자 폴더 경로" for _ in HOME.finditer(line)]
    return out


def test_leak_check_catches_what_it_should_and_lets_fake_values_pass():  # D12 (검사기 자체)
    assert leaks("010-0000-0003, 01000000004, user@example.com, 12345@users.noreply.github.com, actions/checkout@v7, +@pytest.fixture()") == []
    assert leaks("https://example.com/home/page, C:\\Windows\\System32, ~/.cache, /usr/bin/python, 사용자 폴더") == []
    real = "010" + "-1234-" + "5678"  # 이 파일 자신이 검사에 걸리지 않게, 파일에는 이어 붙은 모양으로 적지 않는다
    assert len(leaks("전화 " + real)) == 1 and len(leaks(real.replace("-", ""))) == 1
    assert len(leaks("연락 a.b" + "@gmail.com")) == 1
    assert len(leaks("폴더 C:" + "\\Us" + "ers\\kim\\x")) == 1 and len(leaks("폴더 c:" + "/us" + "ers/kim")) == 1  # 윈도우
    assert len(leaks("폴더 /ho" + "me/kim/x")) == 1 and len(leaks("폴더 /Us" + "ers/kim")) == 1  # 리눅스·맥


def test_gitignore_blocks_real_rosters_and_built_sites():  # D11
    for path in ["roster.xlsx", "명단.csv", "site/abcd/index.html", "_site/x"]:
        assert git("check-ignore", "-q", path)[0] == 0, path
    assert git("ls-files", "--error-unmatch", "sample/roster.sample.csv")[0] == 0  # 가짜 명단은 추적된다
    assert git("check-ignore", "-q", "sample/roster.sample.csv")[0] == 1


def test_no_real_numbers_emails_or_home_paths_in_files_or_git_history():  # D12
    bad, scanned = [], 0
    for rel in filter(None, git("ls-files", "-z")[1].split("\0")):
        try:
            text = (ROOT / rel).read_text("utf-8")
        except (UnicodeDecodeError, OSError):  # 글이 아닌 파일은 훑어볼 수 없으니, 조용히 넘기지 않고 실패로 센다
            bad.append(f"{rel} 글이 아니라서 검사하지 못했어요")
            continue
        scanned += 1
        bad += [f"{rel} {x}" for x in leaks(text)]
    history = git("log", "--all", "-p", "--format=", "--no-color")[1]
    bad += [f"git 기록 {x}" for x in leaks(history)]
    bad += ["git 기록에 글이 아닌 파일이 있어요(검사하지 못했어요)"] * bool(re.search(r"^(Binary files |GIT binary patch)", history, re.M))
    assert scanned >= 20 and history.count("\n") > 1000, (scanned, "추적 파일·기록이 비정상적으로 적다 — 검사가 빈손으로 통과하면 안 된다")
    assert not bad, bad[:10]


def test_no_roster_or_built_site_files_were_ever_committed():  # D12
    names = {n for n in git("log", "--all", "--name-only", "--format=", "--no-color")[1].splitlines() if n}
    odd = sorted(n for n in names if re.search(r"\.(xlsx?|vcf)$", n) or (n.endswith(".csv") and not n.startswith("sample/")) or n.split("/")[0] in ("site", "_site", "public"))
    assert not odd, odd
