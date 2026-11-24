# group-vcard-saver — 모임 연락처, 링크 하나로 한 번에 저장

명단(csv·xlsx)을 넣으면 **"내 이름 누르고 → 체크하고 → 저장"** 하는 정적 페이지가 만들어집니다.
서버·DB·계정·추적 스크립트가 없습니다. 모임 총무가 단톡방에 링크 하나만 올리면 됩니다.

> **라이선스 안내** — 비상업적 용도(모임·동호회·학교·비영리·개인)는 자유롭게 쓰세요([PolyForm Noncommercial 1.0.0](LICENSE)).
> **상업적 용도로 쓰고 싶다면 같이 참여해서 개발해요.** → [COMMERCIAL.md](COMMERCIAL.md)
> (소스가 공개된 라이선스이며, OSI 기준의 오픈소스 라이선스는 아닙니다.)

**미리 써 보기(가짜 명단):** <https://heedonggu.github.io/group-vcard-saver/demo/>

## 무엇을 하나

- 명단의 사람마다 **본인을 뺀** 연락처 파일(`m/<번호>.vcf`, vCard 3.0)을 만듭니다.
- 페이지에서 본인 이름을 입력하거나 누르면 나머지 사람이 체크 목록으로 나오고, **빼고 싶은 사람은 체크를 끄고** 맨 아래 "N명 저장"을 누릅니다.
- 전원을 고르면 올려 둔 파일을 그대로, 일부만 고르면 페이지가 그 사람들만 담은 파일을 그 자리에서 만듭니다.
- 주소 끝에 `?me=<번호>`를 붙이면 이름 고르는 화면 없이 바로 그 사람 목록이 열립니다.
- 카카오톡 안 브라우저에서 열면 기본 브라우저로 넘기려고 시도합니다(비공식 스킴이라 보장하지 않습니다).

## 빠른 시작

```bash
git clone https://github.com/heedonggu/group-vcard-saver
cd group-vcard-saver
pip install -r requirements.txt            # xlsx 명단을 읽을 때만 필요합니다(csv 는 필요 없음)
python build_site.py sample/roster.sample.csv site --org "우리 모임"   # 윈도우는 py build_site.py ...
python -m http.server --directory site     # 열기: http://localhost:8000/<만들어진 주소>/
```

- 명단 형식: **첫 줄은 제목줄**, 열은 `번호, 이름, 전화번호`(010 휴대폰). csv(UTF-8, 엑셀의 CP949 csv)와 xlsx 를 읽습니다. 예시는 [sample/roster.sample.csv](sample/roster.sample.csv)(전부 가짜).
- `--org` 는 폰 연락처의 회사명이 됩니다. 저장한 뒤 연락처에서 이 이름으로 검색하면 전원이 나옵니다.
- 주소 끝(slug)은 **추측할 수 없는 무작위 16자**가 기본이고, 같은 폴더에 다시 만들면 그대로 유지됩니다(이미 뿌린 링크가 죽지 않게). 직접 정하려면 `--slug`.
- 배포는 아무 정적 호스팅이나 됩니다. GitHub Pages 로 올리는 방법과 **개인정보 주의**는 [docs/DEPLOY.md](docs/DEPLOY.md).

## 폰에서 저장하는 법

**아이폰 (사파리에서 열어야 합니다)**

1. "저장"을 누르면 **첫 사람 한 명만** 보이는 화면이 뜹니다. 정상입니다.
2. 그 화면 **오른쪽 위** 공유 버튼을 누릅니다.
3. 뜨는 창에서 **"연락처"** 를 누릅니다("복사" 아래 목록에 있고, 위 아이콘 줄에도 있습니다).
4. 사람 목록 화면이 뜨면 **오른쪽 위 "저장"** 을 누릅니다. 한꺼번에 저장됩니다.

**안드로이드 (크롬)**

1. "저장"을 누르면 화면 위에 "다운로드 완료 · 열기"가 뜹니다. **"열기"** 를 누릅니다. 놓쳤다면 알림이나 "내 파일"의 다운로드에서 받은 파일을 눌러도 됩니다.
2. "연락처를 저장할 곳"을 묻는 창이 뜨면 **계정(또는 "기기")** 을 고릅니다. 한꺼번에 저장됩니다.

(삼성 인터넷·갤럭시 연락처 등은 확인하지 못했습니다 → [docs/VERIFIED.md](docs/VERIFIED.md))

## 확인한 것과 못 한 것 (정직하게)

| 환경 | 확인 방법 | 결과 |
|---|---|---|
| iOS 18.6 시뮬레이터(영어·한국어), iOS 26.5(영어) | 맥 러너에서 사파리 → 공유 → 연락처 → 저장을 누르고 연락처 DB를 직접 셈 | 위 4단계로 저장됨, 일부만 고른 파일도 됨 |
| 실제 아이폰 | 없음 | **미확인** |
| 안드로이드 14 에뮬레이터(크롬 + 구글 연락처, 영어 화면) | 우분투 러너에서 크롬 → "저장" → "열기" → 저장할 곳 선택을 누르고 연락처 수를 직접 셈 | 위 순서로 **전원 저장됨** |
| 실제 안드로이드, 삼성 인터넷·갤럭시 연락처, 한국어 안드로이드 | 없음 | **미확인 — 보고를 부탁드려요** |

자세한 측정값과 방법은 [docs/VERIFIED.md](docs/VERIFIED.md). 실기기 결과는 이슈 양식 **"기기 확인 보고"** 로 알려 주세요.

## 한계 (웹 페이지로는 안 되는 것)

- **그룹을 만들 수 없습니다.** 웹 페이지는 폰 연락처 앱의 그룹을 직접 만들 수 없습니다. 연락처 파일에 모임 이름(`CATEGORIES`)도 넣어 두지만, 폰이 이것을 그룹·라벨로 받아 주는지는 **확인하지 못했습니다**([docs/VERIFIED.md](docs/VERIFIED.md)). 그래서 모든 연락처의 회사명을 `--org` 로 넣어 두었으니 폰 연락처에서 그 이름으로 검색하면 전원이 나옵니다.
- **중복을 자동으로 건너뛰지 못합니다.** 웹 페이지는 폰의 연락처를 읽을 수 없습니다. 측정한 아이폰 동작(iOS 18.6·26.5 시뮬레이터, 연락처 DB를 직접 센 결과):
  - 오른쪽 위 "저장": 이미 있는 사람도 **새 사람으로 또 만듭니다**(같은 2명을 두 번 → 4명).
  - 머리글 "N개의 연락처 모두 추가"(영어 "Add All N Contacts")는 이름이 같으면 기존 연락처에 합치지만 **같은 번호가 한 번 더 붙고**, 번호만 같고 이름이 다르면 새로 만듭니다.
  - 안드로이드(구글 연락처, 에뮬레이터)는 같은 파일을 다시 가져와도 목록에는 같은 사람으로 묶여 5명 그대로였습니다(내부 기록만 늘어남).
  - 그래서 안내는 **"이미 저장해 둔 사람은 체크를 끄세요"** 입니다.

## 개인정보 — 꼭 읽어 주세요

- 만들어진 페이지·파일에는 **명단의 이름과 전화번호가 그대로 들어 있습니다.** 링크를 받은 사람은 전원의 번호를 볼 수 있습니다. 모임 밖으로 공유하지 마세요.
- 페이지에는 `noindex` 가 걸려 있고 주소는 추측할 수 없게 만들지만, **"비공개"가 아니라 "링크를 아는 사람만"** 입니다.
- **실제 명단을 이 저장소(공개)나 이슈에 올리지 마세요.** 이 저장소의 `sample/` 은 전부 가짜입니다.

## 이슈·기여

이슈는 들어오는 대로 **재현 가능한가 · 고칠 가치가 있는가 · 개발 방향([ROADMAP.md](ROADMAP.md))과 맞는가**를 따져 보고, 적용해 본 뒤 그 결과를 이슈에 남깁니다([docs/TRIAGE.md](docs/TRIAGE.md)).
기여 방법은 [CONTRIBUTING.md](CONTRIBUTING.md), 행동 강령은 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), 보안·개인정보 신고는 [SECURITY.md](SECURITY.md).

## English (short)

Turn a roster (CSV/XLSX, Korean mobile numbers) into a static mobile page: each member opens one link, taps their own name, unticks anyone they already have, and saves everyone else's contacts as one vCard. No server, no database, no tracking. UI text is Korean. Free for **noncommercial** use under PolyForm Noncommercial 1.0.0; if you want to use it commercially, let's co-develop — see [COMMERCIAL.md](COMMERCIAL.md). Real-device reports (especially Android/Samsung) are very welcome.

## 라이선스

[PolyForm Noncommercial License 1.0.0](LICENSE) · Required Notice: Copyright (c) 2026 heedonggu
