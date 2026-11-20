"""skyward — grades, assignments, schedule and attendance from Skyward.

Point it at your district's Skyward Student/Family Access URL and it logs
in fresh every run (Skyward sessions die in minutes, so no cookie cache).
"""

from __future__ import annotations

import sys
from datetime import date
from typing import Optional

import typer

from . import client as sky_client
from . import parse
from . import render

app = typer.Typer(
    help="Skyward grades, assignments, schedule and attendance in your terminal.",
    no_args_is_help=True,
    add_completion=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

BASE_HELP = ("Skyward web base URL, e.g. https://skyward.example.org/Sky/web/ "
             "(or SKYWARD_BASE, or base= in the config file)")


def _opts(
    base: Optional[str],
    user: Optional[str],
    password: Optional[str],
    security_code: Optional[str],
) -> tuple[sky_client.SkywardClient, str]:
    """Log in and return (client, student name)."""
    try:
        creds = sky_client.resolve_credentials(user, password, security_code)
        c = sky_client.SkywardClient(base=sky_client.resolve_base(base))
        c.login(creds)
        student = parse.parse_student(c.gradebook())
        return c, student
    except sky_client.LoginError as e:
        render.err_console.print(f"[red]login failed:[/] {e}")
        raise typer.Exit(2)
    except sky_client.SkywardError as e:
        render.err_console.print(f"[red]skyward error:[/] {e}")
        raise typer.Exit(3)


def _fail(msg: str, code: int = 3) -> None:
    render.err_console.print(f"[red]{msg}[/]")
    raise typer.Exit(code)


@app.command()
def grades(
    base: Optional[str] = typer.Option(None, "--base", envvar="SKYWARD_BASE", help=BASE_HELP),
    user: Optional[str] = typer.Option(None, "--user", "-u", help="Username (or SKYWARD_USER)"),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Password (or SKYWARD_PASS)"),
    security_code: Optional[str] = typer.Option(None, "--security-code", help="MFA/security code if required"),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output"),
    gpa: bool = typer.Option(False, "--gpa", help="Include GPA and class rank"),
):
    """Current grades for every class."""
    c, student = _opts(base, user, password, security_code)
    classes = parse.parse_gradebook(c.gradebook())
    with render.console.status("[dim]reading grades…") if not json_out else _noop():
        g = c.gpa() if gpa else None
    if json_out:
        typer.echo(render.to_json({
            "student": student,
            "classes": classes,
            "gpa": g,
        }))
        return
    render.render_grades(student, classes, g)


@app.command()
def assignments(
    base: Optional[str] = typer.Option(None, "--base", envvar="SKYWARD_BASE", help=BASE_HELP),
    user: Optional[str] = typer.Option(None, "--user", "-u"),
    password: Optional[str] = typer.Option(None, "--password", "-p"),
    security_code: Optional[str] = typer.Option(None, "--security-code"),
    course: Optional[str] = typer.Option(None, "--course", "-c", help="Filter by course or teacher"),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Max rows per course"),
    missing: bool = typer.Option(False, "--missing", "-m", help="Only ungraded assignments"),
    json_out: bool = typer.Option(False, "--json"),
):
    """Recent assignments, newest due date first."""
    c, student = _opts(base, user, password, security_code)
    classes = parse.parse_gradebook(c.gradebook())
    if json_out:
        out = []
        for cl in classes:
            if course and course.lower() not in cl.name.lower() and course.lower() not in (cl.teacher or "").lower():
                continue
            items = cl.assignments
            if missing:
                items = [a for a in items if not a.grade]
            out.append({"course": cl.name, "period": cl.period, "teacher": cl.teacher,
                        "current": cl.current, "assignments": items[:limit] if limit else items})
        typer.echo(render.to_json({"student": student, "courses": out}))
        return
    render.render_assignments(student, classes, only=course, limit=limit, missing=missing)


@app.command()
def schedule(
    base: Optional[str] = typer.Option(None, "--base", envvar="SKYWARD_BASE", help=BASE_HELP),
    user: Optional[str] = typer.Option(None, "--user", "-u"),
    password: Optional[str] = typer.Option(None, "--password", "-p"),
    security_code: Optional[str] = typer.Option(None, "--security-code"),
    day: Optional[str] = typer.Option(None, "--day", help="e.g. 2026-11-20 (default: today)"),
    json_out: bool = typer.Option(False, "--json"),
):
    """Today's schedule with times and rooms."""
    when = date.today()
    if day:
        try:
            when = date.fromisoformat(day)
        except ValueError:
            _fail(f"bad --day {day!r}; use YYYY-MM-DD", 1)
    c, student = _opts(base, user, password, security_code)
    gb = c.gradebook()
    sch = parse.parse_schedule(c.schedule())
    term = parse.current_term(c.schedule())
    times = parse.period_times(gb)
    if json_out:
        typer.echo(render.to_json({"student": student, "term": term, "date": when,
                                   "classes": sch, "times": times}))
        return
    render.render_schedule(student, sch, term, times, when)


@app.command()
def attendance(
    base: Optional[str] = typer.Option(None, "--base", envvar="SKYWARD_BASE", help=BASE_HELP),
    user: Optional[str] = typer.Option(None, "--user", "-u"),
    password: Optional[str] = typer.Option(None, "--password", "-p"),
    security_code: Optional[str] = typer.Option(None, "--security-code"),
    json_out: bool = typer.Option(False, "--json"),
):
    """Attendance history (absences, tardies, excused periods)."""
    c, student = _opts(base, user, password, security_code)
    page = c.attendance()
    entries = parse.parse_attendance(page)
    today_line = parse.parse_attendance_today(page)
    if json_out:
        typer.echo(render.to_json({"student": student, "today": today_line, "entries": entries}))
        return
    render.render_attendance(student, entries, today_line)


class _noop:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def main() -> None:
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)
