# SPDX-License-Identifier: MPL-2.0
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from dev import restore_exercise as exercise


class RestoreExerciseSafetyTests(unittest.TestCase):
    def test_environment_does_not_inherit_external_database_settings(self):
        with patch.dict(os.environ, {'HOME': '/existing-home', 'PGHOST': 'danger', 'PGSERVICE': 'danger', 'PGPASSFILE': '/secret', 'PGSERVICEFILE': '/existing-service', 'POSTGRES_DB': 'production', 'RAILET_PRIVATE_MEDIA_ROOT': '/existing'}):
            env = exercise.environment(Path('/tmp/railet-restore-exercise-test'), 'exercise_restore', 'synthetic')
        self.assertNotIn('PGHOST', env)
        self.assertNotIn('PGSERVICE', env)
        self.assertNotIn('HOME', env)
        self.assertEqual(env['PGPASSFILE'], '/tmp/railet-restore-exercise-test/no-pgpass')
        self.assertEqual(env['PGSERVICEFILE'], '/tmp/railet-restore-exercise-test/no-pgservice')
        self.assertEqual(env['POSTGRES_DB'], 'exercise_restore')
        self.assertEqual(env['POSTGRES_HOST'], '/tmp/railet-restore-exercise-test/socket')
        self.assertEqual(env['RAILET_PRIVATE_MEDIA_ROOT'], '/tmp/railet-restore-exercise-test/restore-media')

    def test_missing_tools_fail_before_allocating_a_workspace(self):
        with tempfile.TemporaryDirectory() as path, patch.object(exercise.tempfile, 'mkdtemp') as allocate:
            with self.assertRaisesRegex(RuntimeError, 'Missing executable'):
                exercise.exercise(Path(path))
            allocate.assert_not_called()

    def test_failed_start_with_running_server_stops_before_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'owned'
            root.mkdir()
            binpath = exercise.PROJECT / '.local/pg-integration/install/bin'
            if not (binpath / 'pg_ctl').exists():
                self.skipTest('PostgreSQL development binaries unavailable')
            calls = []
            def fake_run(command, **kwargs):
                calls.append([str(x) for x in command])
                if 'start' in command:
                    raise subprocess.CalledProcessError(1, command)
            with patch.object(exercise.tempfile, 'mkdtemp', return_value=str(root)), \
                 patch.object(exercise.os, 'geteuid', return_value=1000), \
                 patch.object(exercise.pwd, 'getpwuid') as account, \
                 patch.object(exercise, 'run', side_effect=fake_run), \
                 patch.object(exercise.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)), \
                 patch.object(exercise.shutil, 'rmtree') as cleanup:
                account.return_value.pw_name = 'synthetic'
                with self.assertRaises(subprocess.CalledProcessError):
                    exercise.exercise(binpath)
                self.assertTrue(any('stop' in command for command in calls))
                cleanup.assert_called_once_with(root)

    def test_unknown_server_state_is_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'owned'
            root.mkdir()
            binpath = exercise.PROJECT / '.local/pg-integration/install/bin'
            if not (binpath / 'pg_ctl').exists():
                self.skipTest('PostgreSQL development binaries unavailable')
            def fail_start(command, **kwargs):
                if 'start' in command:
                    raise subprocess.CalledProcessError(1, command)
            with patch.object(exercise.tempfile, 'mkdtemp', return_value=str(root)), \
                 patch.object(exercise.os, 'geteuid', return_value=1000), \
                 patch.object(exercise.pwd, 'getpwuid') as account, \
                 patch.object(exercise, 'run', side_effect=fail_start), \
                 patch.object(exercise.subprocess, 'run', return_value=subprocess.CompletedProcess([], 4)), \
                 patch.object(exercise.shutil, 'rmtree') as cleanup:
                account.return_value.pw_name = 'synthetic'
                with self.assertRaisesRegex(RuntimeError, 'workspace retained'):
                    exercise.exercise(binpath)
                cleanup.assert_not_called()

    def test_fixture_refuses_unrelated_environment(self):
        for mode in ('seed', 'verify'):
            with self.subTest(mode=mode):
                result = subprocess.run([str(exercise.PROJECT / '.venv/bin/python'), str(exercise.PROJECT / 'dev/restore_fixture.py'), mode],
                                        env={'PATH': '/usr/bin:/bin'}, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Refusing to run outside', result.stderr)


if __name__ == '__main__':
    unittest.main()
