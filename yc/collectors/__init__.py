from yc.collectors import devevent

# 이름 → 수집 함수. 새 소스는 여기에 추가한다.
COLLECTORS = {
    "dev-event": devevent.collect,
}
