from yc.collectors import devevent, dorm, linkareer, wevity, yonsei

# 이름 → 수집 함수. 새 소스는 여기에 추가한다. (이름은 Event.source와 같아야 한다)
COLLECTORS = {
    "dev-event": devevent.collect,
    "wevity": wevity.collect,
    "yonsei-notice": yonsei.collect,
    "linkareer": linkareer.collect,
    "dorm": dorm.collect,
}
