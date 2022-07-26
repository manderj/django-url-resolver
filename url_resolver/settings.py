import os


DISREGARDED_PYTHON_PATHS = os.getenv('DISREGARDED_PYTHON_PATHS', [
    'build',
    'tests',
])

DISREGARDED_DJANGO_PATHS = os.getenv('DISREGARDED_DJANGO_PATHS', [
    # 'settings',
])

OTHER_DISREGARDED_PATHS = os.getenv('OTHER_DISREGARDED_PATHS', [])

DISREGARDED_PATHS = (
    DISREGARDED_PYTHON_PATHS
    + DISREGARDED_DJANGO_PATHS
    + OTHER_DISREGARDED_PATHS
)