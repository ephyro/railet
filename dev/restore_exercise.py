#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Disposable synthetic PostgreSQL + private-media restore exercise.

Always creates its own cluster and empty databases. It accepts no database,
source-media, restore-media, socket, or cleanup path arguments.
"""
import argparse
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parent.parent
PORT = '55497'


def environment(root, database, user):
    """Do not inherit connection overrides, credentials or Django settings."""
    return {
        'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'PYTHONPATH': str(PROJECT),
        'PGPASSFILE': str(root / 'no-pgpass'), 'PGSERVICEFILE': str(root / 'no-pgservice'),
        'RAILET_DEBUG': '1', 'RAILET_SQLITE': '0', 'RAILET_ALLOWED_HOSTS': 'testserver',
        'POSTGRES_HOST': str(root / 'socket'), 'POSTGRES_PORT': PORT,
        'POSTGRES_USER': user, 'POSTGRES_DB': database,
        'RAILET_PRIVATE_MEDIA_ROOT': str(root / ('source-media' if database == 'exercise_source' else 'restore-media')),
        'RAILET_RESTORE_EXERCISE_ROOT': str(root),
    }


def run(command, *, env, quiet=False):
    subprocess.run([str(x) for x in command], cwd=PROJECT, env=env, check=True,
                   stdout=subprocess.DEVNULL if quiet else None)


def exercise(pg_bin):
    required = ('initdb', 'pg_ctl', 'createdb', 'pg_dump', 'pg_restore')
    for name in required:
        if not (pg_bin / name).is_file() or not os.access(pg_bin / name, os.X_OK):
            raise RuntimeError(f'Missing executable PostgreSQL tool: {name}')
    python = PROJECT / '.venv/bin/python'
    if not python.is_file():
        raise RuntimeError('Project .venv/bin/python is missing.')
    user = pwd.getpwuid(os.geteuid()).pw_name
    if os.geteuid() == 0:
        raise RuntimeError('Run as an unprivileged user, not root.')
    root = Path(tempfile.mkdtemp(prefix='railet-restore-exercise-', dir='/tmp'))
    root.chmod(0o700)
    start_attempted = False
    try:
        (root / 'socket').mkdir(mode=0o700)
        (root / 'marker').write_text('synthetic restore exercise\n')
        env = environment(root, 'exercise_source', user)
        run([pg_bin / 'initdb', '-D', root / 'cluster', '--no-locale', '--encoding=UTF8',
             '--auth-local=trust', '--auth-host=reject', '--username', user], env=env, quiet=True)
        start_attempted = True
        run([pg_bin / 'pg_ctl', '-D', root / 'cluster', '-l', root / 'postgres.log',
             '-o', f'-k {root / "socket"} -p {PORT} -c listen_addresses= -c unix_socket_permissions=0700',
             '-w', 'start'], env=env, quiet=True)
        for db in ('exercise_source', 'exercise_restore'):
            run([pg_bin / 'createdb', '-h', root / 'socket', '-p', PORT, '-U', user, db], env=env, quiet=True)
        run([python, 'manage.py', 'migrate', '--noinput'], env=env, quiet=True)
        run([python, 'dev/restore_fixture.py', 'seed'], env=env)
        # No writers exist in this isolated exercise during the database dump and file copy.
        backup = root / 'backup.dump'
        run([pg_bin / 'pg_dump', '-h', root / 'socket', '-p', PORT, '-U', user,
             '-Fc', '-f', backup, 'exercise_source'], env=env, quiet=True)
        shutil.copytree(root / 'source-media', root / 'backup-media', symlinks=False)
        shutil.copytree(root / 'backup-media', root / 'restore-media', symlinks=False)
        run([pg_bin / 'pg_restore', '-h', root / 'socket', '-p', PORT, '-U', user,
             '--exit-on-error', '--no-owner', '--no-privileges', '-d', 'exercise_restore', backup], env=env, quiet=True)
        run([python, 'dev/restore_fixture.py', 'verify'], env=environment(root, 'exercise_restore', user))
        print('PASS: isolated database and private media restored and verified.')
    finally:
        if start_attempted:
            status = subprocess.run([str(pg_bin / 'pg_ctl'), '-D', str(root / 'cluster'), 'status'],
                cwd=PROJECT, env=environment(root, 'exercise_source', user),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if status.returncode == 0:
                try:
                    run([pg_bin / 'pg_ctl', '-D', root / 'cluster', '-m', 'fast', '-w', 'stop'],
                        env=environment(root, 'exercise_source', user), quiet=True)
                except subprocess.CalledProcessError:
                    print(f'PostgreSQL did not stop; temporary workspace retained at {root}', file=sys.stderr)
                    raise
            elif status.returncode != 3:
                raise RuntimeError(f'Cannot confirm PostgreSQL stopped; workspace retained at {root}')
        shutil.rmtree(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pg-bin', type=Path, default=PROJECT / '.local/pg-integration/install/bin',
                        help='Directory containing compatible PostgreSQL tools (not a cluster).')
    args = parser.parse_args()
    try:
        exercise(args.pg_bin.resolve())
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f'Restore exercise failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
