from apps.transcription.partial_json import parse_partial_json_object as parse


def test_complete_object_is_parsed_as_is():
    assert parse('{"a": 1, "b": [1, 2]}') == {"a": 1, "b": [1, 2]}


def test_text_around_the_json_is_ignored():
    assert parse('Aquí va:\n```json\n{"a": 1}\n```') == {"a": 1}


def test_open_containers_are_closed():
    assert parse('{"a": {"b": [1, 2') == {"a": {"b": [1, 2]}}


def test_unfinished_string_keeps_what_was_written():
    assert parse('{"resumen": "paciente estable, sin fi') == {"resumen": "paciente estable, sin fi"}


def test_dangling_key_or_token_is_dropped():
    assert parse('{"a": 1, "b":') == {"a": 1}
    assert parse('{"a": 1, "b": tr') == {"a": 1}
    assert parse('{"a": 1, "b"') == {"a": 1}


def test_commas_and_brackets_inside_strings_do_not_confuse_it():
    assert parse('{"a": "x, y] }", "b": 2') == {"a": "x, y] }", "b": 2}


def test_nothing_to_read_yet():
    assert parse("") is None
    assert parse("Claro, ahí va el registro") is None
    assert parse("{") == {}
