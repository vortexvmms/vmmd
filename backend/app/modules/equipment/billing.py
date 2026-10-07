"""Tipper-specific billing; independent from worker attendance and payroll."""
from decimal import Decimal, ROUND_HALF_UP
from fastapi import HTTPException


def calculate_billing(data: dict) -> dict:
    mode = data.get("billing_mode", "legacy")
    if mode == "legacy":
        return data
    result = dict(data)
    if mode == "trip":
        count = Decimal(str(data.get("quantity", 0)))
        if count <= 0 or count != count.to_integral_value():
            raise HTTPException(422, "Enter a whole number of trips greater than zero")
        result.update(start_time=None, end_time=None, normal_hours=None, ot_hours=None,
                      total_hours=None, break_minutes=0, unit_type="trip")
        return result
    start, end = data.get("start_time"), data.get("end_time")
    if not start or not end:
        raise HTTPException(422, "Start and end time are required for Day/Night Work")
    def minutes(value):
        parts = str(value).split(":")
        try:
            h, m = int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            raise HTTPException(422, "Enter valid start and end times")
        if not 0 <= h <= 23 or not 0 <= m <= 59:
            raise HTTPException(422, "Enter valid start and end times")
        return h * 60 + m
    elapsed = (minutes(end) - minutes(start)) % 1440
    deduction = int(data.get("break_minutes", 60 if mode == "day" else 0))
    if elapsed == 0 or elapsed <= deduction:
        raise HTTPException(422, "Work duration must be greater than the break deduction")
    total = Decimal(elapsed - deduction) / Decimal(60)
    normal, ot = min(total, Decimal(10)), max(total - Decimal(10), Decimal(0))
    if ot > 0 and data.get("ot_rate") is None:
        raise HTTPException(422, "Enter the separate OT hourly rate")
    result.update(total_hours=float(total.quantize(Decimal(".0001"))),
                  normal_hours=float(normal.quantize(Decimal(".0001"))),
                  ot_hours=float(ot.quantize(Decimal(".0001"))),
                  quantity=1, unit_type="hour", break_minutes=deduction)
    return result


def billing_amount(data: dict) -> Decimal:
    d = calculate_billing(data)
    rate = Decimal(str(d.get("transport_rate", 0)))
    if d.get("billing_mode") in ("day", "night"):
        amount = Decimal(str(d["normal_hours"])) * rate + Decimal(str(d["ot_hours"])) * Decimal(str(d.get("ot_rate") or 0))
    else:
        amount = Decimal(str(d.get("quantity", 0))) * rate
    return amount.quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
