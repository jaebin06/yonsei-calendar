# 연세 통합 일정 캘린더

학사일정·대회·자격증 시험·인턴 공고를 자동으로 모으고, 내 기준으로 걸러서 **구글 캘린더 구독 주소(ICS)**로 내보내는 개인용 시스템. 갤럭시 삼성 캘린더에는 구글 계정 동기화로 자동 표시된다.

- 서버 없음: GitHub Actions가 매일 06:00(KST)에 돌고, 결과를 GitHub Pages에 올린다.
- 과제는 크롤링하지 않는다: LearnUs 캘린더의 내보내기 주소를 구글 캘린더가 직접 구독한다. 그 주소에는 로그인 토큰이 들어 있어서 **이 저장소에 절대 넣지 않는다.**

## 구조

```
yc/collectors/   소스별 수집기 (현재 dev-event)
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
2. **Actions** 탭 → `daily-build` → **Run workflow**
3. 몇 분 뒤 `https://jaebin06.github.io/yonsei-calendar/` 에서 대시보드 확인
4. 대시보드 아래 **구독 주소**를 PC의 calendar.google.com → 다른 캘린더 + → URL로 추가
5. LearnUs 캘린더 내보내기 주소도 같은 방법으로 따로 추가

## 로컬 실행

```bash
pip install -r requirements.txt
python -m pytest -q
python -m yc.build            # public/ 에 결과 생성
python -m http.server -d public 8000
```

## 기준 바꾸기

`config/profile.yaml`만 고치면 된다. 커트라인 60점 이상은 캘린더, 35~59점은 대시보드 '검토' 탭에 들어간다. 세미나·모임은 점수와 관계없이 캘린더에 자동으로 넣지 않고, 별표를 누른 것만 넣는다.

## 다음 단계

- [ ] 위비티·학교 공지 수집기
- [ ] 링커리어·원티드 인턴 수집기
- [ ] 2027-1학기 학사일정, SQLD 2027 일정 공고 반영
- [ ] 일요일 주간 체크인 (구글 캘린더 연결)
