SEASONALITY_MAP = {
    "HOTEL":      {1:0.7,2:0.7,3:0.8,4:0.9,5:1.0,6:1.3,7:1.4,8:1.4,9:1.1,10:0.9,11:0.8,12:1.2},
    "RESTAURANT": {1:0.8,2:0.8,3:0.9,4:1.0,5:1.0,6:1.1,7:1.1,8:1.1,9:1.0,10:0.9,11:0.9,12:1.3},
    "RESORT":     {1:0.5,2:0.5,3:0.7,4:0.9,5:1.1,6:1.4,7:1.5,8:1.5,9:1.1,10:0.8,11:0.6,12:1.0},
    "EVENTS_VENUE":{1:0.6,2:0.7,3:0.8,4:1.0,5:1.1,6:1.2,7:1.2,8:1.1,9:1.0,10:1.0,11:0.9,12:1.3},
    "CRUISE":     {1:0.8,2:0.9,3:1.0,4:1.0,5:1.1,6:1.2,7:1.3,8:1.3,9:1.1,10:1.0,11:0.9,12:1.0},
    "THEME_PARK": {1:0.5,2:0.5,3:0.8,4:1.1,5:1.2,6:1.5,7:1.6,8:1.5,9:1.0,10:0.9,11:0.7,12:1.1},
}

DEPT_BASE_HEADCOUNT = {
    "F&B": 20, "Housekeeping": 15, "Front Desk": 8, "Events": 10,
    "Kitchen": 12, "Security": 5, "Management": 3,
}

def generate_forecast(
    property_type: str,
    historical_data: list,
    occupancy_by_month: list,
    upcoming_events: list,
    departments: list,
    year: int,
) -> list:
    """Returns list of {month, department, predicted_headcount, confidence_score}"""
    seasonality = SEASONALITY_MAP.get(property_type, SEASONALITY_MAP["HOTEL"])
    occupancy_map = {o["month"]: o.get("occupancy_pct", 75) for o in occupancy_by_month}
    avg_occupancy = sum(occupancy_map.values()) / len(occupancy_map) if occupancy_map else 75

    results = []
    for month in range(1, 13):
        for dept in departments:
            hist = [h["hires"] for h in historical_data if h["month"] == month and h["department"] == dept]
            base = sum(hist) / len(hist) if hist else DEPT_BASE_HEADCOUNT.get(dept, 10)
            data_points = len(hist)

            occ_pct = occupancy_map.get(month, avg_occupancy)
            occ_multiplier = occ_pct / avg_occupancy if avg_occupancy else 1.0
            seasonal_factor = seasonality.get(month, 1.0)

            event_boost = 0
            for ev in upcoming_events:
                if ev.get("month") == month:
                    covers = ev.get("expected_covers", 0)
                    if dept == "F&B":
                        event_boost += (covers // 100) * 2
                    elif dept == "Events":
                        event_boost += (covers // 150) * 1

            predicted = max(1, round(base * occ_multiplier * seasonal_factor + event_boost))
            confidence = 0.85 if data_points > 12 else 0.65 if data_points > 6 else 0.40

            results.append({
                "month": month, "department": dept,
                "predicted_headcount": predicted,
                "confidence_score": confidence,
            })
    return results
