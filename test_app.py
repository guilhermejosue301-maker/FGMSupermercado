import importlib


def test_importacao_app():
    modulo = importlib.import_module("app")
    assert modulo is not None