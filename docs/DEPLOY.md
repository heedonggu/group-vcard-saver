# 배포하기 (GitHub Pages 예시) — 개인정보 주의

만들어진 `site/<주소>/` 는 정적 파일이라 **아무 정적 호스팅**에 올리면 됩니다(GitHub Pages, Cloudflare Pages, Netlify, 사내 서버…).

## 먼저 알아 둘 것

- 올리는 순간 **링크를 아는 누구나 전원의 이름·번호를 볼 수 있습니다.** 모임 밖으로 퍼지지 않게 단톡방 같은 곳에만 공유하세요.
- 주소는 무작위 16자라 추측하기 어렵지만 "비공개"는 아닙니다. 검색 노출을 막는 `noindex` 가 들어 있습니다.
- **공개 저장소에 실제 명단·만들어진 파일을 커밋하지 마세요.** 이 저장소의 `.gitignore` 는 `site/` 와 명단 파일을 막아 두었지만, 직접 만든 저장소에서는 스스로 확인하세요.

## GitHub Pages — 실제 명단을 비밀값(secret)으로 올리는 방법

저장소 소스에는 번호를 넣지 않고, 배포할 때만 Actions 비밀값에서 사이트를 풀어 올리는 방식입니다.

1. 내 컴퓨터에서 만든다: `python build_site.py 명단.csv site --org "우리 모임"`
2. 만든 폴더를 비밀값으로 올린다 (GitHub CLI):
   ```bash
   cd site && tar czf - <만들어진주소> | base64 -w0 | gh secret set SITE_B64 --repo <내계정>/<내저장소>
   ```
3. 저장소에 아래 워크플로를 넣고(`.github/workflows/pages.yml`), Settings → Pages → Source 를 **GitHub Actions** 로 바꾼다.
4. 실행: `gh workflow run pages.yml --repo <내계정>/<내저장소>`
5. **배포가 끝나면 Actions 아티팩트를 지운다.** 공개 저장소에서는 아티팩트(= 만들어진 사이트)를 로그인한 누구나 받을 수 있습니다.
   ```bash
   for id in $(gh api repos/<내계정>/<내저장소>/actions/artifacts --jq '.artifacts[].id'); do gh api -X DELETE repos/<내계정>/<내저장소>/actions/artifacts/$id; done
   ```
6. 명단이 바뀌면 1·2·4·5 를 다시. 같은 `site/` 폴더에 다시 만들면 **주소가 그대로**라 이미 뿌린 링크가 살아 있습니다.

`pages.yml`:

```yaml
name: pages
on:
  workflow_dispatch:
permissions:
  contents: read
  pages: write
  id-token: write
concurrency:
  group: pages
  cancel-in-progress: true
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - name: unpack site from secret
        env:
          SITE_B64: ${{ secrets.SITE_B64 }}
        run: |
          mkdir _site
          printf '%s' "$SITE_B64" | base64 -d | tar xz -C _site
          test -n "$(ls -A _site)"
      - uses: actions/configure-pages@v6
      - uses: actions/upload-pages-artifact@v5
        with:
          path: _site
      - id: deployment
        uses: actions/deploy-pages@v5
```

- 트리거는 `workflow_dispatch`(손으로 실행)만 둡니다. PR 이 비밀값을 쓰게 되는 설정(`pull_request_target` 등)을 넣지 마세요.
- 한 번에 올릴 수 있는 비밀값은 48 KB 까지입니다. 명단이 아주 커지면 `tar` 대신 다른 방법이 필요합니다.

## 올리기 전 점검

- [ ] 폰(사파리·크롬)에서 링크를 열어 이름 목록이 보이는가
- [ ] 내 이름 → 체크 목록 → 저장이 되는가 (아이폰은 [README](../README.md) 4단계)
- [ ] 검색에 노출되지 않는가(`noindex`), 저장소 소스에 번호가 없는가
- [ ] 링크를 단톡방 밖에 공유하지 않기로 했는가
