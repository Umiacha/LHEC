"""Adversarial defaults for the isolated migration schema integration test.

Run only with manage.py test; no global server settings are changed.
"""

from copy import deepcopy

from .settings import *  # noqa: F403
from .settings import DATABASES as application_databases


DATABASES = deepcopy(application_databases)
DATABASES['default'].setdefault('TEST', {}).update({
    'CHARSET': 'latin1',
    'COLLATION': 'latin1_swedish_ci',
})
# Deliberately override the connection's InnoDB default after normal setup.
# CREATE TABLE must still pin its engine rather than inheriting this value.
DATABASES['default']['OPTIONS']['init_command'] += ", default_storage_engine = 'MyISAM'"
