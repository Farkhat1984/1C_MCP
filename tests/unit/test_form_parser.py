"""Unit tests for the FormParser."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_1c.domain.form import FormElementKind
from mcp_1c.engines.forms.parser import FormParser

CONFIGURATOR_FORM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">
  <Form>
    <Properties>
      <Name>ФормаСписка</Name>
      <Title><v lang="ru">Список товаров</v></Title>
      <Purpose>ItemListForm</Purpose>
    </Properties>
    <Attributes>
      <Attribute>
        <Name>Список</Name>
        <Title><v lang="ru">Список</v></Title>
        <Type><Type>DynamicList</Type></Type>
        <MainAttribute>true</MainAttribute>
        <SaveData>false</SaveData>
      </Attribute>
      <Attribute>
        <Name>ТекущийФильтр</Name>
        <Type><Type>String</Type></Type>
      </Attribute>
    </Attributes>
    <Commands>
      <Command>
        <Name>ОбновитьСписок</Name>
        <Title><v lang="ru">Обновить</v></Title>
        <Action>ОбновитьСписокНаСервере</Action>
        <Use>ForBoth</Use>
      </Command>
    </Commands>
    <EventHandlers>
      <EventHandler>
        <Event>OnCreateAtServer</Event>
        <Procedure>ПриСозданииНаСервере</Procedure>
      </EventHandler>
    </EventHandlers>
    <ChildItems>
      <Group name="ШапкаФормы">
        <Title><v lang="ru">Шапка</v></Title>
        <ChildItems>
          <InputField name="ПолеФильтр" DataPath="ТекущийФильтр">
            <Title><v lang="ru">Фильтр</v></Title>
            <EventHandlers>
              <EventHandler>
                <Event>OnChange</Event>
                <Procedure>ПолеФильтрПриИзменении</Procedure>
              </EventHandler>
            </EventHandlers>
          </InputField>
          <Button name="КнопкаПоиск">
            <Title><v lang="ru">Найти</v></Title>
          </Button>
        </ChildItems>
      </Group>
      <Table name="ТаблицаСписок" DataPath="Список"/>
    </ChildItems>
    <CommandInterface>
      <NavigationPanel>
        <Item><Name>ОбновитьСписок</Name></Item>
      </NavigationPanel>
    </CommandInterface>
  </Form>
</MetaDataObject>
"""


@pytest.fixture
def configurator_form_path(tmp_path: Path) -> Path:
    p = tmp_path / "Form.xml"
    p.write_text(CONFIGURATOR_FORM_XML, encoding="utf-8")
    return p


def test_parses_form_metadata(configurator_form_path: Path) -> None:
    parser = FormParser()
    s = parser.parse(configurator_form_path, "Catalog", "Товары", "ФормаСписка")

    assert s.title == "Список товаров"
    assert s.purpose == "ItemListForm"
    assert s.full_name == "Catalog.Товары.Form.ФормаСписка"


def test_parses_attributes(configurator_form_path: Path) -> None:
    parser = FormParser()
    s = parser.parse(configurator_form_path, "Catalog", "Товары", "ФормаСписка")

    names = [a.name for a in s.attributes]
    assert "Список" in names and "ТекущийФильтр" in names

    main = next(a for a in s.attributes if a.name == "Список")
    assert main.main is True
    assert main.type == "DynamicList"
    assert main.title == "Список"


def test_parses_commands(configurator_form_path: Path) -> None:
    parser = FormParser()
    s = parser.parse(configurator_form_path, "Catalog", "Товары", "ФормаСписка")

    assert len(s.commands) == 1
    cmd = s.commands[0]
    assert cmd.name == "ОбновитьСписок"
    assert cmd.action == "ОбновитьСписокНаСервере"
    assert cmd.use == "ForBoth"


def test_parses_form_level_handlers(configurator_form_path: Path) -> None:
    parser = FormParser()
    s = parser.parse(configurator_form_path, "Catalog", "Товары", "ФормаСписка")

    events = {(h.event, h.procedure) for h in s.handlers}
    assert ("OnCreateAtServer", "ПриСозданииНаСервере") in events


def test_parses_element_tree(configurator_form_path: Path) -> None:
    parser = FormParser()
    s = parser.parse(configurator_form_path, "Catalog", "Товары", "ФормаСписка")

    # Root has 2 immediate children: ШапкаФормы (Group), ТаблицаСписок (Table)
    children = s.elements.children
    names = [c.name for c in children]
    assert "ШапкаФормы" in names
    assert "ТаблицаСписок" in names

    table = next(c for c in children if c.name == "ТаблицаСписок")
    assert table.kind == FormElementKind.TABLE
    assert table.data_path == "Список"

    header = next(c for c in children if c.name == "ШапкаФормы")
    assert header.kind == FormElementKind.GROUP
    inner_names = {c.name for c in header.children}
    assert "ПолеФильтр" in inner_names and "КнопкаПоиск" in inner_names


def test_parses_element_handlers(configurator_form_path: Path) -> None:
    parser = FormParser()
    s = parser.parse(configurator_form_path, "Catalog", "Товары", "ФормаСписка")

    header = next(c for c in s.elements.children if c.name == "ШапкаФормы")
    field = next(c for c in header.children if c.name == "ПолеФильтр")
    assert any(
        h.event == "OnChange" and h.procedure == "ПолеФильтрПриИзменении"
        for h in field.handlers
    )


def test_parses_command_interface(configurator_form_path: Path) -> None:
    parser = FormParser()
    s = parser.parse(configurator_form_path, "Catalog", "Товары", "ФормаСписка")
    assert "ОбновитьСписок" in s.command_interface.navigation_panel


def test_missing_file_raises(tmp_path: Path) -> None:
    parser = FormParser()
    with pytest.raises(FileNotFoundError):
        parser.parse(tmp_path / "missing.xml", "Catalog", "X", "Form")
