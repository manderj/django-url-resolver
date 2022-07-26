import argparse
import collections
import inspect
import itertools
import multiprocessing
import pathlib
import os
from urllib.parse import urlparse

import django
from django.core.exceptions import AppRegistryNotReady
from django.core.exceptions import ImproperlyConfigured
from django.conf import settings
from django.urls import resolve
from django.urls.base import reverse
from django.urls.exceptions import Resolver404
from django.utils.functional import empty

import url_resolver.settings as resolve_urls_settings
from url_resolver.utils import is_relative_to
from url_resolver.utils import to_dotted_path


cwd = pathlib.Path.cwd()


def _get_func(func):
    if hasattr(func, 'view_class'):
        return _get_func(func.view_class)
    if hasattr(func, '__wrapped__'):
        return _get_func(func.__wrapped__)
    return func


class Project:
    def __init__(self, urlconfs):
        self._current_path = cwd
        self._disregarded_paths = [self._current_path / folder for folder in resolve_urls_settings.DISREGARDED_PATHS]

        # sadly multiprocessing pool's apply function only takes pickable arguments
        # therefore those can't be a generator
        self._project_settings = self._get_project_settings()
        self._urlconfs = urlconfs or self._get_urlconfs_paths()

    def _partof_disregarded_paths(self, path):
        return any(is_relative_to(path, disregarded_path) for disregarded_path in self._disregarded_paths)

    def _get_project_settings(self):
        project_settings = []

        for path in self._current_path.rglob('*settings*'):
            if not self._partof_disregarded_paths(path):
                if path.is_file() and path.suffix == '.py':
                    project_settings.append(ProjectSetting(self._current_path, path))
                elif path.is_dir():
                    project_settings.extend(
                        ProjectSetting(self._current_path, setting_file)
                        for setting_file in path.rglob('*.py')
                        if setting_file.stem != '__init__'
                    )
        return project_settings

    def _get_urlconfs_paths(self):
        urlconfs = []
        for url_path in self._current_path.rglob('*urls*'):
            if not self._partof_disregarded_paths(url_path):
                if url_path.is_dir():
                    urlconfs.extend(to_dotted_path(filepath, self._current_path) for filepath in url_path.glob('*.py'))
                elif url_path.is_file() and url_path.suffix == '.py':
                    urlconfs.append(to_dotted_path(url_path, self._current_path))
        return urlconfs

    def find_urls(self, searched_urls):
        # make sure urls not repeated
        searched_urls = set(searched_urls)
        task_results = []

        # Bypass django Apps' threading Rlock
        # https://github.com/django/django/blob/main/django/apps/registry.py#L49
        # by using multiprocessing to load each settings and search for urls inside new process concurrently
        pool = multiprocessing.Pool(processes=len(self._project_settings))
        for setting in self._project_settings:
            task_results.append(pool.apply(setting.find_urls, (searched_urls, self._urlconfs)))
        pool.close()
        pool.join()

        # merge results by urls
        results = {}
        for task_result in task_results:
            for url, found_pattern in task_result.items():
                results[url] = found_pattern
        return results


class ProjectSetting:
    def __init__(self, current_path, setting_path):
        self._setting_path = setting_path
        self._current_path = current_path
        self.dotted_path = to_dotted_path(self._setting_path, self._current_path)
        self.configured = False

    def configure(self):
        # FIXME: find a prettier way to deal with Django settings
        # reset django settings otherwise a RuntimeError 'Settings already configured' is raised
        try:
            setattr(settings, '_wrapped', empty)
            os.environ['DJANGO_SETTINGS_MODULE'] = self.dotted_path
            django.setup()
            self.configured = True
        except (AttributeError, ImproperlyConfigured, AppRegistryNotReady):
            pass

    def find_urls(self, searched_urls, urlconfs):
        self.configure()

        results = {}
        if not self.configured:
            return results

        for url, urlconf in itertools.product(searched_urls, urlconfs):
            parsed_url = urlparse(url)

            if not parsed_url.netloc:
                url_path = reverse(url)
            else:
                url_path = parsed_url.path

            # enforce slash ending url if project configured as is
            if settings.APPEND_SLASH and url_path[-1] != '/':
                url_path = url_path + '/'

            try:
                view = resolve(url_path, urlconf=urlconf)
            except (AttributeError, Resolver404, ImproperlyConfigured):
                continue

            # get the current function and all expected resources for display
            *filename, view_name = view._func_path.split('.')
            fnc = _get_func(view.func)
            filename = inspect.getsourcefile(fnc)
            _source_code, line = inspect.getsourcelines(fnc)

            results[url] = {
                'filename': filename,
                'line': line,
                'urlconf': urlconf,
                'index': view.view_name,
                'route': view.route,
                'view_name': view_name,
                'setting': self.dotted_path,
            }
        return results


def resolve_project_urls(args):
    project = Project(urlconfs=[args.urlconf] if args.urlconf else None)
    possible_url_paths = project.find_urls(args.urls)

    msg = ""
    for url, results in possible_url_paths.items():
        msg = f"[{url}]:\n\t"
        if args.filename:
            msg += f"+{results['line']} {results['filename']}"
        elif args.view:
            msg += f"{results['view_name']}"
        # elif args.template:
        # TODO: find a way to get the template used by the actual view
        else:
            msg += (
                f"route=\"{results['route']}\"\n"
                f"\tfilename=\"{results['filename']}:{results['line']}\"\n"
                f"\tindex=\"{results['index']}\"\n"
                f"\tview_name=\"{results['view_name']}\""
            )
    if not possible_url_paths:
        msg += "URL couldn't be found."
    print(msg)


def main():
    """
    Find where an URL is defined
    >>> [DJANGO_SETTINGS_MODULE=<settings_path>] resolve_urls <URL> [<URL>] [--conf=<URLCONF>]...
    """
    parser = argparse.ArgumentParser(description="URLResolver")
    parser.add_argument('urls', metavar='URL', type=str, nargs='+', help='list of urls')
    parser.add_argument('--conf', dest='urlconf', help='url conf to search url from', default=None)
    parser.add_argument('--filename', '-f', dest='filename', help='Only show file used', action='store_true')
    # parser.add_argument('--template', '-t', dest='template', help='Only show template used', action='store_true')
    parser.add_argument('--view', '-v', dest='view', help='Only show view used', action='store_true')

    args = parser.parse_args()
    resolve_project_urls(args)


if __name__ == '__main__':
    main()
