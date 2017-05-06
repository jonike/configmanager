import pytest

from configmanager import ConfigItem


@pytest.mark.parametrize('args', [
    ('section1', 'option1'),
    ('section1.option1',),
])
def test_initialisation_of_section_and_option(args):
    c = ConfigItem(*args)
    assert c.section == 'section1'
    assert c.option == 'option1'


def test_initialisation_with_default_section():
    c = ConfigItem('option1')
    assert c.section == 'DEFAULT'
    assert c.option == 'option1'


@pytest.mark.parametrize('args', [
    (True, True),
    ('section', True),
    (True, 'section'),
    (123, 456),
])
def test_paths_with_non_string_segments_raise_type_error(args):
    with pytest.raises(TypeError):
        ConfigItem(*args)


def test_value_with_no_default_value():
    c = ConfigItem('a', 'b')

    with pytest.raises(RuntimeError):
        assert c == ''

    assert not c.has_value
    assert not c.has_default

    with pytest.raises(RuntimeError):
        assert not c.value

    c.value = 'c'
    assert c.value == 'c'
    assert c == 'c'

    assert c.has_value

    c.value = 'd'
    assert c.value == 'd'
    assert c == 'd'
    assert c == c.value

    assert not c.has_default


def test_value_with_default_value():
    c = ConfigItem('a', 'b', default='c')

    assert not c.has_value
    assert c.has_default
    assert c.value == 'c'

    c.value = 'd'

    assert c.has_value
    assert c.has_default
    assert c.value == 'd'

    c.reset()
    assert not c.has_value
    assert c.has_default
    assert c.value == 'c'

    d = ConfigItem('a', 'b', default='c', value='d')
    assert d.value == 'd'

    d.value = 'e'
    assert d.value == 'e'

    d.reset()
    assert d.value == 'c'


def test_value_gets_stringified():
    c = ConfigItem('a', value='23')
    assert c == '23'
    assert c != 23

    c.value = 24
    assert c == '24'
    assert c != 24


def test_int_value():
    c = ConfigItem('a', type=int, default=25)
    assert c == 25

    c.value = '23'
    assert c == 23
    assert c != '23'

    c.reset()
    assert c == 25


def test_bool_of_value():
    c = ConfigItem('a')

    with pytest.raises(RuntimeError):
        # Cannot evaluate if there is no value and no default value
        assert not c

    c.value = 'b'
    assert c

    c.value = ''
    assert not c

    d = ConfigItem('a', default='b')
    assert d

    d.value = ''
    assert not d


def test_str_and_repr_of_not_set_value():
    c = ConfigItem('a')

    with pytest.raises(RuntimeError):
        assert not str(c)

    assert repr(c) == '<ConfigItem DEFAULT.a <NotSet>>'


def test_creates_config_from_dot_notation():
    c = ConfigItem('a.b')
    assert c.section == 'a'
    assert c.option == 'b'


def test_bool_config_preserves_raw_str_value_used_to_set_it():
    c = ConfigItem('a.b', type=bool, default=False)
    assert c.value is False

    assert not c
    assert str(c) == 'False'
    assert c.value is False

    c.value = 'False'
    assert not c
    assert str(c) == 'False'
    assert c.value is False

    c.value = 'no'
    assert not c
    assert str(c) == 'no'
    assert c.value is False

    c.value = '0'
    assert not c
    assert str(c) == '0'
    assert c.value is False

    c.value = '1'
    assert c
    assert str(c) == '1'
    assert c.value is True

    c.reset()
    assert not c
    assert c.value is False

    c.value = 'yes'
    assert str(c) == 'yes'
    assert c.value is True


def test_cannot_set_nonexistent_config():
    c = ConfigItem('not', 'managed')
    c.value = '23'
    assert c.value == '23'

    d = ConfigItem('actually', 'managed', exists=False)
    with pytest.raises(RuntimeError):
        d.value = '23'


def test_repr():
    assert repr(ConfigItem('this.is', 'me', default='yes')) == '<ConfigItem this.is.me yes>'
    assert repr(ConfigItem('this.is', 'me')) == '<ConfigItem this.is.me <NotSet>>'


def test_nonexistent_item_visible_in_repr():
    c = ConfigItem('non', 'ex.is', 'tent', exists=False)
    assert repr(c) == '<ConfigItem non.ex.is.tent <NonExistent>>'