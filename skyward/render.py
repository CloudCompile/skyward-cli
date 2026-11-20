"""Rich renderers for skyward output.

Grade colors: A green, B blue, C yellow, D orange, F red, proficiency
codes (1-4) get a neutral color. Pending/blank grades are dim dashes.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .parse import Assignment, AttendanceEntry, ClassInfo, GPA, ScheduledClass, Student

GRADE_STYLE = {
    "A": "bold green", "B": "bold cyan", "C": "bold yellow",
    "D": "bold dark_orange", "F": "bold red",
    "1": "dim", "2": "white", "3": "cyan", "4": "green",
}

console = Console()
err_console = Console(stderr=True)


def grade_text(grade: str, *, dim_empty: bool = True) -> Text:
    if not grade:
        return Text("–", style="dim") if dim_empty else Text("")
    key = grade.strip()[:1].upper()
    return Text(grade, style=GRADE_STYLE.get(key, "bold"))


def header(student: Student, extra: str = "") -> Text:
    t = Text()
    if student.name:
        t.append(student.name, style="bold")
    if student.school:
        t.append(f"  ·  {student.school}", style="dim")
    if extra:
        t.append(f"  ·  {extra}", style="dim")
    return t


# ── grades ───────────────────────────────────────────────────────────────

def courses_table(classes: list[ClassInfo], terms: list[str] | None = None) -> Table:
    terms = terms or _terms(classes)
    t = Table(box=None, pad_edge=False, header_style="dim", expand=False)
    t.add_column("#", justify="right", style="dim")
    t.add_column("Course")
    t.add_column("Teacher", style="dim")
    for term in terms:
        t.add_column(term, justify="center")
    for c in classes:
        row: list[Any] = [c.period or "", c.name, c.teacher or ""]
        for term in terms:
            row.append(grade_text(c.grades.get(term, "")))
        t.add_row(*row)
    return t


def _terms(classes: list[ClassInfo]) -> list[str]:
    seen: list[str] = []
    for c in classes:
        for k in c.grades:
            if k not in seen:
                seen.append(k)
    return seen


def gpa_line(gpa: GPA) -> Text:
    t = Text()
    if gpa.unweighted is not None:
        t.append("GPA ", style="dim")
        t.append(f"{gpa.unweighted:.2f}", style="bold")
    if gpa.weighted is not None:
        t.append("  ·  weighted ", style="dim")
        t.append(f"{gpa.weighted:.2f}", style="bold")
    if gpa.rank:
        t.append("  ·  rank ", style="dim")
        t.append(gpa.rank, style="bold")
    return t


def render_grades(student: Student, classes: list[ClassInfo], gpa: GPA | None = None) -> None:
    console.print(header(student, "grades"))
    console.print()
    console.print(courses_table(classes))
    if gpa and (gpa.rows or gpa.rank):
        console.print()
        console.print(gpa_line(gpa))


# ── assignments ──────────────────────────────────────────────────────────

def _sort_due(assignments: list[Assignment]) -> list[Assignment]:
    def key(a: Assignment) -> tuple[int, str]:
        for fmt in ("%m/%d/%Y",):
            try:
                return (0, datetime.strptime(a.due, fmt).isoformat())
            except ValueError:
                continue
        return (1, a.name.lower())
    return sorted(assignments, key=key, reverse=True)


def render_assignments(student: Student, classes: list[ClassInfo], *,
                       only: str | None = None, limit: int | None = None,
                       missing: bool = False) -> None:
    console.print(header(student, "assignments"))
    shown_any = False
    for c in classes:
        if only and only.lower() not in c.name.lower() and only.lower() not in (c.teacher or "").lower():
            continue
        items = _sort_due(c.assignments)
        if missing:
            items = [a for a in items if not a.grade]
        if limit:
            items = items[:limit]
        if not items:
            continue
        shown_any = True
        console.print()
        title = Text()
        title.append(f"P{c.period} " if c.period else "", style="dim")
        title.append(c.name, style="bold")
        title.append(f"  {c.current}", style=GRADE_STYLE.get(c.current[:1].upper(), "dim"))
        t = Table(box=None, pad_edge=False, header_style="dim", title=title, title_justify="left")
        t.add_column("Due", style="dim", no_wrap=True)
        t.add_column("Assignment")
        t.add_column("Term", style="dim", justify="center")
        t.add_column("Grade", justify="center")
        for a in items:
            t.add_row(a.due or "—", a.name, a.term or "—", grade_text(a.grade))
        console.print(t)
    if not shown_any:
        console.print("[dim]no matching assignments[/]")


# ── schedule ─────────────────────────────────────────────────────────────

DOW = {"M": 0, "T": 1, "W": 2, "R": 3, "F": 4}


def _meets_on(days: str, when: date) -> bool:
    if not days:
        return True
    d = when.weekday()
    mapping = {"M": 0, "T": 1, "W": 2, "R": 3, "F": 4, "S": 5, "U": 6}
    return any(mapping.get(tok.strip().upper()[:1]) == d for tok in days.split(","))


def render_schedule(student: Student, classes: list[ScheduledClass], term: str,
                    times: dict[str, str], when: date | None = None) -> None:
    when = when or date.today()
    label = when.strftime("%a %b %-d")
    console.print(header(student, f"schedule · term {term or '?'} · {label}"))
    console.print()
    t = Table(box=None, pad_edge=False, header_style="dim")
    t.add_column("", style="dim", width=3)
    t.add_column("Period", justify="right", style="dim", width=6)
    t.add_column("Time", style="dim", no_wrap=True)
    t.add_column("Class")
    t.add_column("Room", style="dim")
    now = datetime.now()
    current_marked = False
    for c in sorted((c for c in classes if not term or c.term == term),
                    key=lambda c: int(c.period) if c.period.isdigit() else 99):
        meets = _meets_on(c.days, when)
        row_style = "" if meets else "dim"
        mark = ""
        if meets and not current_marked and _is_now(times.get(c.period, ""), now):
            mark, row_style, current_marked = "▸", "bold", True
        t.add_row(mark, c.period, times.get(c.period, "") or "—", c.name, c.room or "—",
                  style=row_style)
    console.print(t)
    if not classes:
        console.print("[dim]no schedule posted for this term[/]")


def _is_now(window: str, now: datetime) -> bool:
    import re

    m = re.match(r"(\d{1,2}):(\d{2})\s*([AP]M)\s*-\s*(\d{1,2}):(\d{2})\s*([AP]M)", window)
    if not m:
        return False

    def to_dt(h: str, mi: str, ap: str) -> datetime:
        hour = int(h) % 12 + (12 if ap.upper() == "PM" else 0)
        return now.replace(hour=hour, minute=int(mi))

    return to_dt(*m.group(1, 2, 3)) <= now <= to_dt(*m.group(4, 5, 6))


# ── attendance ───────────────────────────────────────────────────────────

def render_attendance(student: Student, entries: list[AttendanceEntry], today_line: str = "") -> None:
    console.print(header(student, "attendance"))
    if today_line:
        console.print()
        console.print(Text(today_line, style="dim"))
    console.print()
    if not entries:
        console.print("[dim]no absences or tardies on record[/]")
        return
    t = Table(box=None, pad_edge=False, header_style="dim")
    t.add_column("Date", no_wrap=True)
    t.add_column("Reason")
    t.add_column("Period", style="dim", justify="center")
    t.add_column("Class", style="dim")
    for e in entries:
        style = "red" if "absent" in e.reason.lower() or "unexcused" in e.reason.lower() else ""
        t.add_row(e.date, Text(e.reason, style=style), e.period or "—", e.cls or "")
    console.print(t)


# ── json ─────────────────────────────────────────────────────────────────

def to_json(obj: Any) -> str:
    def default(o: Any) -> Any:
        if is_dataclass(o) and not isinstance(o, type):
            return asdict(o)
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        raise TypeError(f"{type(o).__name__} is not JSON serialisable")
    return json.dumps(obj, indent=2, default=default, ensure_ascii=False)
