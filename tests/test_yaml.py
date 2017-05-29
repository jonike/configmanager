import pytest

from configmanager import Config


@pytest.fixture
def yaml_path1(tmpdir):
    return tmpdir.join('path1.yml').strpath


def test_config_written_to_and_read_from_yaml_file(yaml_path1):
    config = Config({
        'uploads': {
            'enabled': True,
            'threads': 5,
            'db': {
                'user': 'root',
            },
        },
    })
    original_values = config.dump_values()

    config.yaml.dump(yaml_path1, with_defaults=True)

    config.yaml.load(yaml_path1)
    assert config.dump_values() == original_values

    config2 = Config()
    config2.yaml.load(yaml_path1, as_defaults=True)
    assert config2.dump_values() == original_values


def test_config_written_to_and_read_from_yaml_string():
    config_str = (
        'uploads:\n'
        '  enabled: True\n'
        '  threads: 5\n'
        '  db:\n'
        '    user: root\n\n'
    )

    config = Config()
    config.yaml.loads(config_str, as_defaults=True)

    # Make sure the order is preserved
    assert list(config.iter_paths(recursive=True, key='str_path')) == [
        'uploads', 'uploads.enabled', 'uploads.threads', 'uploads.db', 'uploads.db.user'
    ]

    # And the values
    assert config.dump_values() == {
        'uploads': {
            'enabled': True,
            'threads': 5,
            'db': {
                'user': 'root',
            }
        }
    }

    config_str2 = config.yaml.dumps(with_defaults=True)
    assert config_str2 == (
        'uploads:\n'
        '  enabled: true\n'
        '  threads: 5\n'
        '  db:\n'
        '    user: root\n'
    )

    config2 = Config()
    config2.yaml.loads(config_str2, as_defaults=True)
    assert list(config2.iter_paths(recursive=True, key='str_path')) == [
        'uploads', 'uploads.enabled', 'uploads.threads', 'uploads.db', 'uploads.db.user'
    ]
    assert config2.dump_values() == config.dump_values()
