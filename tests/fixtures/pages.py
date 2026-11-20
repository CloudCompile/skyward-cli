"""Synthetic Skyward pages with the same structure as the real portal.

Built by hand rather than copied from a live session so no student data
lives in the repo. Shapes were verified against the real pages: login
detailform, `sff.sv()` inline state, and the `sf_gridObjects` JSON the
gradebook hands to the browser.
"""

from __future__ import annotations

import json

STUDENT_ID = "111111"
ENTITY_ID = "222"


def login_page() -> str:
    return """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html><head><title>Skyward: Loading page... (05.26.10.00.02-12.8)</title></head>
<body>
<form style='display:none;' name='navform' method='post' action='sepadm01.w'>
<input type="hidden" name="nameid" id="nameid" value="-1" />
<input type="hidden" name="ButtonID" id="ButtonID" value="" />
</form>
<form name='detailform' id='detailform' action='' method='post'>
<label class='EditLabelL' for='login'><div id='lblUsername'>Username</div></label><input type='text' class='EditInput' name='login' id='login'  autocomplete='off' tabIndex='5' style='width:163px; ' maxlength='50' aria-label='Username' size='28'  />
<label class='EditLabelL' for='password'><div id='lblPassword'>Password</div></label><input type='password' class='EditInput' name='password' id='password'  autocomplete='off' tabIndex='10' style='width:163px; ' maxlength='100' aria-label='Password' size='28'  />
<input type='text' class='EditInput' name='securityCode' id='securityCode' tabIndex='11' maxlength='50' aria-label='Security Code' size='28' />
<input type="checkbox" class="" name="cTrustDevice" id="cTrustDevice" tabIndex="11" />
<input type="hidden" name="SecurityMenuID" id="SecurityMenuID" value="0" />
<input type="hidden" name="nameid" id="nameid" value="-1" />
<input type="hidden" name="CurrentProgram" id="CurrentProgram" value="skyportlogin.w" />
<input type="hidden" name="Browser" id="Browser" value="IE" />
<input type="hidden" name="BrowserPlatform" id="BrowserPlatform" value="Win32" />
<input type="hidden" name="noheader" id="noheader" value="yes" />
<input type="hidden" name="duserid" id="duserid" value="-1" />
<input type="hidden" name="HomePage" id="HomePage" value="sepadm01.w" />
<input type="hidden" name="loginID" id="loginID" value="-1" />
<input type="hidden" name="hAnon" id="hAnon" value="aN0nT0k3n" />
<input type="hidden" name="pageused" id="pageused" value="Desktop" />
<input type="hidden" name="hforgotLoginPage" id="hforgotLoginPage" value="seplog01" />
<input type="hidden" name="qfileretr000" value="" />
</form>
<script type="text/javascript">
function tryLogin() { getExtraInfo('skyporthttp.w','tryLogin','login',''); }
</script>
</body></html>"""


def _shell(title: str, body: str, pages: dict[str, str] | None = None) -> str:
    """Page chrome, including the inline sff.sv() state real pages carry."""
    state = {
        "sessionid": "2000001" + "30000001",   # webrecid + wfaaclrecid
        "encses": "SeSsIoNkEyAbCdEf",
        "dwd": "1001",
        "nameid": STUDENT_ID,
        "gridCount": "1",
    }
    pages = pages or {}
    sv = "\n".join(f"sff.sv('{k}', '{v}');" for k, v in state.items())
    # The real portal merges each grid into one 'sf_gridObjects' map keyed by
    # grid id, which is where feedback/parse.py reads it from.
    grids = {gid: v for gid, v in pages.items() if gid.startswith("stuGradesGrid_")}
    objs = ""
    if grids:
        merged = "{" + ", ".join(f"{json.dumps(k)}:{json.dumps(v)}" for k, v in grids.items()) + "}"
        objs = ("sff.sv('sf_gridObjects',$.extend((sff.getValue('sf_gridObjects') || {}), "
                + merged + "));")
    return f"""<!doctype html>
<html lang='en'>
<head><meta http-equiv='Content-Type' charset='ISO-8859-1'>
<meta name="robots" content="noindex, nofollow">
<title>{title}</title>
<script type='text/javascript'>
var sffDefer = [];
</script>
</head>
<body>
{body}
<input id='reloadValue' type='hidden' name='reloadValue' value='' />
<script type='text/javascript' data-rel='sff'>{sv}
{objs}</script>
</body></html>"""


# ── gradebook ────────────────────────────────────────────────────────────

CLASSES = [
    ("900001", "01", "Algebra I", "1", "8:00 AM - 8:50 AM", "Ms. Addams"),
    ("900002", "02", "Biology", "2", "9:00 AM - 9:50 AM", "Mr. Bode"),
    ("900003", "03", "English 10", "3", "10:00 AM - 10:50 AM", "Dr. Curry"),
]


def _class_table(cor: str, sec: str, name: str, period: str, window: str, teacher: str) -> str:
    return f"""<table id="classDesc_{STUDENT_ID}_{cor}_0_{sec}"><tr><td class="vAt" style="width:16px" rowspan="3"><a id='exp_{cor}_{sec}_{STUDENT_ID}' name='exp_{cor}_{sec}_{STUDENT_ID}' class='sf_expander' href="javascript:void(0)"></a></td><td><span class='bld classDesc'><a id='cls{cor}' name='cls{cor}' href="javascript:void(0)" aria-haspopup='dialog'>{name}</a></span></td></tr><tr><td style="padding-left:10px"><label class="sf_labelRight">Period</label>{period}<span class='fXs fWn'>({window})</span></td></tr><tr><td style="padding-left:10px"><a id='tch{cor}' name='tch{cor}' href="javascript:void(0)" aria-haspopup='dialog'>{teacher}</a></td></tr></table>"""


def _grade_cell(cor: str, sec: str, grade: str) -> str:
    if not grade:
        return "<td class='sf_highlightYellow emptyGrade'><div class='gW'></div></td>"
    return (f"<td class='pB'><div class='gW'><a id='showGradeInfo' name='showGradeInfo' data-sId='{STUDENT_ID}' "
            f"data-eId='{ENTITY_ID}' data-cNI='{cor}' data-trk='0' data-sec='{sec}' data-gId='1' "
            f"data-bkt='TERM 1' data-lit='Q1' data-isEoc='no' href=\"javascript:void(0)\">{grade}</a></div></td>")


TERM_HEADERS = ["Q1", "Q2", "S1"]


def _assignment_row(cor: str, sec: str, name: str, due: str, term: str, grade: str) -> list[dict]:
    """One assignment row as a list of cells (name cell + one per term)."""
    label = (f"<td class=\"nPd aC\"><div class='bEw'><a id='showAssignmentInfo' name='showAssignmentInfo' "
             f"data-eId='x' data-sId='{STUDENT_ID}' href=\"javascript:void(0)\">{name}</a></br>"
             f"<label class=\"sf_labelRight\">Due:</label><span class='fXs fIl'>{due}&nbsp;&nbsp;({term})</span>"
             f"</div></td>")
    grade_fn = _grade_cell if grade else (
        lambda c, s, _g: "<td class='sf_highlightYellow emptyGrade'><div class='gW'></div></td>")
    return [{"h": label}] + [{"h": grade_fn(cor, sec, grade if t == term else "")}
                             for t in TERM_HEADERS]


GRADES = {
    "900001": {"Q1": "A", "Q2": "", "S1": "A", "assignments": [
        ("Quiz 1", "09/10/2026", "Q1", "A"),
        ("Quiz 2", "10/01/2026", "Q1", "B"),
        ("Homework Set 3", "11/12/2026", "Q2", ""),
    ]},
    "900002": {"Q1": "B", "Q2": "C", "S1": "B", "assignments": [
        ("Cell Lab", "09/15/2026", "Q1", "B"),
        ("Genetics Test", "11/05/2026", "Q2", "C"),
    ]},
    "900003": {"Q1": "A", "Q2": "A", "S1": "A", "assignments": [
        ("Essay Draft", "10/20/2026", "Q1", "A"),
        ("Book Talk", "11/10/2026", "Q2", ""),
    ]},
}

def gradebook() -> str:
    rows = []
    for cor, sec, name, period, window, teacher in CLASSES:
        g = GRADES[cor]
        rows.append({
            "h": f'<tr group-parent="{STUDENT_ID}_{cor}_0_{sec}" class="odd cPd" data-rowNum=\'1\'>',
            "c": [{"cId": f"row{cor}", "h": f'<td scope="row" class="cCl">row{cor}</td>'}] + [{"h": c} for c in [
                _grade_cell(cor, sec, g[t]) for t in TERM_HEADERS]],
        })
        for aname, due, term, grade in g["assignments"]:
            rows.append({
                "h": f'<tr group-child="{STUDENT_ID}_{cor}_0_{sec}" class="even bZe">',
                "c": _assignment_row(cor, sec, aname, due, term, grade),
            })
    grid = {
        "id": f"stuGradesGrid_{STUDENT_ID}_{ENTITY_ID}",
        "p": False, "rpp": 0, "lc": 1, "t": "default", "z": True,
        "th": {"r": [{"h": '<tr class="cPd gHd">', "c": [{"h": '<th class="cCl">Class</th>'}] +
                     [{"h": f'<th class="aCt">{t}</th>'} for t in TERM_HEADERS]}]},
        "tb": {"r": rows},
    }
    tables = "".join(_class_table(*c) for c in CLASSES)
    body = f"""<div class="sfTag"><span class="notranslate">Student</span> (Example High School)&nbsp;</div>
<a id='gpaRank_GPA_&nbsp;/&nbsp;Class_Rank' name='gpaRank'>GPA / Class Rank</a>
{tables}
<div id="grid_stuGradesGrid_{STUDENT_ID}_{ENTITY_ID}_gridWrap" class="gridWrap"></div>
<script>sff.sv('studentId', '{STUDENT_ID}'); sff.sv('entity', '{ENTITY_ID}');
sff.sv('stuGradeGrids', '{STUDENT_ID}_{ENTITY_ID}');</script>"""
    return _shell("Family Access", body, {f"stuGradesGrid_{STUDENT_ID}_{ENTITY_ID}": grid})


# ── schedule ─────────────────────────────────────────────────────────────

def _cell(period: str, term: str, name: str, teacher: str, room: str) -> str:
    if not name:
        return (f'<table id="grid_MATRIXStudentClasses_{STUDENT_ID}_{ENTITY_ID}_{period}_{term}" '
                f'grid-table=""><td scope="row">&nbsp;</td></tr></table>')
    return (f'<table id="grid_MATRIXStudentClasses_{STUDENT_ID}_{ENTITY_ID}_{period}_{term}" grid-table=""><tbody>'
            f'<tr class=""><td scope="row"><a id="c{period}{term}" href="javascript:void(0)">{name}</a><br>'
            f'<a id="t{period}{term}" href="javascript:void(0)">{teacher}</a><br>'
            f"<span tooltip='Days class meets'>Days M,T,W,R,F</span>&nbsp;&nbsp;&nbsp;Room {room}<br>"
            f"Example High School</td></tr></table>")


SCHEDULE = [
    # period, term, name, teacher, room
    ("1", "1", "Algebra I", "Ms. Addams", "101"),
    ("1", "2", "Algebra I", "Ms. Addams", "101"),
    ("2", "1", "Biology", "Mr. Bode", "Lab 2"),
    ("2", "2", "Biology", "Mr. Bode", "Lab 2"),
    ("3", "1", "English 10", "Dr. Curry", "303"),
    ("3", "2", "English 10", "Dr. Curry", "303"),
    ("4", "1", "Lunch", "", "Cafeteria"),
    ("4", "2", "Lunch", "", "Cafeteria"),
    ("5", "1", "", "", ""),
    ("5", "2", "", "", ""),
]


def schedule() -> str:
    days = ""
    for term in ("1", "2"):
        days += (f'<div id="grid_{term}_DAYS_gridWrap" class="gridWrap"><div class="sf_gridTableWrap">'
                 f'<table id="grid_{term}_DAYS" grid-table=""><tbody><tr class=""><td scope="row">'
                 f"<strong>Term {term}</strong><br><span>({'09/01/26 - 11/14/26' if term == '1' else '11/15/26 - 01/28/27'})</span>"
                 f"</td></tr></tbody></table></div></div>")
    cells = "".join(_cell(p, t, n, tc, r) for p, t, n, tc, r in SCHEDULE)
    body = f'<div id="grid_todaysCurrentSchedule"><table><tr><td>Currently Scheduled Class</td></tr></table></div>{days}{cells}'
    return _shell("Family Access Schedule", body)


# ── attendance ───────────────────────────────────────────────────────────

def attendance() -> str:
    rows = [
        ("Thu Nov 12, 2026", "Excused (Doctor Visit)", "2", "Biology"),
        ("Wed Nov 04, 2026", "Unexcused", "3", "English 10"),
    ]
    trs = "".join(
        f'<tr><td class="sf_rd">{d}</td><td>{r}</td><td>{p}</td><td>{c}</td></tr>' for d, r, p, c in rows)
    body = f"""<table id="grid_todaysattendance"><tr><td>Today's Attendance: Wed Nov 18, 2026</td></tr>
<tr><td>Today's attendance listed by student name. No Absences or Tardies were recorded for Student.</td></tr></table>
<table id="grid_attendanceHistory{STUDENT_ID}_{ENTITY_ID}"><tr><td>Date</td><td>Reason</td><td>Period</td><td>Class</td></tr>{trs}</table>"""
    return _shell("Family Access Attendance", body)


def home() -> str:
    return _shell("Family Access", '<a class="sf_navMenuItem" data-nav="sfgradebook001.w">Gradebook</a>')


# ── AJAX ─────────────────────────────────────────────────────────────────

def gpa_dialog() -> str:
    """Mirrors httploader.p replies: HTML plus the closing httpCalls script."""
    return """<html><body><div class="sfTag"><span class="notranslate">Student</span> (Example High School)</div>
<table grid-table=""><caption>GPA Type CUMULATIVE GPA CUMULATIVE EARNED CREDITS CUMULATIVE FAILED CREDITS Rank Rank Date</caption>
<tbody>
<tr><th>GPA Type</th><th>Cumulative GPA</th><th>Cumulative Earned Credits</th><th>Cumulative Failed Credits</th><th>Rank</th><th>Rank Date</th></tr>
<tr><td colspan="6"><strong>2026 - 2027 School Year</strong></td></tr>
<tr><td>Normal</td><td>3.75000</td><td>12.500</td><td>0.000</td><td>42 of 310</td><td>10/15/2026</td></tr>
</tbody></table><![CDATA[]]>
</body></html>"""


def ajax_error(msg: str) -> str:
    return f"""<html><body><![CDATA[]]>
sff.httpCalls['1'] = {{ 'messages':[{{'message':{json.dumps(msg)}}}], 'options':{{status:"error"}} }};
</html></body>"""
