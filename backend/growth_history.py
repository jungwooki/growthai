"""Explicit dated height records; no inferred dates or clinical staging."""
import re
from datetime import date

def compute_history(text,birth,exam,current_height):
    if not text.strip():return None
    points={}
    for line in text.splitlines():
        if not line.strip():continue
        m=re.fullmatch(r'\s*(\d{4}-\d{2}-\d{2})\s*[:,：]?\s+(\d+(?:\.\d+)?)\s*(?:cm)?\s*',line,re.I)
        if not m:raise ValueError('성장기록은 한 줄에 2026-04-30 154.2 cm 형식으로 입력해주세요.')
        d=date.fromisoformat(m[1]);height=float(m[2])
        if not birth<=d<=exam or not 40<=height<=230:raise ValueError('성장기록의 날짜와 신장 범위를 확인해주세요.')
        if d in points and points[d]!=height:raise ValueError('같은 날짜에 서로 다른 신장이 있습니다.')
        points[d]=height
    if exam in points and points[exam]!=current_height:raise ValueError('성장기록의 검사일 신장과 현재 신장이 다릅니다.')
    points[exam]=current_height
    ordered=sorted(points.items());intervals=[]
    for (d1,h1),(d2,h2) in zip(ordered,ordered[1:]):
        days=(d2-d1).days
        intervals.append(dict(start=d1.isoformat(),end=d2.isoformat(),days=days,change=round(h2-h1,2),annualized=round((h2-h1)*365.2425/days,2)))
    first,h=ordered[0];days=(exam-first).days
    return dict(points=[dict(date=d.isoformat(),height=h) for d,h in ordered],intervals=intervals,overall=None if days==0 else dict(days=days,change=round(current_height-h,2),value=round((current_height-h)*365.2425/days,2),note='실제 입력 날짜 사이 신장 변화의 연환산 값. 단기간 변동·측정오차가 있으며 PHV를 이 값만으로 확정하지 않습니다.'))
