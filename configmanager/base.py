import collections
import copy

from configparser import ConfigParser
import six

from .exceptions import UnknownConfigItem, ConfigValueMissing
from .proxies import ConfigItemProxy, ConfigValueProxy, ConfigSectionProxy


class _NotSet(object):
    def __nonzero__(self):
        return False

    def __bool__(self):
        return False

    def __str__(self):
        return ''

    def __repr__(self):
        return '<NotSet>'

    def __deepcopy__(self, memodict):
        return self

    def __copy__(self):
        return self


not_set = _NotSet()


def resolve_config_path(*path):
    for p in path:
        if not isinstance(p, six.string_types):
            raise TypeError('Config path segments should be strings, got a {}: {}'.format(type(p), p))
        if not p:
            raise ValueError('Config path segments should be non-empty strings, got an empty one')

    if len(path) == 0:
        raise ValueError('Config path must not be empty')

    return tuple(path)


def resolve_config_prefix(*prefix):
    if len(prefix) == 0:
        return tuple()

    return resolve_config_path(*prefix)


def parse_bool_str(bool_str):
    return str(bool_str).lower().strip() in ('yes', 'y', 'yeah', 't', 'true', '1', 'yup', 'on')


class ConfigItem(object):
    """
    Represents a single configurable thing which has a name (a path), a type, a default value, a value,
    and other things.
    """

    DEFAULT_SECTION = 'DEFAULT'
    strpath_separator = '/'

    class Descriptor(object):
        def __init__(self, name, default=not_set, value=not_set):
            self.name = name
            self.default = default
            self.value = value
            self.attr_name = '_{}'.format(self.name)

        def __set__(self, instance, value):
            setattr(instance, self.attr_name, value)

        def __get__(self, instance, owner):
            return getattr(instance, self.attr_name, self.default)

    #: Default value.
    default = Descriptor('default')

    #: Type, defaults to ``str``. Type can be any callable that converts a string to an instance of
    #: the expected type of the config value.
    type = Descriptor('type', default=str)

    # Internally, hold on to the raw string value that was used to set value, so that
    # when we persist the value, we use the same notation
    raw_str_value = Descriptor('raw_str_value')

    required = Descriptor('required', default=False)

    # envvar = Descriptor('envvar')
    # prompt = Descriptor('prompt')
    # labels = Descriptor('labels')
    # choices = Descriptor('choices')

    def __init__(self, *path, **kwargs):
        #: a ``tuple`` of config's path segments.
        self.path = None

        resolved = resolve_config_path(*path)
        if len(resolved) == 1:
            self.path = tuple([self.DEFAULT_SECTION]) + resolved
        else:
            self.path = resolved

        # NB! type must be set first because otherwise setting value below may fail.
        if 'type' in kwargs:
            self.type = kwargs.pop('type')

        self._value = not_set
        for k, v in kwargs.items():
            setattr(self, k, v)

    @property
    def strpath(self):
        return self.strpath_separator.join(self.path)

    @property
    def section(self):
        """
        The first segment of :attr:`.path`.
        """
        if len(self.path) != 2:
            raise RuntimeError('section is not defined for items with non-trivial paths')
        return self.path[0]

    @property
    def option(self):
        """
        The second segment of :attr:`.path`.
        """
        if len(self.path) != 2:
            raise RuntimeError('option is not defined for items with non-trivial paths')
        return self.path[-1]

    @property
    def name(self):
        """
        A string, the last segment of :attr:`.path`.
        """
        return self.path[-1]

    @property
    def value(self):
        """
        Value or default value (if no value set) of the :class:`.ConfigItem` instance. 
        """
        if self._value is not not_set:
            return self._value
        if self.default is not_set and self.required:
            raise ConfigValueMissing(self.path)
        return self.default

    @value.setter
    def value(self, value):
        self._value = self._parse_str_value(value)
        if not issubclass(self.type, six.string_types):
            if isinstance(value, six.string_types):
                self.raw_str_value = value
            else:
                self.raw_str_value = not_set

    @property
    def has_value(self):
        """
        Returns:
            ``True`` if the :class:`.ConfigItem` has a value set.
        """
        return self._value is not not_set

    @property
    def is_default(self):
        """
        Returns:
            ``True`` if item does not have a value set, or its value equals the default value.
                In other words, it returns ``True`` if item's resolved value equals its default value.
                This is NOT the opposite of :attr:`.has_value`!
        """
        return self._value is not_set or self._value == self.default

    @property
    def has_default(self):
        """
        Is ``True`` if the :class:`.ConfigItem` has the default value set.
        """
        return self.default is not not_set

    def __str__(self):
        if self.raw_str_value is not not_set:
            return self.raw_str_value
        if self.has_value or self.has_default:
            return str(self.value)
        else:
            return repr(self)

    def __hash__(self):
        return hash(
            (self.type, self.path, self._value if self.has_value else self.default)
        )

    def __eq__(self, other):
        if isinstance(other, ConfigItem):
            # if self is other:
            #     return True
            return (
                self.type == other.type
                and
                self.path == other.path
                and
                (
                    (
                        # Both have a value that can be compared
                        (self.has_value or self.has_default)
                        and (other.has_value or other.has_default)
                        and (self.value == other.value)
                    )
                    or
                    (
                        # Neither has value that can be compared
                        not (self.has_value or self.has_default)
                        and not (other.has_value or other.has_default)
                    )
                )
            )
        return False

    def reset(self):
        """
        Unsets :attr:`value`. 
        """
        self._value = not_set
        self.raw_str_value = not_set

    def __repr__(self):
        if self.has_value:
            value = str(self.value)
        elif self.default is not not_set:
            value = str(self.default)
        else:
            value = self.default

        return '<{} {} {!r}>'.format(self.__class__.__name__, self.strpath, value)

    def _parse_str_value(self, str_value):
        if str_value is None or str_value is not_set:
            return str_value
        elif self.type is bool:
            return parse_bool_str(str_value)
        else:
            return self.type(str_value)


class ConfigManager(object):
    """
    A collection and manager of instances of :class:`.ConfigItem`.
    
    Args:
        *configs:
            config items describing what configs this manager handles.
    
    Unlike ``ConfigParser``, config manager normally works only with 
    registered config items. A good time to register items is when creating a manager::
    
        config = ConfigManager(
            ConfigItem('uploads', 'threads'),
            ConfigItem('uploads', 'enabled', type=bool, default=False),
        )
    
    Alternatively, you can register items with :meth:`.add` or 
    by passing ``as_defaults=True`` to :meth:`.read`, :meth:`.read_file`, and other
    read methods::
    
        config.read('defaults.ini', as_defaults=True)
    
    """

    def __init__(self, *configs, **config_manager_options):
        self._options = {
            'config_parser_factory': config_manager_options.pop('config_parser_factory', ConfigParser),
            'config_item_factory': config_manager_options.pop('config_item_factory', ConfigItem),
        }

        if config_manager_options:
            raise ValueError('Unsupported option: {}'.format(next(config_manager_options.keys())))

        self._configs = collections.OrderedDict()
        self._prefixes = collections.OrderedDict()

        self.t = ConfigItemProxy(self)
        self.v = ConfigValueProxy(self)
        self.s = ConfigSectionProxy(self)

        for config in configs:
            self.add(config)

    @property
    def config_item_factory(self):
        return self._options['config_item_factory']

    @property
    def config_parser_factory(self):
        return self._options['config_parser_factory']

    @property
    def default_section(self):
        return self.config_item_factory.DEFAULT_SECTION

    def _resolve_config_path(self, *path):
        path = resolve_config_path(*path)
        if len(path) == 1:
            return (self.default_section,) + path
        return path

    def add(self, *args, **kwargs):
        """
        Register a new config item to manage.
        
        Examples:
            config.add('section', 'option2', default='hello')
            config.add('option1')
            config.add('option2', default='hello')
            config.add(ConfigItem('section', 'option1', default='hello'))
        """

        if args:
            if not isinstance(args[0], six.string_types):
                assert len(args) == 1 and not kwargs
                return self._add_config_item(args[0])

        path = tuple(args)
        if 'section' in kwargs:
            assert 'path' not in kwargs
            if 'option' in kwargs:
                assert not path
                path = (kwargs.pop('section'), kwargs.pop('option'))
            else:
                path += (kwargs.pop('section'))
        elif 'path' in kwargs:
            path = kwargs.pop('path')

        assert 'option' not in kwargs  # ConfigItem('section', option='option') is truly ugly

        return self._add_config_item(self.config_item_factory(*path, **kwargs))

    def _add_config_item(self, item):
        if item.path in self._configs:
            raise ValueError('Config item {} already present'.format(item.name))

        item = copy.deepcopy(item)
        self._configs[item.path] = item

        prefix = []
        for p in item.path[:-1]:
            prefix.append(p)
            temp_prefix = tuple(prefix)
            if temp_prefix not in self._prefixes:
                self._prefixes[temp_prefix] = set()
            self._prefixes[temp_prefix].add(item)

    def remove(self, *path):
        item = self.get_item(*path)

        prefixes_to_remove = []
        for prefix in self._prefixes.keys():
            if item in self._prefixes[prefix]:
                self._prefixes[prefix].remove(item)
                if not self._prefixes[prefix]:
                    prefixes_to_remove.append(prefix)

        for prefix in prefixes_to_remove:
            del self._prefixes[prefix]

        del self._configs[item.path]

    def get(self, *path_and_fallback):
        """
        Returns :attr:`.ConfigItem.value` of item matching the path. If the item does
        not have a value or a default value set, the ``fallback`` value is returned.
        
        Args:
            *path_and_fallback: 

        Returns:
            config value
        
        Raises:
            UnknownConfigItem:
                if a config item with the specified ``path`` is not
                managed by this manager.

        """
        if not path_and_fallback:
            raise ValueError('Path is required')

        # The last element of path_and_fallback cannot be part of path if it's not a string
        if isinstance(path_and_fallback[-1], six.string_types) and self.has(*path_and_fallback):
            return self.get_item(*path_and_fallback).value

        if self.has(*path_and_fallback[:-1]):
            config = self.get_item(*path_and_fallback[:-1])
            fallback = path_and_fallback[-1]
            if config.has_value or config.has_default:
                return config.value
            else:
                return fallback
        else:
            raise UnknownConfigItem('Config not found: {}'.format(path_and_fallback))

    def get_item(self, *path):
        """Get a config item by path.

        If you need to get a config value, use :meth:`ConfigManager.get` instead.

        Args:
            *path:

        Returns:
            ConfigItem: an existing or newly created :class:`.ConfigItem` matching the ``path``.
        
        Raises:
            UnknownConfigItem: if this manager does not know about a config with the specified ``path``.

        Examples:
            >>> cm = ConfigManager(ConfigItem('very', 'real', default=0.0, type=float))
            >>> cm.get_item('very', 'real')
            <ConfigItem very.real 0.0>

        """
        path = self._resolve_config_path(*path)

        if path in self._configs:
            return self._configs[path]
        else:
            raise UnknownConfigItem(*path)

    def set(self, *path_and_value):
        """
        Sets ``value`` of previously added :class:`.ConfigItem` identified by ``path``.
        
        :param path_and_value:
        """
        if len(path_and_value) < 2:
            raise ValueError('set requires at least two arguments - a path segment and a value')
        self.get_item(*path_and_value[:-1]).value = path_and_value[-1]

    def has(self, *path):
        """
        Args:
            *path:

        Returns:
            bool: ``True`` if the specified config is managed by this :class:`.ConfigManager`, ``False`` otherwise. 
        """
        return self._resolve_config_path(*path) in self._configs

    def find_items(self, *prefix):
        prefix = resolve_config_prefix(*prefix)
        if not prefix:
            return self._configs.values()
        else:
            return (self._configs[path] for path in self._configs.keys() if path[:len(prefix)] == prefix[:])

    def find_paths(self, *prefix):
        prefix = resolve_config_prefix(*prefix)
        if not prefix:
            return self._configs.keys()
        else:
            return (path for path in self._configs.keys() if path[:len(prefix)] == prefix[:])

    def find_prefixes(self, *prefix):
        prefix = resolve_config_prefix(*prefix)
        if not prefix:
            return self._prefixes.keys()
        else:
            return (p for p in self._prefixes.keys() if p[:len(prefix)] == prefix[:])

    def export(self, *prefix):
        """
        Returns:
            list: list of ``(name_without_prefix, value)`` pairs for each config item under the specified
            prefix.
        """
        pairs = []

        for item in self.find_items(*prefix):
            if item.has_value or item.has_default:
                item_name_without_prefix = '.'.join(item.path[len(prefix):])
                pairs.append((item_name_without_prefix, item.value))

        return pairs

    def read(self, *args, **kwargs):
        """
        Read and parse configuration from one or more files identified by individual filenames or lists
        of filenames.
        
        Keyword Args:
            as_defaults=False:
                If set to ``True`` all parsed config items will be added to the config 
                manager and their values set as defaults.
            
            encoding=None: as in ``ConfigParser.read``
        
        Returns:
            list of filenames from which config was successfully loaded.
        
        Examples:
            
            >>> config = ConfigManager()
            >>> config.read('defaults.ini')
            >>> config.read('country_config.ini', 'user_config.ini')
            >>> config.read(['country_config.ini', 'user_config.ini'])  # ConfigParser-like access
        
        """
        as_defaults = kwargs.pop('as_defaults', False)

        used_filenames = []
        cp = self.config_parser_factory()

        def get_filenames():
            for arg in args:
                if isinstance(arg, six.string_types):
                    yield arg
                else:
                    for filename in arg:
                        yield filename

        # Do it one file after another so that we can tell which file contains invalid configuration
        for filename in get_filenames():
            result = cp.read(filename, **kwargs)
            if result:
                self.load_from_config_parser(cp, as_defaults=as_defaults)
                used_filenames.append(filename)

        return used_filenames

    def read_file(self, fileobj, as_defaults=False):
        """
        Read configuration from a file descriptor like in ``ConfigParser.read_file``.
        
        Keyword Args:
            as_defaults=False:
                If set to ``True`` all parsed config items will be added to the config 
                manager and their values set as defaults.
        """
        cp = self.config_parser_factory()
        cp.read_file(fileobj)
        self.load_from_config_parser(cp, as_defaults=as_defaults)

    def read_string(self, string, source=not_set, as_defaults=False):
        """
        Read configuration from a string like in ``ConfigParser.read_string``.
        
        Only supported in Python 3.
        
        Keyword Args:
            as_defaults=False:
                If set to ``True`` all parsed config items will be added to the config 
                manager and their values set as defaults.
        """
        cp = self.config_parser_factory()
        if source is not not_set:
            args = (string, source)
        else:
            args = (string,)
        cp.read_string(*args)
        self.load_from_config_parser(cp, as_defaults=as_defaults)

    def read_dict(self, dictionary, source=not_set, as_defaults=False):
        """
        Read configuration from a dictionary like in ``ConfigParser.read_dict``.
        
        Keyword Args:
            as_defaults=False:
                If set to ``True`` all parsed config items will be added to the config 
                manager and their values set as defaults.
        """
        cp = self.config_parser_factory()
        if source is not not_set:
            args = (dictionary, source)
        else:
            args = (dictionary,)
        cp.read_dict(*args)
        self.load_from_config_parser(cp, as_defaults=as_defaults)

    def write(self, fileobj_or_path):
        """
        Write configuration to a file object or a path.
        
        This differs from ``ConfigParser.write`` in that it accepts a path too.
        """
        cp = self.config_parser_factory()
        self.load_into_config_parser(cp)

        if isinstance(fileobj_or_path, six.string_types):
            with open(fileobj_or_path, 'w') as f:
                cp.write(f)
        else:
            cp.write(fileobj_or_path)

    def reset(self):
        """
        Resets values of config items.
        """
        for config in self._configs.values():
            config.reset()

    def load_from_config_parser(self, cp, as_defaults=False):
        """
        Updates config items from data in `ConfigParser`
        
        Args:
            cp (ConfigParser):
        
        Keyword Args:
            as_defaults=False:
        """
        for section in cp.sections():
            for option in cp.options(section):
                value = cp.get(section, option)
                if as_defaults:
                    if not self.has(section, option):
                        self.add(self.config_item_factory(section, option, default=value))
                    else:
                        self.get_item(section, option).default = value
                else:
                    self.get_item(section, option).value = value

    def load_into_config_parser(self, cp):
        """
        Writes config to `ConfigParser`.
        
        Items with :attr:`.ConfigItem.path` longer than two segments will fail
        as standard `ConfigParser` file format does not support it.
        
        Args:
            cp (ConfigParser): 
        """
        for config in self._configs.values():
            if len(config.path) > 2:
                raise NotImplementedError('{} with more than 2 path segments cannot be loaded into {}'.format(
                    config.__class__.__name__, self.__class__.__name__
                ))
            if not config.has_value:
                continue
            if not cp.has_section(config.section):
                cp.add_section(config.section)
            cp.set(config.section, config.option, str(config))

    @property
    def is_default(self):
        for item in self.find_items():
            if not item.is_default:
                return False
        return True
