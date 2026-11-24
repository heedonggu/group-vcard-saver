"""명단(csv/xlsx) -> 폰에서 '내 이름 누르고 한 번에 저장'하는 정적 페이지.

사용:  py build_site.py 명단.csv site [--org "우리 모임"] [--note "메모"] [--title "페이지 제목"] [--slug 주소끝]

사람마다 '본인을 뺀' 연락처 파일 m/<번호>.vcf 를 만들고, 페이지에서 그 사람들 중 저장할 사람을 고른다.
site 안에 폴더가 이미 있으면 그 이름(slug)을 그대로 쓴다 - 주소가 바뀌면 이미 뿌린 링크가 죽는다.
명단: 첫 줄은 제목줄, 열은 번호·이름·전화번호(010). csv(UTF-8 또는 엑셀 CP949)와 xlsx 를 읽는다.
"""
import argparse
import csv
import html
import json
import re
import secrets
import shutil
import unicodedata
from pathlib import Path

ENCODINGS = ("utf-8-sig", "cp949")  # 한국 엑셀의 'CSV(쉼표로 분리)'는 CP949 다


def read_table(path):
    """제목줄을 뺀 [(번호, 이름, 전화), ...] 를 돌려준다. 끝의 빈 줄은 버리고, 가운데 빈 줄은 parse 가 건너뛴다."""
    path = Path(path)
    if path.suffix.lower() == ".xlsx":
        import openpyxl  # xlsx 를 읽을 때만 필요(csv 는 표준 라이브러리)

        table = [tuple(r) for r in openpyxl.load_workbook(path, data_only=True).active.iter_rows(values_only=True)]
    else:
        raw = path.read_bytes()
        for enc in ENCODINGS:
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise SystemExit("명단 파일 글자 인코딩을 못 읽었어요(UTF-8 또는 CP949 csv).")
        table = [tuple(r) for r in csv.reader(text.splitlines())]
    out = [tuple((list(r) + [None, None, None])[:3]) for r in table[1:]]
    while out and not any(str(c).strip() for c in out[-1] if c is not None):
        out.pop()  # 끝의 빈 줄만 버린다. 가운데 빈 줄을 남겨 둬야 오류 메시지의 줄 번호가 파일과 맞는다
    return out


def parse(table):
    """(번호, 이름, 전화) -> (int, 이름, '010-0000-0001'). 틀린 줄은 모아서 한 번에 알려 준다(전화번호 값은 출력에 안 찍는다)."""
    rows, bad, first = [], [], {}
    for i, (no, name, tel) in enumerate(table, start=2):  # 2 = 제목줄 다음 줄(파일의 줄 번호)
        if not any(str(c).strip() for c in (no, name, tel) if c is not None):
            continue  # 가운데 빈 줄은 건너뛰되 줄 번호는 센다
        try:
            no = int(float(str(no).strip()))
        except (ValueError, OverflowError):
            bad.append(f"{i}번째 줄: 번호가 숫자가 아니에요")
            continue
        if isinstance(tel, float):
            tel = int(tel)
        d = re.sub(r"\D", "", str(tel))
        if len(d) == 10 and d.startswith("10"):  # 엑셀이 앞자리 0을 떼먹은 경우
            d = "0" + d
        name = unicodedata.normalize("NFC", re.sub(r"\s+", " ", str(name or ""))).strip()
        if not name:
            bad.append(f"{i}번째 줄: 이름이 비었어요")
        elif not re.fullmatch(r"010\d{8}", d):
            bad.append(f"{i}번째 줄({name}): 전화번호가 010 휴대폰 번호가 아니에요")
        else:
            tel = f"{d[:3]}-{d[3:7]}-{d[7:]}"
            for what, key in (("전화번호", tel), ("번호(첫 열)", no)):  # 같은 값은 두 번째 줄부터 줄 번호로 알린다
                if (what, key) in first:
                    bad.append(f"{i}번째 줄({name}): 같은 {what}가 {first[what, key]}번째 줄에 이미 있어요")
                first.setdefault((what, key), i)
            rows.append((no, name, tel))
    if not bad and len(rows) < 2:
        bad.append("두 명 이상 있어야 해요")
    if bad:
        raise SystemExit("명단을 고쳐 주세요:\n- " + "\n- ".join(bad))
    return rows


def esc(s):
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


# 이름은 성/이름으로 나누지 않는다(남궁·선우 오분리 방지). 줄 접기 없음: 75바이트가 넘으면 알려 준다(ROADMAP 참고).
def card(name, tel, org, note):
    lines = ["BEGIN:VCARD", "VERSION:3.0", f"N:;{esc(name)};;;", f"FN:{esc(name)}", f"ORG:{esc(org)}", f"CATEGORIES:{esc(org)}", f"TEL;TYPE=CELL:{tel}"]
    if note:
        lines.append(f"NOTE:{esc(note)}")
    return "\r\n".join(lines + ["END:VCARD", ""])


PAGE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>@TITLE@</title>
<meta property="og:title" content="@TITLE@">
<meta property="og:description" content="내 이름을 고르면 나를 뺀 연락처를 골라서 저장할 수 있어요">
<meta property="og:type" content="website">
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#14171c;--sub:#5b6472;--line:#e3e6ea;--accent:#2563eb;--on-accent:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#0e1013;--card:#171a1f;--ink:#eef0f3;--sub:#9aa3b0;--line:#272c34;--accent:#5b8def;--on-accent:#0b1020}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic",sans-serif;-webkit-text-size-adjust:100%;word-break:keep-all;overflow-wrap:break-word}
main{max-width:440px;margin:0 auto;padding:40px 16px 56px}
.tag{display:inline-block;max-width:100%;padding:2px 10px;border:1px solid var(--line);border-radius:999px;font-size:13px;color:var(--sub);overflow-wrap:anywhere}
h1{margin:14px 0 6px;font-size:28px;line-height:1.25;letter-spacing:-.02em}
.lead{margin:0 0 16px;color:var(--sub)}
.names{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.name{display:flex;align-items:center;justify-content:center;min-height:48px;padding:6px 4px;border:1px solid var(--line);border-radius:12px;background:var(--card);color:var(--ink);font-size:16px;font-weight:600;text-decoration:none;text-align:center;overflow-wrap:anywhere}
.name:active{background:var(--accent);border-color:var(--accent);color:var(--on-accent)}
.name:focus-visible{outline:3px solid var(--ink);outline-offset:2px}
.q{width:100%;min-height:52px;margin:0 0 12px;padding:0 16px;border:1px solid var(--line);border-radius:12px;background:var(--card);color:var(--ink);font:inherit;font-size:17px}
.q:focus-visible{outline:3px solid var(--accent);outline-offset:1px}
.after{margin:0 0 16px;padding:12px 14px;border:1px solid var(--line);border-radius:12px;background:var(--card);font-size:15px;color:var(--sub)}
.after p{margin:4px 0}
.after b{color:var(--ink)}
.after ol{margin:2px 0 8px;padding-left:22px}
.after li{margin:3px 0}
.ico{vertical-align:-4px}
.bar{display:flex;align-items:center;gap:8px;margin:0 0 10px}
.bar button{min-height:40px;padding:0 14px;border:1px solid var(--line);border-radius:10px;background:var(--card);color:var(--ink);font:inherit;font-size:15px}
.bar span{margin-left:auto;color:var(--sub);font-size:15px}
.picks{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:0 0 18px;color:var(--sub)}
.pick{display:flex;align-items:center;gap:6px;min-height:44px;padding:4px 8px;border:1px solid var(--line);border-radius:10px;background:var(--card);color:var(--ink);font-size:15px}
.pick input{width:18px;height:18px;margin:0;flex:none}
.pick span{min-width:0;overflow-wrap:anywhere}
.how{margin:28px 0 0;padding:0;list-style:none;display:grid;gap:10px}
.how li{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.how b{display:block;margin-bottom:2px}
.how span{color:var(--sub);font-size:15px}
.note{margin:22px 0 0;color:var(--sub);font-size:14px}
.kakao-note{display:none;margin:0 0 20px;padding:12px 14px;border-radius:12px;background:var(--card);border:1px solid var(--accent);font-size:15px}
.kakao .kakao-note{display:block}
.btn{display:flex;align-items:center;justify-content:center;min-height:60px;border-radius:14px;background:var(--accent);color:var(--on-accent);font-size:19px;font-weight:700;text-decoration:none}
.btn:active{opacity:.85}
.btn[aria-disabled=true]{background:var(--line);color:var(--sub);pointer-events:none}
#save{position:sticky;bottom:12px;z-index:2;box-shadow:0 6px 24px rgba(0,0,0,.28)}
[hidden]{display:none!important}
</style>
</head>
<body>
<main>
  <span class="tag">@ORG@</span>
  <h1>연락처 한 번에 저장</h1>
  <p class="kakao-note">카카오톡 안에서는 저장이 막힐 수 있어요. 기본 브라우저가 자동으로 안 열리면, 아이폰은 공유 버튼 → Safari로 열기, 안드로이드는 ⋮ → 다른 브라우저로 열기를 눌러 주세요.</p>
  <section id="mine" hidden>
    <p class="lead"><b id="who"></b>님, 나를 뺀 @COUNT@명이에요. 빼고 싶은 사람이나 이미 저장해 둔 사람은 체크를 끄고(안 끄면 같은 사람이 한 번 더 생겨요), 맨 아래 “저장”을 누르세요.</p>
    <div class="after">
      <p><b>아이폰</b> (Safari에서 열어야 해요)</p>
      <ol>
        <li>“저장”을 누르세요. 첫 사람 한 명만 보이는 화면이 떠요. 정상이에요.</li>
        <li>그 화면 <b>오른쪽 위</b> 공유 버튼 <svg class="ico" width="20" height="20" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12M8 7l4-4 4 4M7 11H5.5a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h13a1 1 0 0 0 1-1v-8a1 1 0 0 0-1-1H17" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg> 을 누르세요.</li>
        <li>뜨는 창에서 <b>“연락처”</b>를 누르세요. “복사” 아래 목록에 있어요. 위 아이콘 줄에도 있으면 한쪽이 안 될 때 다른 쪽을 누르세요.</li>
        <li>고른 사람 목록 화면이 뜨면 <b>오른쪽 위 “저장”</b>을 누르세요. 그러면 한꺼번에 저장돼요.</li>
      </ol>
      <p class="note">연락처가 안 열리고 처음 화면으로 돌아오면 처음부터 한 번 더 해 보세요.</p>
      <p><b>안드로이드</b> (크롬)</p>
      <ol>
        <li>“저장”을 누르면 화면 위에 “다운로드 완료 · 열기”가 떠요. <b>“열기”</b>를 누르세요. 놓쳤다면 알림이나 “내 파일”의 다운로드에서 받은 파일을 눌러도 돼요.</li>
        <li>“연락처를 저장할 곳”을 묻는 창이 뜨면 <b>계정(또는 “기기”)</b>을 고르세요. 그러면 한꺼번에 저장돼요.</li>
      </ol>
    </div>
    <div class="bar"><button type="button" id="all">모두 선택</button><button type="button" id="none">모두 해제</button><span id="cnt"></span></div>
    <div class="picks" id="picks">불러오는 중…</div>
    <a class="btn" id="save" href="./">저장</a>
    <p class="note"><a href="./">내 이름이 아니에요</a></p>
  </section>
  <div id="list">
    <p class="lead">내 이름을 입력하거나 누르세요. 나를 뺀 @COUNT@명 중에서 골라 저장할 수 있어요.</p>
    <input id="q" class="q" type="search" placeholder="내 이름 입력" autocomplete="off" aria-label="내 이름 입력">
    <p id="nomatch" class="note" hidden>일치하는 이름이 없어요.</p>
    <nav class="names" aria-label="내 이름 선택">
@NAMES@
    </nav>
    <ul class="how">
      <li><b>아이폰</b><span>Safari에서 이름을 누르고 “저장” → 한 명만 보이는 화면 오른쪽 위 공유 버튼 → “연락처” → 오른쪽 위 “저장”.</span></li>
      <li><b>안드로이드</b><span>이름을 누르고 “저장” → 화면 위 “열기” → 저장할 계정(또는 기기) 고르기.</span></li>
    </ul>
    <p class="note">저장한 뒤 연락처에서 “@ORG@”로 검색하면 나와요. (연락처 앱의 그룹은 웹 페이지로 만들 수 없어서 이름 검색으로 대신해요.)</p>
    <p class="note">이 링크는 @ORG@ 전용이에요. 밖으로 공유하지 말아 주세요.</p>
  </div>
</main>
<script>
(function () {
  if (/KAKAOTALK/i.test(navigator.userAgent)) {
    document.documentElement.classList.add('kakao');
    location.href = 'kakaotalk://web/openExternal?url=' + encodeURIComponent(location.href);
    return;
  }
  var $ = function (id) { return document.getElementById(id); };
  var items = Array.prototype.slice.call(document.querySelectorAll('a.name'));
  var cards = [], boxes = [];

  var norm = function (s) { return s.replace(/\\s+/g, '').toLowerCase(); };  // 입력과 명단 이름 모두 공백·영문 대소문자를 무시한다
  $('q').addEventListener('input', function () {  // 이름을 입력하면 맞는 이름만 남긴다
    var v = norm($('q').value), n = 0;
    items.forEach(function (a) { var ok = !v || norm(a.textContent).indexOf(v) !== -1; a.hidden = !ok; if (ok) n++; });
    $('nomatch').hidden = n > 0;
  });
  items.forEach(function (a) { a.addEventListener('click', function (e) { e.preventDefault(); show(a); }); });

  function show(a) {  // 내 이름을 고르면 나를 뺀 사람들을 체크 목록으로 보여 준다
    $('who').textContent = a.textContent;
    $('save').href = a.href;
    $('save').setAttribute('download', @FILE_JS@);  // 안드로이드 브라우저가 파일로 받게 한다. 아이폰 사파리는 이 속성을 무시하고 첫 사람 미리보기를 띄운다(공유 버튼은 오른쪽 위, iOS 18.6·26.5 시뮬레이터 확인)
    $('list').hidden = true;
    $('mine').hidden = false;
    $('picks').textContent = '불러오는 중…';
    cards = []; boxes = [];
    window.scrollTo(0, 0);
    fetch(a.href).then(function (r) { return r.text(); }).then(function (t) {
      cards = t.split(/(?=BEGIN:VCARD)/).filter(function (c) { return /BEGIN:VCARD/.test(c); });
      $('picks').textContent = '';
      cards.forEach(function (c) {
        var l = document.createElement('label'), b = document.createElement('input'), s = document.createElement('span');
        l.className = 'pick'; b.type = 'checkbox'; b.checked = true; b.addEventListener('change', count);
        s.textContent = ((c.match(/^FN:(.*?)\\r?$/m) || [])[1] || '').replace(/\\\\([\\\\;,])/g, '$1');  // 연락처 파일에서 글자 앞에 붙인 역슬래시를 뗀다(쉼표·세미콜론·역슬래시)
        l.appendChild(b); l.appendChild(s); $('picks').appendChild(l); boxes.push(b);
      });
      count();
    }).catch(function () { $('picks').textContent = '목록을 못 불러왔어요. 저장을 누르면 전원이 저장돼요.'; });
  }
  function count() {
    var n = boxes.filter(function (b) { return b.checked; }).length;
    $('cnt').textContent = n + '명 선택';
    $('save').textContent = n ? n + '명 저장' : '고른 사람이 없어요';
    $('save').setAttribute('aria-disabled', n ? 'false' : 'true');
  }
  function setAll(v) { boxes.forEach(function (b) { b.checked = v; }); count(); }
  $('all').addEventListener('click', function () { setAll(true); });
  $('none').addEventListener('click', function () { setAll(false); });

  $('save').addEventListener('click', function (e) {
    var picked = cards.filter(function (c, i) { return boxes[i] && boxes[i].checked; });
    if (!cards.length || picked.length === cards.length) return;  // 전원이면 올려 둔 파일을 그대로 받는다
    e.preventDefault();
    if (!picked.length) return;
    var a = document.createElement('a');  // 일부만 고르면 그 사람들만 담은 파일을 바로 만든다
    a.href = URL.createObjectURL(new Blob([picked.join('')], { type: 'text/vcard' }));
    a.download = @FILE_JS@;
    document.body.appendChild(a); a.click(); a.remove();
  });

  var me = (location.search.match(/[?&]me=(\\d+)/) || [])[1];
  var mine = me && document.querySelector('a.name[data-no="' + me + '"]');
  if (mine) show(mine);
})();
</script>
</body>
</html>
"""


def render(rows, org, title):
    fname = re.sub(r'[\\/:*?"<>|\s]+', "-", org).strip("-") or "contacts"
    vals = {
        "TITLE": html.escape(title),
        "ORG": html.escape(org),
        "FILE_JS": json.dumps(fname + ".vcf", ensure_ascii=False).replace("<", "\\u003c"),
        "COUNT": str(len(rows) - 1),
        "NAMES": "\n".join(f'    <a class="name" href="m/{no}.vcf" data-no="{no}">{html.escape(name)}</a>' for no, name, _ in rows),
    }
    return re.sub(r"@(TITLE|ORG|FILE_JS|COUNT|NAMES)@", lambda m: vals[m.group(1)], PAGE)  # 한 번에 바꾼다(바뀐 글자를 다시 훑지 않는다)


def build(src, site, org="우리 모임", note="", title=None, slug=None):
    """site/<slug>/index.html + site/<slug>/m/<번호>.vcf 를 만들고 (slug, 사람 수)를 돌려준다."""
    rows = parse(read_table(src))
    site = Path(site)
    old = [d.name for d in site.iterdir() if d.is_dir()] if site.exists() else []
    if len(old) > 1:
        raise SystemExit(f"site 안 폴더가 둘 이상이에요: {old}")
    if slug and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", slug):
        raise SystemExit("slug 는 영문·숫자·-_ 만 쓸 수 있어요")
    if slug and old and old[0] != slug:
        raise SystemExit(f"site 안에 다른 주소({old[0]})가 이미 있어요. 지우거나 --slug {old[0]} 로 맞춰 주세요")
    slug = slug or (old[0] if old else secrets.token_hex(8))
    cards = {no: (name, tel, card(name, tel, org, note)) for no, name, tel in rows}
    if any(len(l.encode("utf-8")) > 75 for _, _, c in cards.values() for l in c.split("\r\n")):  # 폴더를 건드리기 전에 알린다
        raise SystemExit("한 줄이 75바이트를 넘어요: --org/--note 나 명단의 이름을 줄여 주세요(한글 약 23자)")
    out = site / slug
    shutil.rmtree(out, ignore_errors=True)  # 이전 빌드 산출물 정리(줄어든 명단의 옛 파일이 남지 않게)
    (out / "m").mkdir(parents=True)
    for no, (name, tel, _) in cards.items():
        raw = "".join(c for k, (_, _, c) in cards.items() if k != no).encode("utf-8")
        assert raw.startswith(b"BEGIN:VCARD\r\nVERSION:3.0\r\n"), "BOM/헤더 이상"
        assert b"\n" not in raw.replace(b"\r\n", b""), "CRLF 아닌 줄바꿈"
        assert raw.count(b"BEGIN:VCARD") == raw.count(b"END:VCARD") == len(rows) - 1, "카드 수 불일치"
        assert tel.encode() not in raw, f"본인 번호가 들어감: {name}"
        (out / "m" / f"{no}.vcf").write_bytes(raw)
    (out / "index.html").write_text(render(rows, org, title or f"{org} 연락처 저장"), encoding="utf-8", newline="\n")
    return slug, len(rows)


def main(argv=None):
    p = argparse.ArgumentParser(description="명단 -> 연락처 한 번에 저장 페이지")
    p.add_argument("roster", help="명단 csv 또는 xlsx (제목줄 + 번호·이름·전화번호)")
    p.add_argument("site", help="만들어질 폴더")
    p.add_argument("--org", default="우리 모임", help="연락처의 회사명·페이지 이름. 폰 연락처에서 이 이름으로 검색하면 전원이 나온다")
    p.add_argument("--note", default="", help="연락처 메모(선택)")
    p.add_argument("--title", help="페이지 제목(기본: '<org> 연락처 저장')")
    p.add_argument("--slug", help="주소 끝 이름(기본: 기존 폴더 이름, 없으면 무작위 16자)")
    a = p.parse_args(argv)
    slug, n = build(a.roster, a.site, a.org, a.note, a.title, a.slug)
    print(f"OK {n}명 / 파일 {n}개 / 경로 /{slug}/")


if __name__ == "__main__":
    main()
