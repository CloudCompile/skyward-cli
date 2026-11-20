"""CLI tests: run each command end-to-end against the fake portal."""
import json

import pytest
from typer.testing import CliRunner

from fake_skyward import PASSWORD, USER, FakeSkyward
from skyward.cli import app

runner = CliRunner()


@pytest.fixture
def fake():
    with FakeSkyward() as f:
        yield f


def run(fake, *args):
    return runner.invoke(app, list(args) + ["--base", fake.base, "-u", USER, "-p", PASSWORD])


def test_grades_table(fake):
    r = run(fake, "grades")
    assert r.exit_code == 0, r.output
    out = r.output
    for text in ("Algebra I", "Biology", "English 10", "Ms. Addams", "Student"):
        assert text in out
    assert "grades" in out


def test_grades_json(fake):
    r = run(fake, "grades", "--json")
    assert r.exit_code == 0, r.output
    data = json.loads(r.stdout)
    assert data["student"]["name"] == "Student"
    assert [c["name"] for c in data["classes"]] == ["Algebra I", "Biology", "English 10"]
    assert data["gpa"] is None


def test_grades_json_with_gpa(fake):
    r = run(fake, "grades", "--json", "--gpa")
    data = json.loads(r.stdout)
    assert data["gpa"]["rows"][0]["gpa"] == 3.75
    assert "gpa" in fake.pages_served


def test_grades_gpa_line(fake):
    r = run(fake, "grades", "--gpa")
    assert r.exit_code == 0
    assert "GPA" in r.output and "3.75" in r.output and "42 of 310" in r.output


def test_bad_password_exits_2(fake):
    r = runner.invoke(app, ["grades", "--base", fake.base, "-u", USER, "-p", "wrong"])
    assert r.exit_code == 2
    assert "login failed" in r.output


def test_assignments_all(fake):
    r = run(fake, "assignments")
    assert r.exit_code == 0, r.output
    assert "Quiz 1" in r.output and "Book Talk" in r.output


def test_assignments_course_filter_and_limit(fake):
    r = run(fake, "assignments", "--course", "biology", "-n", "1")
    assert "Biology" in r.output
    assert "Algebra I" not in r.output
    rows = [ln for ln in r.output.splitlines() if "2026" in ln]
    assert len(rows) == 1


def test_assignments_missing_only(fake):
    r = run(fake, "assignments", "--missing", "--json")
    data = json.loads(r.stdout)
    listed = {a["name"] for c in data["courses"] for a in c["assignments"]}
    assert listed == {"Homework Set 3", "Book Talk"}


def test_schedule(fake):
    r = run(fake, "schedule", "--day", "2026-12-01")
    assert r.exit_code == 0, r.output
    assert "term 2" in r.output
    assert "Algebra I" in r.output and "8:00 AM - 8:50 AM" in r.output
    assert "Cafeteria" in r.output


def test_schedule_bad_day(fake):
    r = run(fake, "schedule", "--day", "tomorrow")
    assert r.exit_code == 1
    assert "YYYY-MM-DD" in r.output


def test_schedule_json(fake):
    r = run(fake, "schedule", "--day", "2026-12-01", "--json")
    data = json.loads(r.stdout)
    assert data["term"] == "2"
    assert data["times"]["3"] == "10:00 AM - 10:50 AM"


def test_attendance(fake):
    r = run(fake, "attendance")
    assert r.exit_code == 0, r.output
    assert "Excused (Doctor Visit)" in r.output
    assert "Unexcused" in r.output
    assert "Today's Attendance" in r.output


def test_attendance_json(fake):
    r = run(fake, "attendance", "--json")
    data = json.loads(r.stdout)
    assert len(data["entries"]) == 2
    assert data["entries"][0]["date"] == "Thu Nov 12, 2026"


def test_help_lists_commands():
    r = runner.invoke(app, ["--help"])
    assert r.exit_code == 0
    for cmd in ("grades", "assignments", "schedule", "attendance"):
        assert cmd in r.output
