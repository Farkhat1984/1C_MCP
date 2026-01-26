# Публикация MCP-1C

## Содержание

- [GitHub Repository](#github-repository)
- [GitHub Release](#github-release)
- [PyPI](#pypi)

---

## GitHub Repository

### Инициализация Git

```bash
# Инициализировать репозиторий
git init

# Добавить файлы
git add .

# Первый коммит
git commit -m "Initial commit: MCP-1C v0.1.0"
```

### Создание репозитория на GitHub

1. Создайте новый репозиторий на https://github.com/new
2. Имя: `mcp-1c`
3. Описание: `MCP Server for 1C:Enterprise platform`
4. Публичный/Приватный: на ваш выбор

### Подключение к GitHub

```bash
# Добавить remote
git remote add origin https://github.com/YOUR_USERNAME/mcp-1c.git

# Переименовать ветку в main
git branch -M main

# Пуш в GitHub
git push -u origin main
```

### Настройка GitHub Secrets

Для автоматической публикации добавьте секреты:

1. Перейдите в Settings → Secrets and variables → Actions
2. Добавьте:
   - `PYPI_TOKEN` — токен PyPI для публикации

---

## GitHub Release

### Создание релиза через UI

1. Перейдите в репозиторий → Releases → Create a new release
2. Tag: `v0.1.0` (создастся автоматически)
3. Target: `main`
4. Title: `v0.1.0 - Initial Release`
5. Description: скопируйте из CHANGELOG.md
6. Прикрепите артефакты из `dist/`:
   - `mcp_1c-0.1.0.tar.gz`
   - `mcp_1c-0.1.0-py3-none-any.whl`
7. Нажмите "Publish release"

### Создание релиза через CLI

```bash
# Установите GitHub CLI
# Windows: winget install GitHub.cli
# Mac: brew install gh

# Авторизация
gh auth login

# Создание тега
git tag -a v0.1.0 -m "Release v0.1.0"
git push origin v0.1.0

# Создание релиза
gh release create v0.1.0 \
  --title "v0.1.0 - Initial Release" \
  --notes-file CHANGELOG.md \
  dist/mcp_1c-0.1.0.tar.gz \
  dist/mcp_1c-0.1.0-py3-none-any.whl
```

### Автоматический релиз при публикации тега

При создании GitHub Release с тегом `v*`:
1. CI workflow прогонит тесты
2. Publish workflow соберёт пакет
3. Пакет автоматически опубликуется в PyPI

---

## PyPI

### Подготовка

### 1. Установите инструменты сборки

```bash
pip install build twine
```

### 2. Создайте аккаунт PyPI

- Зарегистрируйтесь на https://pypi.org
- Создайте API токен в Account Settings → API tokens
- Сохраните токен (он показывается только один раз)

### 3. Настройте credentials

Создайте файл `~/.pypirc`:

```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-your-token-here

[testpypi]
username = __token__
password = pypi-your-testpypi-token-here
```

## Сборка

```bash
# Очистить предыдущие сборки
rm -rf dist/ build/ *.egg-info

# Собрать пакет
python -m build
```

Результат в директории `dist/`:
- `mcp_1c-0.1.0.tar.gz` — source distribution
- `mcp_1c-0.1.0-py3-none-any.whl` — wheel

## Публикация

### Тестовая публикация (TestPyPI)

Сначала опубликуйте на TestPyPI для проверки:

```bash
# Загрузить на TestPyPI
python -m twine upload --repository testpypi dist/*

# Проверить установку с TestPyPI
pip install --index-url https://test.pypi.org/simple/ mcp-1c
```

### Продакшн публикация (PyPI)

После проверки публикуйте на PyPI:

```bash
python -m twine upload dist/*
```

## Проверка

```bash
# Установка из PyPI
pip install mcp-1c

# Проверка версии
python -c "import mcp_1c; print(mcp_1c.__version__)"

# Запуск
mcp-1c --help
```

## Обновление версии

1. Обновите версию в `pyproject.toml`:
   ```toml
   version = "0.2.0"
   ```

2. Обновите `CHANGELOG.md`

3. Создайте git tag:
   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```

4. Соберите и опубликуйте:
   ```bash
   python -m build
   python -m twine upload dist/*
   ```

## Автоматическая публикация (GitHub Actions)

Для автоматической публикации при создании релиза добавьте в `.github/workflows/publish.yml`:

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install build twine

      - name: Build package
        run: python -m build

      - name: Publish to PyPI
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_TOKEN }}
        run: python -m twine upload dist/*
```

Добавьте `PYPI_TOKEN` в GitHub Secrets:
1. Settings → Secrets and variables → Actions
2. New repository secret: `PYPI_TOKEN` = ваш PyPI API токен

## Ссылки

- PyPI: https://pypi.org/project/mcp-1c/
- TestPyPI: https://test.pypi.org/project/mcp-1c/
- Документация Twine: https://twine.readthedocs.io/
