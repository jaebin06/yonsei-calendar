# 연세 통합 일정 캘린더

학사일정·대회·자격증 시험·인턴 공고를 자동으로 모으고, 내 기준으로 걸러서 **구글 캘린더 구독 주소(ICS)**로 내보내는 개인용 시스템. 갤럭시 삼성 캘린더에는 구글 계정 동기화로 자동 표시된다.

- 서버 없음: GitHub Actions가 매일 06:00(KST)에 돌고, 결과를 GitHub Pages에 올린다.
- 과제는 크롤링하지 않는다: LearnUs 캘린더 내보내기 주소를 **개인 서버(Cloudflare Worker)**가 읽는다. 그 주소에는 로그인 토큰이 들어 있어서 GitHub Secret에만 두고 **이 저장소와 공개 페이지에는 절대 넣지 않는다.**
- 완료 체크·내 일정 선택·추천 안 함은 개인 서버(KV)에 저장되어 폰과 PC에서 같이 보인다.
- 구글 캘린더에는 개인 서버의 '내 일정' 구독 주소 하나만 넣는다: 학사·기숙사·LearnUs는 기본 포함, 대회·인턴은 내가 고른 것만, 완료한 건 ✅.

## 구조

```
worker/          개인 서버 (상태 저장, LearnUs 읽기, 내 일정 피드)
yc/collectors/   소스별 수집기 (dev-event, wevity, yonsei 공지, linkareer 인턴, 생활관)
yc/score.py      하드 필터 + 0~100점 점수화
yc/ics.py        ICS 피드 생성
yc/build.py      전체 파이프라인 (python -m yc.build)
config/profile.yaml       관심 키워드·지역·커트라인
data/manual/*.yaml        학사일정·자격증 시험 (손으로 관리)
data/overrides.yaml       별표·숨기기·직접 추가 (이슈로 자동 반영)
data/events.json          지난 실행 상태 (first_seen 유지용, 봇이 커밋)
site/index.html           대시보드
```

## 처음 설정 (한 번만)

1. **Settings → Pages → Source: GitHub Actions** 선택
2. **Settings → Actions → General → Workflow permissions: Read and write**
3. **Actions** 탭 → `daily-build` → **Run workflow**
4. 몇 분 뒤 `https://jaebin06.github.io/yonsei-calendar/` 에서 대시보드 확인

### 개인 서버 (Cloudflare Worker)

1. https://dash.cloudflare.com 가입 → **Workers & Pages**에 한 번 들어가서 workers.dev 하위 도메인 정하기
2. **My Profile → API Tokens → Create Token → 'Edit Cloudflare Workers' 템플릿**으로 토큰 만들기
3. 대시보드 오른쪽의 **Account ID** 복사
4. GitHub 저장소 **Settings → Secrets and variables → Actions**에 4개 추가
   - `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`
   - `APP_KEY`: 대시보드 연결용 비밀번호 (길게, 아무 문자열)
   - `LEARNUS_URL`: LearnUs 캘린더 내보내기 주소
5. **Actions → deploy-worker → Run workflow** → 로그 끝에 나오는 `https://yonsei-calendar.○○.workers.dev` 주소 확인
6. 대시보드 **⚙ 연결**에 서버 주소와 APP_KEY 입력 → 아래 '내 일정' 구독 주소를 구글 캘린더에 추가
7. 전에 따로 구독한 학사·대회·LearnUs 캘린더는 겹치니까 구글 캘린더에서 삭제

## 로컬 실행

```bash
pip install -r requirements.txt
python -m pytest -q
python -m yc.build            # public/ 에 결과 생성
python -m http.server -d public 8000
```

## 개인 서버 로컬 실행

```bash
cd worker && npm install --no-save wrangler@4
printf 'APP_KEY="test"\nLEARNUS_URL="http://localhost:8765/learnus.ics"\n' > .dev.vars
npx wrangler dev --local --var PUBLIC_BASE:http://localhost:8765
node --test test/*.test.js
```

## 기준 바꾸기

`config/profile.yaml`만 고치면 된다. 커트라인 60점 이상은 캘린더, 35~59점은 대시보드 '검토' 탭에 들어간다. 세미나·모임은 점수와 관계없이 캘린더에 자동으로 넣지 않고, 별표를 누른 것만 넣는다.

## 다음 단계

- [x] 위비티·학교 공지 수집기
- [x] 링커리어 인턴 수집기 (원티드는 GitHub Actions 접속을 막아서 제외)
- [ ] 2027-1학기 학사일정, SQLD 2027 일정 공고 반영
- [x] 완료 체크, 내 일정 고르기, 추천 안 함, 월간 달력, 무악학사 일정
- [ ] 일요일 주간 체크인
