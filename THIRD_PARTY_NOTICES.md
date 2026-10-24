# Third-party software

Railet's original community source is covered by MPL 2.0; see [LICENSE](LICENSE). The repository does not vendor the packages below. Installers fetch them separately, with their own license texts and notices. Preserve the upstream notices when redistributing packages or container images, and review the exact resolved artifacts before a binary release.

| Dependency | License | Upstream |
| --- | --- | --- |
| Django | BSD-3-Clause | https://github.com/django/django |
| asgiref (Django dependency) | BSD-3-Clause | https://github.com/django/asgiref |
| sqlparse (Django dependency) | BSD-3-Clause | https://github.com/andialbrecht/sqlparse |
| psycopg and psycopg-binary | LGPL-3.0-only | https://github.com/psycopg/psycopg |
| Pillow | MIT-CMU; bundled components have additional notices | https://github.com/python-pillow/Pillow |
| Gunicorn (optional staging) | MIT | https://github.com/benoitc/gunicorn |
| WhiteNoise (optional staging) | MIT | https://github.com/evansd/whitenoise |

`requirements.txt` and `requirements-staging.txt` declare version ranges. This source preview does not ship a reproducible production dependency lock or binary distribution. psycopg-binary/Pillow wheels can include native libraries with their own licenses; Python/PostgreSQL/Caddy/container base images and Docker tooling also carry separate licenses. Inspect the installed artifacts when packaging a distribution; this table does not replace their notices or LGPL obligations.

The interface uses independently written local templates, CSS, JavaScript, and inline SVG. No private vendor captures, commercial form packs, bundled fonts, or third-party illustration assets are included in this source publication. Railet and Ephyro names are project identifiers, not a grant of trademark rights.
