from unittest.mock import patch
from app.services.command_parser import parse_command
from app.services.employee_engagement_service import aggregate_comparison, calculate_engagement_score, submit_pulse_response

class Result:
    def __init__(self, data): self.data = data
class Query:
    def __init__(self, db, table): self.db, self.table_name, self.filters, self.payload = db, table, {}, None
    def select(self, *_): return self
    def eq(self, key, value): self.filters[key] = value; return self
    def limit(self, *_): return self
    def insert(self, payload): self.payload = payload; return self
    def execute(self):
        if self.payload is not None:
            self.db.inserts.setdefault(self.table_name, []).append(self.payload)
            return Result([{"id": "saved-id", **self.payload}])
        return Result([])
class FakeDB:
    def __init__(self): self.inserts = {}
    def table(self, name): return Query(self, name)

def test_anonymous_submission_separates_identity_from_response():
    db = FakeDB()
    with patch("app.services.employee_engagement_service.secrets.token_hex", return_value="a" * 64) as token:
        receipt = submit_pulse_response(db, survey={"id":"s1","scale_min":1,"scale_max":5,"is_anonymous":True,"channels":["PWA"]}, employee={"id":"e1","org_id":"o1","active_property_id":"p1","department_id":"d1"}, score=4, comment="Good support", source="PWA")
    assert db.inserts["employee_pulse_participation"][0]["employee_id"] == "e1"
    response = db.inserts["employee_pulse_responses"][0]
    assert response["employee_id"] is None
    assert response["response_fingerprint"] == "a" * 64
    token.assert_called_once_with(32)
    assert "response_fingerprint" not in receipt

def test_small_groups_are_suppressed():
    data = [{"property_id":"p1","score":5} for _ in range(4)] + [{"property_id":"p2","score":4} for _ in range(5)]
    result = {x["property_id"]: x for x in aggregate_comparison(data, "property_id", 5)}
    assert result["p1"]["suppressed"] is True and result["p1"]["average_score"] is None
    assert result["p2"]["suppressed"] is False and result["p2"]["average_score"] == 4

def test_engagement_score_is_rules_based_and_explainable():
    result = calculate_engagement_score({"pulse_average":4,"attendance_rate":90,"training_completion_rate":75,"approved_recognitions":2})
    assert result["model_type"] == "RULES_BASED" and 0 <= result["engagement_score"] <= 100
    assert {x["code"] for x in result["score_components"]} == {"PULSE","ATTENDANCE","LEARNING","RECOGNITION"}

def test_whatsapp_survey_english_and_hindi_aliases():
    english, hindi = parse_command("SURVEY 4 Helpful manager"), parse_command("सर्वे 5 अच्छा सहयोग")
    assert english.command == "SURVEY" and english.is_valid and english.parsed_args["score"] == 4
    assert hindi.command == "SURVEY" and hindi.is_valid and hindi.parsed_args["score"] == 5

def test_whatsapp_survey_rejects_invalid_score():
    parsed = parse_command("SURVEY 8")
    assert parsed.command == "SURVEY" and not parsed.is_valid
