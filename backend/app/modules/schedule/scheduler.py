from __future__ import annotations
from datetime import date, timedelta


def _rules(calendar, workweeks, exceptions):
    cid = calendar.get("id") if calendar else None
    week = {int(r["day_of_week"]): bool(r["is_working"]) for r in workweeks if r["calendar_id"] == cid}
    special = {date.fromisoformat(x["exception_date"]): bool(x["is_working"]) for x in exceptions if x["calendar_id"] == cid}
    return week or {0: False, 1: True, 2: True, 3: True, 4: True, 5: True, 6: False}, special


def _working(day, week, special):
    return special.get(day, week.get((day.weekday() + 1) % 7, False))


def shift(day, working_days, week, special):
    if working_days == 0:
        while not _working(day, week, special): day += timedelta(days=1)
        return day
    step = 1 if working_days > 0 else -1
    remaining = abs(working_days)
    while remaining:
        day += timedelta(days=step)
        if _working(day, week, special): remaining -= 1
    return day


def span(start, duration, week, special):
    return start if duration == 0 else shift(start, duration - 1, week, special)


def distance(start, finish, week, special):
    if finish <= start: return 0
    count, day = 0, start
    while day < finish:
        day += timedelta(days=1)
        if _working(day, week, special): count += 1
    return count


def calculate_schedule(activities, relationships, calendars, workweeks, exceptions):
    items = {a["id"]: dict(a) for a in activities}
    incoming = {key: [] for key in items}; outgoing = {key: [] for key in items}
    indegree = {key: 0 for key in items}
    for rel in relationships:
        if rel["predecessor_id"] in items and rel["successor_id"] in items:
            incoming[rel["successor_id"]].append(rel); outgoing[rel["predecessor_id"]].append(rel); indegree[rel["successor_id"]] += 1
    queue = [key for key, degree in indegree.items() if degree == 0]; order = []
    while queue:
        key = queue.pop(0); order.append(key)
        for rel in outgoing[key]:
            indegree[rel["successor_id"]] -= 1
            if indegree[rel["successor_id"]] == 0: queue.append(rel["successor_id"])
    if len(order) != len(items): raise ValueError("Activity logic contains a cycle")
    calendar_map = {c["id"]: c for c in calendars}; result = {}
    for key in order:
        activity = items[key]; week, special = _rules(calendar_map.get(activity.get("calendar_id")), workweeks, exceptions)
        start = shift(date.fromisoformat(activity["planned_start"]), 0, week, special); duration = int(activity["duration_days"])
        for rel in incoming[key]:
            pred = result[rel["predecessor_id"]]; lag = int(rel["lag_days"]); kind = rel["relationship_type"]
            if kind == "FS": candidate = shift(pred["early_finish"], lag + 1, week, special)
            elif kind == "SS": candidate = shift(pred["early_start"], lag, week, special)
            else:
                required_finish = shift(pred["early_finish"] if kind == "FF" else pred["early_start"], lag, week, special)
                candidate = shift(required_finish, -(max(duration, 1) - 1), week, special)
            start = max(start, candidate)
        result[key] = {"early_start": start, "early_finish": span(start, duration, week, special), "week": week, "special": special, "duration": duration}
    project_finish = max((x["early_finish"] for x in result.values()), default=date.today())
    for key in reversed(order):
        row = result[key]; week, special, duration = row["week"], row["special"], row["duration"]
        late_finish = project_finish
        if outgoing[key]:
            candidates=[]
            for rel in outgoing[key]:
                succ=result[rel["successor_id"]]; lag=int(rel["lag_days"]); kind=rel["relationship_type"]
                if kind=="FS": candidates.append(shift(succ["late_start"],-(lag+1),week,special))
                elif kind=="FF": candidates.append(shift(succ["late_finish"],-lag,week,special))
                else:
                    latest_start=shift(succ["late_start"] if kind=="SS" else succ["late_finish"],-lag,week,special)
                    candidates.append(span(latest_start,duration,week,special))
            late_finish=min(candidates)
        late_start=shift(late_finish,-(max(duration,1)-1),week,special); total_float=distance(row["early_start"],late_start,week,special)
        row.update(late_start=late_start,late_finish=late_finish,total_float=total_float,is_critical=total_float==0)
    return {key:{k:(v.isoformat() if isinstance(v,date) else v) for k,v in row.items() if k not in("week","special","duration")} for key,row in result.items()}
