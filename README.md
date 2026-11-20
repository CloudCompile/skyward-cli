# skyward

[![tests](https://github.com/CloudCompile/skyward-cli/actions/workflows/tests.yml/badge.svg)](https://github.com/CloudCompile/skyward-cli/actions/workflows/tests.yml)

Grades, assignments, schedule and attendance from Skyward Student/Family
Access, in your terminal. Python + [typer](https://typer.tiangolo.com)/[rich](https://rich.readthedocs.io),
`--json` on every read command.

Works against any district that uses the Skyward Student/Family Access
portal. There is no useful default instance, so tell it yours once:

```console
$ echo 'base=https://skyward.your-district.org/Sky/web/' >> ~/.config/skyward/config
```

or pass `--base URL`, or set `SKYWARD_BASE`. The sample output below uses
`https://skyward.example.org/Sky/web/`.

```console
$ skyward grades --gpa
Student Name  ·  Sample High School  ·  grades

#  Course                     Teacher           Q1  Q2  SE1  S1
1  Foundations of Fitness     Jordan Pike       A   –    –   A
2  WORLD HISTORY              Sam Ortiz         B   A    –   B
3  GEOMETRY HONORS            Alex Rivera       A   B    –   A
5  ENG 1: FOUNDATIONS HONORS  Dana Ellison      A   –    –   A
7  Environmental Science HO   Robin Lee         B   B    –   B
8  Concert Band               Jean Moreau       A   –    –   A

GPA 3.50  ·  rank 45 of 320
```

## Commands

| command | what it does |
| --- | --- |
| `skyward grades [--gpa] [--json]` | every class, term grades, current grade |
| `skyward assignments [-c COURSE] [-n N] [-m/--missing] [--json]` | assignments, newest due date first |
| `skyward schedule [--day YYYY-MM-DD] [--json]` | the current term's schedule with times and rooms |
| `skyward attendance [--json]` | absences, tardies, excused periods |

Every command takes `--base URL` (default: Rochester) so it works against
any district's Skyward, and `--json` where noted for piping into other
tools (`jq`, a widget, the Tidbyt renderer, …).

## Logging in

Skyward sessions die after a few minutes, so skyward **logs in fresh on
every run** and never stores cookies. Credentials come from, in order:

1. `--user/-u`, `--password/-p` flags
2. `SKYWARD_USER`, `SKYWARD_PASS`, `SKYWARD_SECURITY_CODE` env vars
3. `~/.config/skyward/config`:

   ```ini
   username=1234567
   password=hunter2
   # security_code=123456   # only if the district forces MFA
   ```

4. prompt (`getpass`, so it never lands in shell history)

The config file should be `chmod 600`. `skyward` never ticks "trust this
device" on the Skyward login form, so it can't silently expire sessions
your phone or school Chromebook rely on.

If your account needs a Skyward security code / MFA, pass
`--security-code`; without it the CLI stops with the portal's message
rather than retrying (repeated bad logins lock the account).

## How it talks to Skyward

Three requests:

1. `GET /Sky/web/seplog01.w` — the login form plus its hidden anti-anon
   fields (`hAnon`, `CurrentProgram`, `nameid`, …)
2. `POST /Sky/web/skyporthttp.w` — that form with
   `requestAction=eel&codeType=tryLogin&codeValue=login`. The reply is a
   caret-delimited token list (`dwd^webrecid^wfaaclrecid^…^enc^encses^…`)
3. `POST /Sky/web/sfgradebook001.w`, `sfschedule001.w`, `sfattendance001.w`
   with those tokens as form fields

The gradebook itself is a JSON blob (`sff.sv('sf_gridObjects', …)`) that
the page hands to the browser; skyward reads that directly instead of
scraping thousands of `<td>`s. GPA/class rank is fetched the way the page's
own JS does it: `POST /Sky/web/httploader.p?file=sfgradebook002.w` with
`action=viewGPARank`.

If Skyward changes its markup, `skyward/parse.py` is the only file to
touch, and `tests/fixtures/pages.py` is a synthetic copy of the page
shapes to test against.

## Install

```console
$ ./install.sh            # pipx-style editable install into ~/.venv-skyward
```

or run straight from the checkout: `./skyward-cli grades`.

## Tests

```console
$ python3 -m pytest
```

37 tests: parsers against synthetic pages, plus the CLI end-to-end against
a fake Skyward HTTP server (`tests/fake_skyward.py`) that reproduces the
token protocol, session expiry, and the `httploader.p` AJAX path.

## Notes

- Unofficial. Not affiliated with Skyward or any school district; it just automates the
  same requests your browser makes. Be kind to the portal: one login per
  command, pages cached within a run.
- Don't commit `~/.config/skyward/config` anywhere.

## See also

- [skyward-cli](https://github.com/CloudCompile/skyward-cli) — grades and assignments from the gradebook
- [msl-cli](https://github.com/CloudCompile/msl-cli) — the MyStudyLife planner, including the sync that fills it
- [classroom-cli](https://github.com/CloudCompile/classroom-cli) — Classroom posts, classwork and attachments
- [agenda-cli](https://github.com/CloudCompile/agenda-cli) — all of the above in one view
- [gsuite-cli](https://github.com/CloudCompile/gsuite-cli) — the school Google account's mail, drive, docs and calendar

## License

MIT — see [LICENSE](LICENSE).
