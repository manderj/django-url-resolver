import sys


def is_relative_to(from_path, to_path):
    # from_path.is_relative_to(to_path) only compatible to >= python3.9
    if sys.version_info >= (3, 9):
        return from_path.is_relative_to(to_path)
    from_path_str = str(from_path)
    return from_path_str == str(to_path)[0:len(from_path_str)]


def to_dotted_path(path, current_path):
    return str(path).replace(str(current_path) + '/', '').rsplit('.')[0].replace('/', '.')
