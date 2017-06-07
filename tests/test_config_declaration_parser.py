import types

import pytest

from configmanager.items import Item
from configmanager import Config, Types
from configmanager.simple_sections import Section


@pytest.fixture
def app_config_cls_example():
    class DeepConfig:
        question = 'Why would you want a config this deep?'

    class UploadsConfig:
        enabled = True
        threads = 1
        type_ = Item(name='type', default=None)

    class DownloadsConfig:
        content_type = 'text/plain'
        deep = DeepConfig
        threads = Item(type=int)

    class AppConfig:
        uploads = UploadsConfig
        downloads = DownloadsConfig
        greeting = 'Hello, world!'

    return AppConfig


@pytest.fixture
def app_config_dict_example():
    return {
        'uploads': {
            'enabled': True,
            'threads': 1,
            'type_': Item(name='type', default=None),
        },
        'downloads': {
            'content_type': 'text/plain',
            'deep': {
                'question': 'Why would you want a config this deep?',
            },
            'threads': Item(type=int),
        },
        'greeting': 'Hello, world!',
    }


@pytest.fixture
def app_config_module_example():
    uploads = types.ModuleType('uploads')
    uploads.enabled = True
    uploads.threads = 1
    uploads.type_ = Item(name='type', default=None)

    downloads = types.ModuleType('downloads')
    downloads.content_type = 'text/plain'

    deep = types.ModuleType('deep')
    deep.question = 'Why would you want a config this deep?'
    downloads.deep = deep
    downloads.threads = Item(type=int)

    app_config = types.ModuleType('app_config')
    app_config.uploads = uploads
    app_config.downloads = downloads
    app_config.greeting = 'Hello, world!'

    return app_config


@pytest.fixture
def app_config_mixed_example():
    class DeepConfig:
        question = 'Why would you want a config this deep?'

    uploads_module = types.ModuleType('uploads')
    uploads_module.enabled = True
    uploads_module.threads = 1
    uploads_module.type_ = Item(name='type', default=None)

    downloads_dict = {
        'content_type': 'text/plain',
        'deep': DeepConfig,
        'threads': Item(type=int),
    }

    class AppConfig:
        uploads = uploads_module
        downloads = downloads_dict
        greeting = 'Hello, world!'

    return AppConfig


def test_class_based_config_declaration(app_config_cls_example):
    tree = Config(app_config_cls_example)

    assert tree['uploads']
    assert tree['uploads']['enabled'].name == 'enabled'
    assert tree['uploads']['type'].name == 'type'
    assert tree['uploads']['type'].value is None

    assert tree['downloads']
    assert tree['downloads']['deep']
    assert tree['downloads']['deep']['question']
    assert tree['downloads']['deep']['question'].value

    assert tree['downloads']['threads'].name == 'threads'
    assert tree['greeting'].name == 'greeting'

    assert 'deep' not in tree
    assert 'question' not in tree
    assert 'enabled' not in tree


def test_dict_based_config_declaration(app_config_dict_example, app_config_cls_example):
    dict_tree = Config(app_config_dict_example)
    cls_tree = Config(app_config_cls_example)
    assert dict_tree.dump_values() == cls_tree.dump_values()


def test_module_based_config_declaration(app_config_module_example, app_config_cls_example):
    module_tree = Config(app_config_module_example)
    cls_tree = Config(app_config_cls_example)
    assert module_tree.dump_values() == cls_tree.dump_values()


def test_mixed_config_declaration(app_config_mixed_example, app_config_cls_example):
    mixed_tree = Config(app_config_mixed_example)
    cls_tree = Config(app_config_cls_example)
    assert mixed_tree.dump_values() == cls_tree.dump_values()


def test_default_value_is_deep_copied():
    things = [1, 2, 3, 4]

    config = Config({'items': things})
    assert config['items'].value == [1, 2, 3, 4]

    things.remove(2)
    assert config['items'].value == [1, 2, 3, 4]


def test_config_declaration_can_be_a_list_of_items_or_two_tuples():
    config = Config([
        ('enabled', True),
        ('threads', 5),
        Item('greeting'),
        ('db', Config({'user': 'root'}))
    ])
    assert list(path for path, _ in config.iter_items(recursive=True)) == [('enabled',), ('threads',), ('greeting',), ('db', 'user')]


def test_declaration_can_be_a_list_of_field_names():
    config = Config([
        'enabled', 'threads', 'greeting', 'tmp_dir',
        ('db', Config(['user', 'host', 'password', 'name']))
    ])

    assert config.enabled
    assert config.threads
    assert config.greeting
    assert config.tmp_dir
    assert config.db.user
    assert config.db.host
    assert config.db.password
    assert config.db.name

    assert not config.enabled.has_value


def test_declaration_cannot_be_a_list_of_other_things():
    with pytest.raises(TypeError):
        Config(['enabled', True])

    with pytest.raises(TypeError):
        Config([True, 5])

    with pytest.raises(TypeError):
        Config([True, 5, 0.0])


def test_declaration_can_be_a_filename(tmpdir):
    config = Config([
        ('uploads', Config([
            ('enabled', True),
            ('db', Config([
                ('user', 'root'),
                ('password', 'secret'),
            ])),
            ('threads', 5),
        ]))
    ])

    json_path = tmpdir.join('uploads.json').strpath
    ini_path = tmpdir.join('uploads.ini').strpath
    yaml_path = tmpdir.join('uploads.yaml').strpath

    config.json.dump(json_path, with_defaults=True)
    config.yaml.dump(yaml_path, with_defaults=True)

    c2 = Config(json_path)
    assert c2.dump_values(with_defaults=True) == config.dump_values(with_defaults=True)

    c3 = Config(yaml_path)
    assert c3.dump_values(with_defaults=True) == config.dump_values(with_defaults=True)

    # For configparser test 2 levels only:
    config.uploads.configparser.dump(ini_path, with_defaults=True)

    c4 = Config(ini_path)
    print(c4.configparser.dumps(with_defaults=True))
    print(config.uploads.configparser.dumps(with_defaults=True))
    assert c4.configparser.dumps(with_defaults=True) == config.uploads.configparser.dumps(with_defaults=True)


def test_dict_with_all_keys_prefixed_with_at_symbol_is_treated_as_item_meta():
    config = Config({
        'enabled': {
            '@default': False,
        },
        'db': {
            'user': 'root',
            'name': {
                '@help': 'Name of the database'
            },
            '@help': 'db configuration',  # This should be ignored for now
        },
    })

    paths = set(path for path, _ in config.iter_items(recursive=True, key='str_path'))
    assert 'enabled' in paths
    assert 'enabled.@default' not in paths
    assert 'db' not in paths
    assert 'db.@help' not in paths
    assert 'db.user' in paths
    assert 'db.name' in paths
    assert 'db.name.@help' not in paths

    assert config.enabled.default is False
    assert config.db.name.help == 'Name of the database'

    # Make sure it still behaves like a bool
    config.enabled.value = 'yes'
    assert config.enabled.value is True

    # Name is excluded because it has no value
    assert config.db.dump_values() == {'user': 'root'}

    config.db.name.value = 'testdb'
    assert config.db.dump_values() == {'user': 'root', 'name': 'testdb'}


def test_dictionary_with_type_meta_field_marks_an_item():
    config = Config({
        'db': {
            '@type': 'dict',
            'user': 'root',
            'password': 'password',
            'host': 'localhost',
        }
    })

    assert isinstance(config.db, Item)
    assert config.db.type == Types.dict
    assert dict(**config.db.value) == {'user': 'root', 'password': 'password', 'host': 'localhost'}

    config = Config({
        'db': {
            '@something': 'dict',  # intentionally non-sense
            'user': 'root',
            'password': 'password',
            'host': 'localhost',
        }
    })

    assert isinstance(config.db, Config)

def test_accepts_configmanager_settings_which_are_passed_to_all_subsections():
    configmanager_settings = {
        'message': 'everyone should know this',
    }
    config1 = Config({}, configmanager_settings=configmanager_settings)
    assert config1.configmanager_settings['message'] == 'everyone should know this'

    config2 = Config({'greeting': 'Hello'}, configmanager_settings=configmanager_settings)
    assert config2.configmanager_settings['message'] == 'everyone should know this'

    config3 = Config({'db': {'user': 'root'}}, configmanager_settings=configmanager_settings)
    assert config3.configmanager_settings['message'] == 'everyone should know this'
    assert config3.db.configmanager_settings['message'] == 'everyone should know this'

    assert config3.db.configmanager_settings is config3.configmanager_settings
