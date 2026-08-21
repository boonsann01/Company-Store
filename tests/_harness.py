"""Shared test harness.

Two jobs, and the first one matters most:

1. Redirect the database to a throwaway file BEFORE anything opens the real
   one. `database.DB_PATH` is resolved at call time, so reassigning it here is
   enough — but it has to happen before `init_db()`. Without this, running the
   tests from the project folder would mutate the live store.

2. Provide a dependency-free check/report helper, so the suites run with a
   plain `python`, with nothing to install on the Pi.
"""
import os
import sys
import tempfile

# Import the app modules from the project root regardless of where the
# test was launched from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database  # noqa: E402


def use_temp_database():
    """Point every database call at a fresh empty file. Returns its path."""
    path = os.path.join(tempfile.mkdtemp(prefix='kiosk-test-'), 'store.db')
    database.DB_PATH = path
    database.init_db()
    return path


def admin_credentials():
    """Set known admin credentials before admin_server is imported."""
    os.environ['STORE_ADMIN_USERNAME'] = 'testadmin'
    os.environ['STORE_ADMIN_PASSWORD'] = 'testpass123'
    os.environ['STORE_ADMIN_SECRET_KEY'] = 'test-secret-key'
    return 'testadmin', 'testpass123'


class Results:
    """Minimal assertion recorder — prints as it goes, exits non-zero on any failure."""

    def __init__(self, title):
        self.title = title
        self.passed = []
        self.failed = []
        print(f'\n=== {title} ===')

    def section(self, name):
        print(f'\n{name}')

    def check(self, name, condition, detail=''):
        if condition:
            self.passed.append(name)
            print(f'  PASS: {name} {detail}')
        else:
            self.failed.append(name)
            print(f'  FAIL: {name} {detail}')
        return bool(condition)

    def raises(self, name, exc_type, fn, *args, **kwargs):
        """Assert fn(*args) raises exc_type."""
        try:
            fn(*args, **kwargs)
        except exc_type as exc:
            return self.check(name, True, f"'{exc}'")
        except Exception as exc:  # wrong exception type is still a failure
            return self.check(name, False, f'raised {type(exc).__name__}: {exc}')
        return self.check(name, False, 'did not raise')

    def finish(self):
        total = len(self.passed) + len(self.failed)
        print(f'\n--- {self.title}: {len(self.passed)}/{total} passed ---')
        for name in self.failed:
            print(f'    FAILED: {name}')
        return 1 if self.failed else 0
