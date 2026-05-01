"""Unit tests for the DataCompositionSchema parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_1c.domain.composition import DataSetKind
from mcp_1c.engines.composition.parser import CompositionParser

SAMPLE_SKD = """<?xml version="1.0" encoding="UTF-8"?>
<DataCompositionSchema xmlns="http://v8.1c.ru/8.1/data-composition-system/schema">
  <Title>Отчёт по продажам</Title>
  <DataSet>
    <Name>ОсновнойНаборДанных</Name>
    <Type>DataSetQuery</Type>
    <Query>ВЫБРАТЬ Контрагент, СУММА(Сумма) ИЗ РегистрНакопления.Продажи СГРУППИРОВАТЬ ПО Контрагент</Query>
    <Field>
      <DataPath>Контрагент</DataPath>
      <Title>Контрагент</Title>
      <Type><Type>СправочникСсылка.Контрагенты</Type></Type>
      <Role>Dimension</Role>
    </Field>
    <Field>
      <DataPath>Сумма</DataPath>
      <Title>Сумма продаж</Title>
      <Type><Type>Число</Type></Type>
      <Role>Resource</Role>
    </Field>
  </DataSet>
  <Parameter>
    <Name>НачалоПериода</Name>
    <Title>Начало периода</Title>
    <ValueType><Type>Дата</Type></ValueType>
  </Parameter>
  <Parameter>
    <Name>КонецПериода</Name>
    <Title>Конец периода</Title>
    <ValueType><Type>Дата</Type></ValueType>
    <AvailableForUser>true</AvailableForUser>
  </Parameter>
  <TotalField>
    <DataPath>Сумма</DataPath>
    <Expression>Сумма(Сумма)</Expression>
    <Title>Итого</Title>
  </TotalField>
  <CalculatedField>
    <DataPath>СредняяСумма</DataPath>
    <Title>Средняя сумма</Title>
    <Expression>Сумма / Количество</Expression>
  </CalculatedField>
  <SettingsVariants>
    <SettingsVariant>
      <Name>Основной</Name>
      <Title>Основной вариант</Title>
    </SettingsVariant>
    <SettingsVariant>
      <Name>ПоКонтрагентам</Name>
      <Title>Группировка по контрагентам</Title>
    </SettingsVariant>
  </SettingsVariants>
</DataCompositionSchema>
"""


@pytest.fixture
def schema_path(tmp_path: Path) -> Path:
    p = tmp_path / "MainSchema.xml"
    p.write_text(SAMPLE_SKD, encoding="utf-8")
    return p


def test_parses_metadata(schema_path: Path) -> None:
    parser = CompositionParser()
    s = parser.parse(schema_path, "Report", "Продажи")
    assert s.title == "Отчёт по продажам"
    assert s.full_name == "Report.Продажи.MainSchema"


def test_parses_data_set(schema_path: Path) -> None:
    parser = CompositionParser()
    s = parser.parse(schema_path, "Report", "Продажи")
    assert len(s.data_sets) == 1
    ds = s.data_sets[0]
    assert ds.name == "ОсновнойНаборДанных"
    assert ds.kind == DataSetKind.QUERY
    assert "ВЫБРАТЬ" in ds.query_text
    assert {f.name for f in ds.fields} == {"Контрагент", "Сумма"}


def test_parses_parameters(schema_path: Path) -> None:
    parser = CompositionParser()
    s = parser.parse(schema_path, "Report", "Продажи")
    names = [p.name for p in s.parameters]
    assert "НачалоПериода" in names and "КонецПериода" in names
    end = next(p for p in s.parameters if p.name == "КонецПериода")
    assert end.title == "Конец периода"


def test_parses_resources(schema_path: Path) -> None:
    parser = CompositionParser()
    s = parser.parse(schema_path, "Report", "Продажи")
    assert any(r.field == "Сумма" for r in s.resources)


def test_parses_calculated_fields(schema_path: Path) -> None:
    parser = CompositionParser()
    s = parser.parse(schema_path, "Report", "Продажи")
    calc = next((f for f in s.fields if f.name == "СредняяСумма"), None)
    assert calc is not None
    assert calc.expression == "Сумма / Количество"


def test_parses_settings_variants(schema_path: Path) -> None:
    parser = CompositionParser()
    s = parser.parse(schema_path, "Report", "Продажи")
    names = [v.name for v in s.settings]
    assert "Основной" in names and "ПоКонтрагентам" in names
