import os
from pathlib import Path
from pydantic import BaseModel
from saigon.utils import (
    get_file_dir, parse_comma_separated_list, NameValueItem,
    EnvironmentRepository, Environment, NodeEntity
)


def test_get_file_dir():
    assert get_file_dir("/tmp/test.txt") == Path("/tmp").resolve()


def test_parse_comma_separated_list():
    assert parse_comma_separated_list("a, b, c") == ["a", "b", "c"]
    assert parse_comma_separated_list("  a  ,b  ") == ["a", "b"]
    assert parse_comma_separated_list("") == []
    assert parse_comma_separated_list("   ") == []


def test_name_value_item():
    item = NameValueItem(name="k", value=1)
    assert item.name == "k"
    assert item.value == 1


class TestEnvironmentRepository:
    def test_get_by_name_bool(self, monkeypatch):
        repo = EnvironmentRepository()
        monkeypatch.setenv("TEST_BOOL", "true")
        assert repo.get_by_name(bool, "TEST_BOOL") is True

        monkeypatch.setenv("TEST_BOOL_FALSE", "false")
        assert repo.get_by_name(bool, "TEST_BOOL_FALSE") is False

        monkeypatch.delenv("TEST_BOOL", raising=False)
        assert repo.get_by_name(bool, "TEST_BOOL") is None

    def test_get_by_name_list(self, monkeypatch):
        repo = EnvironmentRepository()
        monkeypatch.setenv("TEST_LIST", "a,b,c")
        from typing import List
        assert repo.get_by_name(List, "TEST_LIST") == ["a", "b", "c"]

    def test_set_by_name(self, monkeypatch):
        repo = EnvironmentRepository()
        repo.set_by_name("NEW_VAR", "val")
        assert os.environ["NEW_VAR"] == "val"

        repo.set_by_name("NEW_VAR", None)
        assert "NEW_VAR" not in os.environ


class TestEnvironment:
    class MyEnv(Environment):
        VAR1: str
        VAR2: int = 10

    def test_environment_loading(self, monkeypatch):
        monkeypatch.setenv("VAR1", "env_val")
        env = self.MyEnv()
        assert env.VAR1 == "env_val"
        assert env.VAR2 == 10

        env2 = self.MyEnv(VAR1="override")
        assert env2.VAR1 == "override"

    def test_setvars(self, monkeypatch):
        env = self.MyEnv(VAR1="val1", VAR2=20)
        env.setvars()
        assert os.environ["VAR1"] == "val1"
        assert os.environ["VAR2"] == "20"


class TestNodeEntity:
    class Item(BaseModel):
        id: str
        name: str

    def test_node_entity_structure(self):
        root_item = self.Item(id="1", name="root")
        child_item = self.Item(id="2", name="child")

        root_node = NodeEntity(entity=root_item)
        child_node = NodeEntity(entity=child_item)

        root_node.add_child(child_node)

        assert child_node.parent == root_node
        assert child_node in root_node.children

    def test_traverse(self):
        root = NodeEntity(entity=self.Item(id="1", name="root"))
        c1 = NodeEntity(entity=self.Item(id="2", name="c1"))
        root.add_child(c1)

        visited = []
        root.traverse(lambda n: visited.append(n.entity.name))
        assert visited == ["root", "c1"]

    def test_serialization(self):
        root = NodeEntity(entity=self.Item(id="1", name="root"))
        child = NodeEntity(entity=self.Item(id="2", name="child"))
        root.add_child(child)

        # Test custom parent serializer
        dump = child.model_dump()
        assert dump['parent'] == "root"
