"""Parsers for Skyward Family/Student Access pages.

Skyward serves a fixed set of pages, each of which is plain HTML plus a
`sf_gridObjects` JSON blob describing the main data grid. The pages we use:

    sfgradebook001.w     classes, term grades, every assignment
    sfschedule001.w      per-term schedule matrix (period x term)
    sfattendance001.w    attendance history
    sfhome01.w           student name / school, upcoming events

Everything here is pure functions over HTML strings so it can be tested
against saved fixtures without a network.
"""

from __future__ import annotations

import html as _html
import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterator

# ── generic HTML helpers ─────────────────────────────────────────────────

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def text(fragment: str) -> str:
    """Tags out, entities decoded, whitespace collapsed."""
    plain = _html.unescape(_TAG_RE.sub(" ", fragment.replace("\\/", "/")))
    return _WS_RE.sub(" ", plain.replace("\xa0", " ")).strip()


def _table_rows(markup: str) -> list[str]:
    return re.findall(r"<tr\b[^>]*>(.*?)</tr\s*>", markup, re.S | re.I)


def _cells(row: str) -> list[str]:
    return re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row, re.S | re.I)


def find_table(markup: str, table_id: str) -> str | None:
    """Inner HTML of <table id="table_id">, or None."""
    m = re.search(r"""<table\b[^>]*\bid\s*=\s*(?:"%s"|'%s')[^>]*>(.*?)</table>""" % (
        re.escape(table_id), re.escape(table_id)), markup, re.S | re.I)
    return m.group(1) if m else None


def cell_text(cell: dict[str, Any] | str) -> str:
    """Text of a gridObjects cell; grid rows may point at another row by cId."""
    if isinstance(cell, dict):
        return text(cell.get("h", ""))
    return text(str(cell))


def tables(markup: str) -> Iterator[tuple[str, str]]:
    """Yield (id, body) for every identified table."""
    for m in re.finditer(r"<table\b([^>]*)>(.*?)</table>", markup, re.S | re.I):
        i = re.search(r"""\bid\s*=\s*(?:"([^"]*)"|'([^']*)')""", m.group(1))
        if i:
            yield (i.group(1) or i.group(2) or ""), m.group(2)


def grid_object(markup: str, name_prefix: str) -> dict[str, Any] | None:
    """Pull one grid out of `sff.sv('sf_gridObjects', $.extend(..., {...}))`.

    Skyward hands the whole gradebook grid to the browser as JSON; we read it
    straight out instead of re-parsing thousands of <td> tags.
    """
    i = markup.find("sff.sv('sf_gridObjects'")
    if i < 0:
        return None
    # find `<name>_...": {` anywhere in the object map, whatever its key order
    # and whether the key was written with double or single quotes
    m = re.search(r"""['"]%s[^'"]*['"]\s*:\s*\{""" % re.escape(name_prefix), markup[i:])
    if not m:
        return None
    j = i + m.end() - 1
    try:
        grid, _ = json.JSONDecoder().raw_decode(markup[j:])
    except json.JSONDecodeError:
        return None
    return grid


# ── student identity ─────────────────────────────────────────────────────

@dataclass
class Student:
    name: str = ""
    school: str = ""
    student_id: str = ""
    entity_id: str = ""

    def __bool__(self) -> bool:
        return bool(self.name or self.student_id)


def parse_student(gradebook_html: str) -> Student:
    s = Student()
    for key in ("studentId", "entity"):
        m = re.search(r"sff\.sv\('%s', '([^']*)'" % key, gradebook_html)
        if m:
            if key == "studentId":
                s.student_id = m.group(1)
            else:
                s.entity_id = m.group(1)
    m = re.search(r"sff\.sv\('stuGradeGrids', '(\d+)_(\d+)'", gradebook_html)
    if m:
        s.student_id = s.student_id or m.group(1)
        s.entity_id = s.entity_id or m.group(2)
    m = re.search(r"sf_gridObjects.*?\"id\":\"stuGradesGrid_(\d+)_(\d+)\"", gradebook_html)
    if m:  # header shows "Student Name (Sample High School)"
        s.student_id = s.student_id or m.group(1)
        s.entity_id = s.entity_id or m.group(2)
    m = re.search(r"""<div class="sfTag"><span[^>]*>([^<]+)</span>\s*\(([^)]+)\)""", gradebook_html)
    if m:
        s.name, s.school = text(m.group(1)), text(m.group(2))
    if not s.name:
        m = re.search(r"\b([A-Z][a-z]+(?: [A-Z]\.)? [A-Z][a-z]+)\s{2,}", gradebook_html)
        if m:
            s.name = m.group(1)
    return s


# ── gradebook ────────────────────────────────────────────────────────────

@dataclass
class ClassInfo:
    name: str
    period: str = ""
    time: str = ""
    teacher: str = ""
    cor_num_id: str = ""
    section: str = ""
    grades: dict[str, str] = field(default_factory=dict)   # term -> grade
    assignments: list["Assignment"] = field(default_factory=list)

    @property
    def current(self) -> str:
        """Best "right now" grade: last non-empty term, preferring S1/S2."""
        for term in ("S2", "S1", "S2E", "S1E"):
            if self.grades.get(term):
                return self.grades[term]
        vals = [v for v in self.grades.values() if v]
        return vals[-1] if vals else ""


@dataclass
class Assignment:
    name: str
    grade: str
    terms: dict[str, str] = field(default_factory=dict)    # term -> grade
    due: str = ""
    term: str = ""                                          # term as shown "(Q1)"
    cls: str = ""
    period: str = ""


_CLASS_TABLE_RE = re.compile(r"""<table\b[^>]*\bid=['"]classDesc_[^'"]*['"][^>]*>(.*?)</table>""", re.S | re.I)
_GRADE_LINK_RE = re.compile(r"data-cNI='([^']*)'.*?data-sec='([^']*)'.*?data-bkt='([^']*)'.*?data-lit='([^']*)'", re.S)


def parse_gradebook(markup: str) -> list[ClassInfo]:
    """Classes (with teacher/period/time) joined to the term/assignment grid."""
    classes: dict[str, ClassInfo] = {}
    for cm in _CLASS_TABLE_RE.finditer(markup):
        body = cm.group(1)
        rows = _table_rows(body)
        name = ""
        period = time_ = teacher = ""
        for idx, row in enumerate(rows):
            cells = _cells(row)
            plain = text(" ".join(cells))
            if idx == 0:
                nm = re.search(r"classDesc[^>]*>\s*<a\b[^>]*>(.*?)</a>", row, re.S)
                name = text(nm.group(1)) if nm else plain
                continue
            pm = re.search(r"Period\s*([0-9A-Za-z]+)?\s*(?:\(([^)]*)\))?", plain)
            if pm:
                period, time_ = pm.group(1) or "", pm.group(2) or ""
            elif plain and not teacher:
                teacher = plain
        if not name:
            continue
        cor = re.search(r"id=['\"]exp_(\d+)_([^_]+)_", body)
        c = ClassInfo(name=name, period=period, time=time_, teacher=teacher,
                      cor_num_id=cor.group(1) if cor else "",
                      section=cor.group(2) if cor else "")
        classes[c.cor_num_id or name] = c

    grid = grid_object(markup, "stuGradesGrid_")
    if not grid:
        return list(classes.values())

    header = [text(c["h"]) for c in grid["th"]["r"][0]["c"]] if grid.get("th", {}).get("r") else []
    terms = header[1:]

    # gridObjects rows reference other rows by cId; resolve and join on them.
    rows_by_id = {r["h"]: r for r in grid["tb"]["r"] if isinstance(r, dict) and "h" in r}
    for row in grid["tb"]["r"]:
        if isinstance(row, dict):
            row["c"] = [rows_by_id.get(c, c) if isinstance(c, str) else c for c in row.get("c", [])]

    by_cor: dict[str, ClassInfo] = {c.cor_num_id: c for c in classes.values() if c.cor_num_id}
    # order classes by appearance in the grid, falling back to page order
    order: list[str] = []
    current: ClassInfo | None = None
    for row in grid["tb"]["r"]:
        if not isinstance(row, dict):
            continue
        row_html = row.get("h", "")
        cells = row.get("c", [])
        is_class_row = "group-parent=" in row_html
        is_assignment = "group-child=" in row_html
        if is_class_row:
            m = re.search(r'group-[a-z]+="[^"]*?_(\d+)_', row_html)
            cor = m.group(1) if m else ""
            current = by_cor.get(cor)
            if current and current.cor_num_id not in order:
                order.append(current.cor_num_id)
            if current:
                for lit, cell in zip(terms, cells[1:]):
                    h = cell.get("h", "") if isinstance(cell, dict) else ""
                    if "emptyGrade" in h:
                        val = ""
                    elif "<a" in h:
                        am2 = re.search(r"<a\b[^>]*>(.*?)</a>", h, re.S)
                        val = text(am2.group(1)) if am2 else ""
                    else:
                        val = text(h)
                    if lit:
                        current.grades[lit] = val
            continue
        if current is None or not is_assignment:
            continue
        label = cell_text(cells[0]) if cells else ""
        # an ungraded assignment's cells are blank; its label still holds
        # "Name Due: 11/12/2026 (Q2)" (nbsp between date and term)
        if cells and isinstance(cells[0], dict):
            label = text(cells[0].get("h", "")) or label
        if not label:
            continue
        am = re.search(r"(Due:\s*[\d/]+)\s*\((\w+)\)", label)
        due = am.group(1).replace("Due:", "").strip() if am else ""
        aname = re.sub(r"\s*Due:.*$", "", label).strip()
        a_terms = {}
        for lit, cell in zip(terms, cells[1:]):
            v = cell_text(cell)
            if v:
                a_terms[lit] = v
        a_grade = next(iter(a_terms.values()), "")
        current.assignments.append(Assignment(
            name=aname, grade=a_grade, terms=a_terms, due=due,
            term=am.group(2) if am else "", cls=current.name, period=current.period,
        ))
    ordered = [by_cor[k] for k in order if k in by_cor]
    seen = {c.cor_num_id for c in ordered}
    ordered += [c for c in classes.values() if c.cor_num_id not in seen]
    return ordered


# ── GPA ──────────────────────────────────────────────────────────────────

@dataclass
class GPARow:
    kind: str = ""            # e.g. "Normal", "Weighted"
    gpa: float | None = None
    credits: float | None = None
    failed_credits: float | None = None
    rank: str = ""
    rank_of: str = ""
    rank_date: str = ""
    school_year: str = ""


@dataclass
class GPA:
    rows: list[GPARow] = field(default_factory=list)
    school_year: str = ""

    @property
    def unweighted(self) -> float | None:
        for r in self.rows:
            if r.kind.lower().startswith("normal") or not r.kind:
                return r.gpa
        return None

    @property
    def weighted(self) -> float | None:
        for r in self.rows:
            if "weight" in r.kind.lower():
                return r.gpa
        return None

    @property
    def rank(self) -> str:
        for r in self.rows:
            if r.rank:
                return f"{r.rank} of {r.rank_of}".strip()
        return ""


def _num(s: str) -> float | None:
    try:
        return float(s.replace(",", ""))
    except (TypeError, ValueError):
        return None


def _make_col(idx: dict[str, int]):
    """Column lookup by fuzzy header name; closes over idx safely."""
    def col(cells: list[str], *names: str) -> str:
        for n in names:
            for h, pos in idx.items():
                if n in h and pos < len(cells):
                    return cells[pos]
        return ""
    return col


def parse_gpa(html_fragment: str) -> GPA:
    """GPA / class rank dialog table.

    Rows look like: Normal | 3.00000 | 1.000 | 0.000 | 161 of 468 | 09/30/2026
    """
    g = GPA()
    m = re.search(r"(\d{4})\s*-\s*(\d{4}) School Year", text(html_fragment))
    if m:
        g.school_year = f"{m.group(1)}-{m.group(2)}"
    for _, body in tables(html_fragment):
        rows = _table_rows(body)
        if not rows:
            continue
        header = [c.lower() for c in (text(c) for c in _cells(rows[0]))]
        if not any("gpa" in h for h in header):
            continue
        idx = {name: i for i, name in enumerate(header)}

        col = _make_col(idx)

        for row in rows[1:]:
            cells = [text(c) for c in _cells(row)]
            if not any(cells) or re.match(r"\d{4}\s*-\s*\d{4} School Year", cells[0]):
                continue                      # blank or year-section divider row
            rank = col(cells, "rank")
            rank_of = ""
            rm = re.match(r"(\S+)\s+of\s+(\S+)", rank)
            if rm:
                rank, rank_of = rm.group(1), rm.group(2)
            g.rows.append(GPARow(
                kind=col(cells, "gpa type", "type") or cells[0],
                gpa=_num(col(cells, "cumulative gpa", "gpa")),
                credits=_num(col(cells, "earned")),
                failed_credits=_num(col(cells, "failed")),
                rank=rank, rank_of=rank_of,
                rank_date=col(cells, "rank date", "date"),
            ))
    # fall back to a single line of text when the table shape changes
    if not g.rows:
        t = text(html_fragment)
        m = re.search(r"(Normal|Weighted)\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+(\d+)\s+of\s+(\d+)", t)
        if m:
            g.rows.append(GPARow(kind=m.group(1), gpa=_num(m.group(2)), credits=_num(m.group(3)),
                                 failed_credits=_num(m.group(4)), rank=m.group(5), rank_of=m.group(6)))
    return g


# ── schedule ─────────────────────────────────────────────────────────────

@dataclass
class ScheduledClass:
    period: str
    term: str
    name: str
    teacher: str = ""
    room: str = ""
    school: str = ""
    days: str = ""


_PERIOD_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*([AP]M)\s*-\s*(\d{1,2}):(\d{2})\s*([AP]M)", re.I)


def period_times(gradebook_html: str) -> dict[str, str]:
    """period -> '8:50 AM - 9:35 AM' from the gradebook's period labels.

    Markup: <label ...>Period</label>1<span ...>(8:50 AM - 9:35 AM)</span>
    """
    out: dict[str, str] = {}
    rx = re.compile(r">\s*Period\s*</label>\s*(\d+)\s*<span[^>]*>\(?\s*"
                    r"(\d{1,2}:\d{2}\s*[AP]M\s*-\s*\d{1,2}:\d{2}\s*[AP]M)", re.S | re.I)
    for m in rx.finditer(gradebook_html):
        out.setdefault(m.group(1), _WS_RE.sub(" ", m.group(2)))
    return out


_SCHED_CELL_RE = re.compile(r"grid_MATRIXStudentClasses_\d+_\d+_(\d+)_(\d+)$")


def parse_schedule(markup: str) -> list[ScheduledClass]:
    """Schedule matrix cell for each (period, term).

    One cell looks like (tags stripped, breaks kept):
      Class | Teacher | Days M,T,W,R,F    Room Gym | Sample High School
    """
    out: list[ScheduledClass] = []
    for tid, body in tables(markup):
        m = _SCHED_CELL_RE.match(tid)
        if not m:
            continue
        anchors = [text(a) for a in re.findall(r"<a\b[^>]*>(.*?)</a>", body, re.S)]
        if not anchors or not anchors[0]:
            continue                      # empty slot
        plain = re.sub(r"&nbsp;+", " | ", body)
        plain = re.sub(r"<br\s*/?>", " | ", plain)
        parts = [p for p in (text(x) for x in plain.split("|")) if p]
        days = room = school = ""
        for part in parts:
            if part.lower().startswith("days "):
                days = re.sub(r"\s*Room\s+.*$", "", part[5:], flags=re.I).strip()
                rm = re.search(r"Room\s+(\S.*)$", part, re.I)
                if rm:
                    room = rm.group(1).strip()
            elif part.lower().startswith("room "):
                room = part[5:].strip()
            elif part.endswith("School") and not part.startswith("Room"):
                school = part
        out.append(ScheduledClass(period=m.group(1), term=m.group(2),
                                  name=anchors[0],
                                  teacher=anchors[1] if len(anchors) > 1 else "",
                                  room=room, days=days, school=school))
    out.sort(key=lambda c: (int(c.period) if c.period.isdigit() else 99, int(c.term)))
    return out


def current_term(markup: str, today: date | None = None) -> str:
    """Which term column is "now", from the schedule page's term date ranges.

    The page prints each term as 'Term 2 (11/04/26 - 01/14/27)'.
    """
    today = today or date.today()
    rx = (r"""grid_(\d+)_DAYS["']?[^>]*>.*?(\d{2})/(\d{2})/(\d{2})\s*[-\u2013]\s*"""
          r"""(\d{2})/(\d{2})/(\d{2})""")
    for m in re.finditer(rx, markup, re.S):
        start = date(2000 + int(m.group(4)), int(m.group(2)), int(m.group(3)))
        end = date(2000 + int(m.group(7)), int(m.group(5)), int(m.group(6)))
        if start <= today <= end:
            return m.group(1)
    return ""


# ── attendance ───────────────────────────────────────────────────────────

@dataclass
class AttendanceEntry:
    date: str
    reason: str
    period: str = ""
    cls: str = ""


def parse_attendance(markup: str) -> list[AttendanceEntry]:
    out = []
    for tid, body in tables(markup):
        if not tid.startswith("grid_attendanceHistory"):
            continue
        rows = _table_rows(body)
        for row in rows[1:]:
            cells = [text(c) for c in _cells(row)]
            if not cells or not cells[0]:
                continue
            out.append(AttendanceEntry(
                date=cells[0],
                reason=cells[1] if len(cells) > 1 else "",
                period=cells[2] if len(cells) > 2 else "",
                cls=cells[3] if len(cells) > 3 else "",
            ))
    return out


def parse_attendance_today(markup: str) -> str:
    body = find_table(markup, "grid_todaysattendance")
    if not body:
        return ""
    return " ".join(text(r) for r in _table_rows(body))


# ── events / misc ────────────────────────────────────────────────────────

@dataclass
class Event:
    title: str
    when: str = ""
    kind: str = ""


def parse_events(markup: str) -> list[Event]:
    """Upcoming events from the home page's event module (best effort)."""
    out: list[Event] = []
    for m in re.finditer(r"class=['\"][^'\"]*sf_evtTitle[^'\"]*['\"][^>]*>(.*?)</", markup, re.S):
        t = text(m.group(1))
        if t:
            out.append(Event(title=t))
    return out
