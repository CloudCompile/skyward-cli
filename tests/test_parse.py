"""Parser tests against synthetic pages shaped like the real portal."""
from datetime import date


from fixtures import pages
from skyward import parse


def test_student():
    s = parse.parse_student(pages.gradebook())
    assert s.name == "Student"
    assert s.school == "Example High School"
    assert s.student_id == pages.STUDENT_ID


def test_classes_have_teacher_period_time():
    classes = parse.parse_gradebook(pages.gradebook())
    assert [c.name for c in classes] == ["Algebra I", "Biology", "English 10"]
    a = classes[0]
    assert (a.period, a.time, a.teacher) == ("1", "8:00 AM - 8:50 AM", "Ms. Addams")
    assert a.section == "01"


def test_term_grades_and_current():
    algebra, bio, english = parse.parse_gradebook(pages.gradebook())
    assert algebra.grades == {"Q1": "A", "Q2": "", "S1": "A"}
    assert algebra.current == "A"
    assert bio.current == "B", "S1 beats Q2 when both posted"
    assert english.current == "A"


def test_assignments_with_due_and_term():
    algebra = parse.parse_gradebook(pages.gradebook())[0]
    names = [a.name for a in algebra.assignments]
    assert names == ["Quiz 1", "Quiz 2", "Homework Set 3"]
    hw = algebra.assignments[-1]
    assert hw.due == "11/12/2026"
    assert hw.term == "Q2"
    assert hw.grade == ""            # not graded yet
    assert algebra.assignments[0].terms == {"Q1": "A"}
    assert algebra.assignments[0].grade == "A"


def test_period_times():
    assert parse.period_times(pages.gradebook()) == {
        "1": "8:00 AM - 8:50 AM",
        "2": "9:00 AM - 9:50 AM",
        "3": "10:00 AM - 10:50 AM",
    }


def test_schedule_cells():
    sch = parse.parse_schedule(pages.schedule())
    first = [c for c in sch if c.period == "1"]
    assert {c.term for c in first} == {"1", "2"}
    assert first[0].name == "Algebra I"
    assert first[0].teacher == "Ms. Addams"
    assert first[0].room == "101"
    assert first[0].days == "M,T,W,R,F"
    assert first[0].school == "Example High School"
    # empty slots are skipped entirely
    assert not [c for c in sch if c.period == "5"]
    lunch = [c for c in sch if c.name == "Lunch"][0]
    assert lunch.teacher == "" and lunch.room == "Cafeteria"


def test_current_term_from_date_ranges():
    page = pages.schedule()
    assert parse.current_term(page, date(2026, 9, 15)) == "1"
    assert parse.current_term(page, date(2026, 12, 1)) == "2"
    assert parse.current_term(page, date(2027, 5, 1)) == ""


def test_attendance():
    entries = parse.parse_attendance(pages.attendance())
    assert [e.reason for e in entries] == ["Excused (Doctor Visit)", "Unexcused"]
    assert entries[1].period == "3" and entries[1].cls == "English 10"
    assert "No Absences or Tardies" in parse.parse_attendance_today(pages.attendance())


def test_gpa_dialog():
    g = parse.parse_gpa(pages.gpa_dialog())
    assert g.school_year == "2026-2027"
    assert g.unweighted == 3.75
    assert g.weighted is None
    assert g.rank == "42 of 310"
    assert g.rows[0].credits == 12.5
    assert len(g.rows) == 1, "year divider rows are not GPA rows"


def test_gpa_text_fallback():
    g = parse.parse_gpa("<div>Normal 3.50000 2.000 0.000 9 of 100</div>")
    assert g.unweighted == 3.5 and g.rank == "9 of 100"


def test_parse_empty_page_is_safe():
    assert parse.parse_gradebook("<html></html>") == []
    assert parse.parse_schedule("") == []
    assert parse.parse_attendance("") == []
    assert parse.parse_student("<!doctype html><title>Family Access</title>").name == ""
