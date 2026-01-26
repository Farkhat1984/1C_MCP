# Техническое задание: MCP-сервер для 1С:Предприятие

## 1. Общие сведения

### 1.1. Наименование продукта
**mcp-1c** — универсальный MCP-сервер для работы с конфигурациями 1С:Предприятие

### 1.2. Назначение
Предоставить Claude Code (и другим LLM-агентам) полноценный инструментарий для работы с любыми конфигурациями 1С:Предприятие — типовыми, отраслевыми и самописными.

### 1.3. Целевая аудитория
- Разработчики 1С, использующие AI-ассистенты
- Команды внедрения типовых решений
- Консультанты по настройке 1С

### 1.4. Ключевые требования
- Работа с любой конфигурацией без предварительной настройки
- Не требует RAG — использует прямой доступ к файлам и индексацию
- Работа с выгрузкой конфигурации в XML (формат EDT/Конфигуратора)
- Опциональное подключение к работающей базе через COM/HTTP

---

## 2. Архитектура системы

### 2.1. Общая схема

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Claude Code                                 │
│                         (или другой MCP-клиент)                         │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │ MCP Protocol (stdio/SSE)
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           mcp-1c Server                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐             │
│  │   Metadata     │  │     Code       │  │    Runtime     │             │
│  │    Engine      │  │    Engine      │  │    Engine      │             │
│  ├────────────────┤  ├────────────────┤  ├────────────────┤             │
│  │ • XML Parser   │  │ • BSL Parser   │  │ • COM Connector│             │
│  │ • Indexer      │  │ • Dependency   │  │ • HTTP Client  │             │
│  │ • Cache        │  │   Analyzer     │  │ • OneScript    │             │
│  │ • Search       │  │ • Generator    │  │   Runner       │             │
│  └────────────────┘  └────────────────┘  └────────────────┘             │
│                                                                          │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐             │
│  │   Template     │  │     Query      │  │   Knowledge    │             │
│  │    Engine      │  │    Engine      │  │     Base       │             │
│  ├────────────────┤  ├────────────────┤  ├────────────────┤             │
│  │ • Layout Parse │  │ • Query Parser │  │ • Platform API │             │
│  │ • Print Forms  │  │ • Optimizer    │  │ • BSL Syntax   │             │
│  │ • Parameters   │  │ • Generator    │  │ • Patterns     │             │
│  └────────────────┘  └────────────────┘  └────────────────┘             │
│                                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│                         Configuration Index                              │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  SQLite / LevelDB / In-Memory                                    │    │
│  │  • Objects Index    • Modules Index    • References Graph        │    │
│  │  • Synonyms Map     • Full-Text Index  • Call Graph              │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           Data Sources                                   │
├──────────────────┬──────────────────┬───────────────────────────────────┤
│   XML Files      │   BSL Files      │   1C Platform (optional)          │
│   (Metadata)     │   (Code)         │   (COM/HTTP)                      │
└──────────────────┴──────────────────┴───────────────────────────────────┘
```

### 2.2. Компоненты системы

#### 2.2.1. Metadata Engine
Отвечает за парсинг и индексацию метаданных конфигурации.

**Функции:**
- Парсинг XML-файлов метаданных
- Построение индекса объектов конфигурации
- Кэширование метаданных в памяти и на диске
- Инкрементальное обновление индекса при изменении файлов
- Полнотекстовый поиск по именам и синонимам

**Поддерживаемые типы метаданных:**
| Английское имя | Русское название | Описание |
|----------------|------------------|----------|
| CommonModules | Общие модули | Серверные и клиентские модули |
| Catalogs | Справочники | Справочная информация |
| Documents | Документы | Хозяйственные операции |
| DocumentJournals | Журналы документов | Группировка документов |
| Enums | Перечисления | Фиксированные списки значений |
| Reports | Отчёты | Формирование отчётности |
| DataProcessors | Обработки | Сервисные функции |
| InformationRegisters | Регистры сведений | Хранение данных |
| AccumulationRegisters | Регистры накопления | Учёт оборотов и остатков |
| CalculationRegisters | Регистры расчёта | Периодические расчёты |
| ChartsOfCalculationTypes | Планы видов расчёта | Виды начислений/удержаний |
| ChartsOfCharacteristicTypes | Планы видов характеристик | Дополнительные реквизиты |
| ChartsOfAccounts | Планы счетов | Бухгалтерские счета |
| BusinessProcesses | Бизнес-процессы | Маршрутизация задач |
| Tasks | Задачи | Задачи пользователей |
| ExchangePlans | Планы обмена | Синхронизация данных |
| Constants | Константы | Настройки системы |
| Subsystems | Подсистемы | Структура конфигурации |
| CommonForms | Общие формы | Переиспользуемые формы |
| CommonCommands | Общие команды | Глобальные команды |
| CommonTemplates | Общие макеты | Общие шаблоны печати |
| CommonPictures | Общие картинки | Изображения |
| SessionParameters | Параметры сеанса | Данные сессии |
| Roles | Роли | Права доступа |
| FunctionalOptions | Функциональные опции | Включение/отключение функций |
| ScheduledJobs | Регламентные задания | Фоновые задачи |
| EventSubscriptions | Подписки на события | Триггеры |
| HTTPServices | HTTP-сервисы | REST API |
| WebServices | Web-сервисы | SOAP API |
| XDTOPackages | XDTO-пакеты | XML-схемы |
| DefinedTypes | Определяемые типы | Составные типы |

#### 2.2.2. Code Engine
Отвечает за работу с исходным кодом BSL.

**Функции:**
- Парсинг BSL-кода (построение AST)
- Анализ зависимостей между модулями
- Поиск определений и использований
- Генерация кода по шаблонам
- Интеграция с BSL Language Server

**Анализируемые элементы кода:**
- Процедуры и функции (сигнатуры, параметры, экспорт)
- Вызовы методов (локальные, модулей, платформы)
- Обращения к метаданным (Справочники.*, Документы.*)
- Запросы (встроенные в код)
- Директивы компиляции (#Если, #Область)
- Аннотации (&НаСервере, &НаКлиенте)

#### 2.2.3. Runtime Engine
Отвечает за выполнение кода и получение данных из работающей базы.

**Функции:**
- Подключение к базе через COM (Windows)
- Подключение через HTTP-сервисы
- Выполнение произвольных запросов
- Вызов методов конфигурации
- Получение данных объектов

**Режимы работы:**
1. **Offline** — только файлы, без подключения к базе
2. **COM** — подключение через V83.COMConnector (Windows)
3. **HTTP** — подключение через HTTP-сервис в базе
4. **OneScript** — выполнение через OneScript runtime

#### 2.2.4. Template Engine
Отвечает за работу с макетами и печатными формами.

**Функции:**
- Парсинг структуры табличных документов
- Извлечение областей и параметров
- Анализ связей макет-код
- Генерация кода печатных форм

#### 2.2.5. Query Engine
Отвечает за работу с запросами 1С.

**Функции:**
- Парсинг синтаксиса запросов
- Валидация запросов
- Анализ используемых таблиц
- Оптимизация запросов
- Генерация запросов по описанию

#### 2.2.6. Knowledge Base
Статическая база знаний, не зависящая от конфигурации.

**Содержимое:**
- Методы и свойства платформы 8.3.x
- Глобальный контекст
- Синтаксис языка BSL
- Шаблоны кода (patterns)
- Типичные ошибки и их решения

---

## 3. Спецификация MCP Tools

### 3.1. Группа: metadata — Работа с метаданными

#### 3.1.1. metadata.init
Инициализация индекса конфигурации.

```typescript
interface MetadataInitParams {
  path: string;                    // Путь к корню выгрузки
  force?: boolean;                 // Пересоздать индекс
  watch?: boolean;                 // Следить за изменениями
}

interface MetadataInitResult {
  success: boolean;
  objectsCount: number;            // Количество объектов
  modulesCount: number;            // Количество модулей
  indexPath: string;               // Путь к индексу
  configurationName: string;       // Имя конфигурации
  configurationVersion: string;    // Версия
  platformVersion: string;         // Версия платформы
  elapsed: number;                 // Время в мс
}
```

#### 3.1.2. metadata.list
Получить список объектов метаданных.

```typescript
interface MetadataListParams {
  type: MetadataType;              // Тип объектов
  filter?: string;                 // Фильтр по имени (regex)
  subsystem?: string;              // Фильтр по подсистеме
  limit?: number;                  // Ограничение количества
  offset?: number;                 // Смещение
}

interface MetadataListResult {
  objects: MetadataObjectInfo[];
  total: number;
}

interface MetadataObjectInfo {
  name: string;                    // Имя объекта
  synonym: string;                 // Синоним (русское название)
  type: MetadataType;              // Тип
  fullPath: string;                // Полный путь в конфигурации
  hasModule: boolean;              // Есть модуль объекта
  hasManagerModule: boolean;       // Есть модуль менеджера
  formsCount: number;              // Количество форм
  templatesCount: number;          // Количество макетов
  comment: string;                 // Комментарий
}
```

#### 3.1.3. metadata.get
Получить полную информацию об объекте.

```typescript
interface MetadataGetParams {
  object: string;                  // Имя или путь объекта
                                   // "Документ.БольничныйЛист" или
                                   // "Documents/БольничныйЛист"
}

interface MetadataGetResult {
  name: string;
  synonym: string;
  type: MetadataType;
  uuid: string;
  comment: string;

  // Структура
  attributes: AttributeInfo[];
  tabularSections: TabularSectionInfo[];

  // Модули
  modules: ModuleInfo[];

  // Формы
  forms: FormInfo[];

  // Макеты
  templates: TemplateInfo[];

  // Команды
  commands: CommandInfo[];

  // Специфичные для типа
  registers?: RegisterInfo[];       // Для документов — регистры движений
  owners?: string[];                // Для подчинённых справочников
  characteristics?: CharacteristicInfo[]; // Для планов видов характеристик
  calculationTypes?: CalculationTypeInfo[]; // Для планов видов расчёта

  // Связи
  references: ReferenceInfo[];      // Ссылки на другие объекты
  referencedBy: ReferenceInfo[];    // Кто ссылается на этот объект
}

interface AttributeInfo {
  name: string;
  synonym: string;
  type: TypeDescription;
  mandatory: boolean;
  indexing: string;
  fillChecking: string;
  comment: string;
}

interface TabularSectionInfo {
  name: string;
  synonym: string;
  attributes: AttributeInfo[];
}

interface ModuleInfo {
  type: "ObjectModule" | "ManagerModule" | "RecordSetModule" | "FormModule";
  path: string;
  linesCount: number;
  procedures: ProcedureInfo[];
  functions: FunctionInfo[];
}

interface FormInfo {
  name: string;
  synonym: string;
  formType: "Managed" | "Ordinary";
  path: string;
  hasModule: boolean;
}

interface TemplateInfo {
  name: string;
  synonym: string;
  templateType: "SpreadsheetDocument" | "TextDocument" | "BinaryData" | "HTMLDocument";
  path: string;
}
```

#### 3.1.4. metadata.search
Поиск объектов по имени или синониму.

```typescript
interface MetadataSearchParams {
  query: string;                   // Поисковый запрос
  types?: MetadataType[];          // Ограничить типами
  searchIn?: ("name" | "synonym" | "comment")[]; // Где искать
  limit?: number;
}

interface MetadataSearchResult {
  results: MetadataSearchHit[];
  total: number;
}

interface MetadataSearchHit {
  object: MetadataObjectInfo;
  matchedField: string;
  matchedText: string;
  score: number;
}
```

#### 3.1.5. metadata.tree
Получить дерево подсистем.

```typescript
interface MetadataTreeParams {
  root?: string;                   // Корневая подсистема (или вся конфигурация)
  depth?: number;                  // Глубина вложенности
  includeObjects?: boolean;        // Включить объекты в узлы
}

interface MetadataTreeResult {
  subsystems: SubsystemNode[];
}

interface SubsystemNode {
  name: string;
  synonym: string;
  path: string;
  children: SubsystemNode[];
  objects?: MetadataObjectInfo[];
}
```

#### 3.1.6. metadata.attributes
Быстрое получение реквизитов объекта.

```typescript
interface MetadataAttributesParams {
  object: string;
  includeStandard?: boolean;       // Включить стандартные реквизиты
  includeTabular?: boolean;        // Включить ТЧ
}

interface MetadataAttributesResult {
  standardAttributes: AttributeInfo[];
  attributes: AttributeInfo[];
  tabularSections: TabularSectionInfo[];
}
```

#### 3.1.7. metadata.forms
Получить формы объекта.

```typescript
interface MetadataFormsParams {
  object: string;
}

interface MetadataFormsResult {
  forms: FormDetailInfo[];
}

interface FormDetailInfo extends FormInfo {
  mainAttribute: string;           // Основной реквизит
  attributes: FormAttributeInfo[]; // Реквизиты формы
  commands: FormCommandInfo[];     // Команды формы
  elements: FormElementInfo[];     // Элементы (кратко)
}
```

#### 3.1.8. metadata.templates
Получить макеты объекта.

```typescript
interface MetadataTemplatesParams {
  object: string;
}

interface MetadataTemplatesResult {
  templates: TemplateDetailInfo[];
}

interface TemplateDetailInfo extends TemplateInfo {
  areas: TemplateAreaInfo[];       // Области макета
  parameters: string[];            // Параметры [Параметр]
}

interface TemplateAreaInfo {
  name: string;
  type: "Rows" | "Columns" | "Rectangle";
  top: number;
  left: number;
  bottom: number;
  right: number;
}
```

#### 3.1.9. metadata.registers
Получить регистры, связанные с документом.

```typescript
interface MetadataRegistersParams {
  document: string;
}

interface MetadataRegistersResult {
  accumulationRegisters: RegisterMovementInfo[];
  informationRegisters: RegisterMovementInfo[];
  calculationRegisters: RegisterMovementInfo[];
  accountingRegisters: RegisterMovementInfo[];
}

interface RegisterMovementInfo {
  name: string;
  synonym: string;
  path: string;
  recordType?: "Expense" | "Receipt" | "ExpenseAndReceipt"; // Для накопления
  dimensions: AttributeInfo[];
  resources: AttributeInfo[];
  attributes: AttributeInfo[];
}
```

#### 3.1.10. metadata.references
Получить ссылки объекта.

```typescript
interface MetadataReferencesParams {
  object: string;
  direction: "outgoing" | "incoming" | "both";
  depth?: number;                  // Глубина графа (1 = прямые связи)
}

interface MetadataReferencesResult {
  outgoing: ReferenceInfo[];       // На кого ссылается
  incoming: ReferenceInfo[];       // Кто ссылается
}

interface ReferenceInfo {
  object: string;                  // Имя объекта
  type: MetadataType;
  field: string;                   // Поле-ссылка
  fieldPath: string;               // Путь к полю (для ТЧ)
}
```

---

### 3.2. Группа: code — Работа с кодом

#### 3.2.1. code.module
Получить код модуля.

```typescript
interface CodeModuleParams {
  object: string;                  // Объект метаданных
  moduleType: ModuleType;          // Тип модуля
  // или
  path?: string;                   // Прямой путь к файлу
}

type ModuleType =
  | "ObjectModule"                 // Модуль объекта
  | "ManagerModule"                // Модуль менеджера
  | "FormModule"                   // Модуль формы (нужен formName)
  | "RecordSetModule"              // Модуль набора записей
  | "CommandModule";               // Модуль команды

interface CodeModuleResult {
  path: string;
  content: string;
  encoding: string;
  linesCount: number;
  procedures: ProcedureSignature[];
  functions: FunctionSignature[];
  regions: RegionInfo[];
}

interface ProcedureSignature {
  name: string;
  line: number;
  endLine: number;
  params: ParameterInfo[];
  export: boolean;
  directive: string;               // "&НаСервере", "&НаКлиенте" и т.д.
  isEventHandler: boolean;
  comment: string;                 // Документирующий комментарий
}

interface FunctionSignature extends ProcedureSignature {
  returnType?: string;             // Из комментария, если есть
}

interface ParameterInfo {
  name: string;
  byValue: boolean;                // Знач
  defaultValue?: string;
  type?: string;                   // Из комментария
}

interface RegionInfo {
  name: string;
  startLine: number;
  endLine: number;
  nested: RegionInfo[];
}
```

#### 3.2.2. code.procedure
Получить код конкретной процедуры/функции.

```typescript
interface CodeProcedureParams {
  object: string;
  moduleType: ModuleType;
  procedureName: string;
  formName?: string;               // Для модуля формы
}

interface CodeProcedureResult {
  signature: ProcedureSignature | FunctionSignature;
  code: string;
  startLine: number;
  endLine: number;
  calls: CallInfo[];               // Вызовы внутри
  variables: VariableInfo[];       // Локальные переменные
}

interface CallInfo {
  target: string;                  // Куда вызов (модуль.метод или метод)
  line: number;
  isAsync: boolean;
  resolved?: string;               // Путь к определению
}

interface VariableInfo {
  name: string;
  line: number;
  type?: string;                   // Выведенный тип
}
```

#### 3.2.3. code.resolve
Найти определение по имени.

```typescript
interface CodeResolveParams {
  name: string;                    // "ЗарплатаКадры.ПроверитьДату" или просто "ПроверитьДату"
  context?: string;                // Контекст (файл, откуда вызов)
  line?: number;                   // Строка в контексте
}

interface CodeResolveResult {
  found: boolean;
  definitions: DefinitionInfo[];
}

interface DefinitionInfo {
  type: "Procedure" | "Function" | "Variable" | "Parameter" | "MetadataObject";
  name: string;
  path: string;                    // Путь к файлу
  line: number;
  signature?: string;
  export: boolean;
  module?: string;                 // Имя модуля
  object?: string;                 // Имя объекта метаданных
}
```

#### 3.2.4. code.usages
Найти все использования.

```typescript
interface CodeUsagesParams {
  name: string;                    // Имя для поиска
  scope?: "all" | "module" | "object"; // Область поиска
  context?: string;                // Контекст
  includeComments?: boolean;       // Искать в комментариях
}

interface CodeUsagesResult {
  usages: UsageInfo[];
  total: number;
}

interface UsageInfo {
  path: string;
  line: number;
  column: number;
  lineContent: string;
  usageType: "Call" | "Reference" | "Assignment" | "Parameter";
  context: string;                 // Имя процедуры/функции
}
```

#### 3.2.5. code.dependencies
Получить граф зависимостей.

```typescript
interface CodeDependenciesParams {
  object: string;                  // Объект или модуль
  direction: "calls" | "calledBy" | "both";
  depth?: number;                  // Глубина графа
  includeTypes?: string[];         // Типы объектов для включения
}

interface CodeDependenciesResult {
  nodes: DependencyNode[];
  edges: DependencyEdge[];
}

interface DependencyNode {
  id: string;
  name: string;
  type: string;
  path: string;
}

interface DependencyEdge {
  from: string;
  to: string;
  type: "calls" | "uses" | "references";
  count: number;                   // Количество вызовов
}
```

#### 3.2.6. code.validate
Проверить синтаксис кода.

```typescript
interface CodeValidateParams {
  code?: string;                   // Код для проверки
  path?: string;                   // Или путь к файлу
  rules?: string[];                // Правила для проверки
}

interface CodeValidateResult {
  valid: boolean;
  diagnostics: DiagnosticInfo[];
}

interface DiagnosticInfo {
  severity: "Error" | "Warning" | "Information" | "Hint";
  code: string;                    // Код правила
  message: string;
  line: number;
  column: number;
  endLine: number;
  endColumn: number;
  source: string;                  // "bsl-ls", "sonar", etc.
  quickFix?: QuickFixInfo;
}

interface QuickFixInfo {
  title: string;
  edit: TextEdit;
}
```

#### 3.2.7. code.lint
Статический анализ кода.

```typescript
interface CodeLintParams {
  path?: string;                   // Путь к файлу или директории
  object?: string;                 // Или объект метаданных
  rules?: string[];                // Правила (по умолчанию все)
  severity?: "Error" | "Warning" | "Information";
}

interface CodeLintResult {
  files: FileLintResult[];
  summary: LintSummary;
}

interface FileLintResult {
  path: string;
  diagnostics: DiagnosticInfo[];
}

interface LintSummary {
  filesAnalyzed: number;
  errors: number;
  warnings: number;
  information: number;
}
```

#### 3.2.8. code.format
Форматирование кода.

```typescript
interface CodeFormatParams {
  code?: string;
  path?: string;
  options?: FormatOptions;
}

interface FormatOptions {
  indentSize: number;
  indentStyle: "space" | "tab";
  maxLineLength: number;
  insertFinalNewline: boolean;
}

interface CodeFormatResult {
  formatted: string;
  changes: TextEdit[];
}
```

#### 3.2.9. code.complexity
Анализ сложности кода.

```typescript
interface CodeComplexityParams {
  path?: string;
  object?: string;
  threshold?: number;              // Порог цикломатической сложности
}

interface CodeComplexityResult {
  modules: ModuleComplexityInfo[];
}

interface ModuleComplexityInfo {
  path: string;
  totalComplexity: number;
  procedures: ProcedureComplexityInfo[];
}

interface ProcedureComplexityInfo {
  name: string;
  line: number;
  complexity: number;
  cognitiveComplexity: number;
  linesOfCode: number;
  parameters: number;
  exceedsThreshold: boolean;
}
```

---

### 3.3. Группа: generate — Генерация кода

#### 3.3.1. generate.query
Генерация запроса 1С.

```typescript
interface GenerateQueryParams {
  description: string;             // Описание на естественном языке
  tables?: string[];               // Таблицы для использования
  context?: string;                // Контекст (объект метаданных)
  style?: "simple" | "optimized";  // Стиль запроса
}

interface GenerateQueryResult {
  query: string;
  explanation: string;             // Пояснение к запросу
  tables: string[];                // Использованные таблицы
  parameters: QueryParameterInfo[];
}

interface QueryParameterInfo {
  name: string;
  type: string;
  description: string;
}
```

#### 3.3.2. generate.handler
Генерация обработчика события.

```typescript
interface GenerateHandlerParams {
  object: string;                  // Объект метаданных
  event: string;                   // Имя события
  moduleType: ModuleType;
  description?: string;            // Описание логики
}

type EventName =
  // Модуль объекта
  | "ПередЗаписью" | "ПриЗаписи" | "ПослеЗаписи"
  | "ОбработкаЗаполнения" | "ОбработкаПроверкиЗаполнения"
  | "ПередУдалением" | "ОбработкаПроведения" | "ОбработкаУдаленияПроведения"
  // Модуль формы
  | "ПриСозданииНаСервере" | "ПриОткрытии" | "ПередЗакрытием"
  | "ПриИзменении" | "ОбработкаВыбора" | "ОбработкаОповещения"
  // Модуль набора записей
  | "ПередЗаписью" | "ПриЗаписи";

interface GenerateHandlerResult {
  code: string;
  signature: string;
  insertPosition?: InsertPosition;
}

interface InsertPosition {
  path: string;
  line: number;
  region?: string;
}
```

#### 3.3.3. generate.print
Генерация печатной формы.

```typescript
interface GeneratePrintParams {
  object: string;                  // Объект метаданных
  templateName: string;            // Имя макета
  description: string;             // Описание печатной формы
  areas?: AreaDescription[];       // Описание областей
}

interface AreaDescription {
  name: string;
  type: "Header" | "Footer" | "TableHeader" | "TableRow" | "Group";
  parameters: string[];
}

interface GeneratePrintResult {
  managerCode: string;             // Код в модуле менеджера
  commandCode?: string;            // Код команды печати
  templateStructure: TemplateStructureInfo;
}
```

#### 3.3.4. generate.movement
Генерация движений по регистрам.

```typescript
interface GenerateMovementParams {
  document: string;
  registers: string[];             // Регистры для движений
  description?: string;            // Описание логики
}

interface GenerateMovementResult {
  code: string;
  movements: MovementCodeInfo[];
}

interface MovementCodeInfo {
  register: string;
  registerType: "Accumulation" | "Information" | "Accounting" | "Calculation";
  movementType?: "Receipt" | "Expense";
  code: string;
}
```

#### 3.3.5. generate.api
Генерация API-методов модуля.

```typescript
interface GenerateApiParams {
  moduleName: string;              // Имя модуля
  methods: MethodDescription[];
}

interface MethodDescription {
  name: string;
  type: "Procedure" | "Function";
  description: string;
  params?: ParamDescription[];
  returns?: string;
  directive: string;
}

interface ParamDescription {
  name: string;
  type: string;
  description: string;
  optional?: boolean;
  defaultValue?: string;
}

interface GenerateApiResult {
  code: string;
  documentation: string;
}
```

#### 3.3.6. generate.form_handler
Генерация обработчиков формы.

```typescript
interface GenerateFormHandlerParams {
  object: string;
  formName: string;
  elementName: string;             // Имя элемента формы
  event: FormElementEvent;
  description?: string;
}

type FormElementEvent =
  | "ПриИзменении" | "НачалоВыбора" | "ОкончаниеВводаТекста"
  | "Нажатие" | "ПриАктивизации" | "ПередНачаломДобавления"
  | "ПередУдалением" | "ПриАктивизацииСтроки" | "ВыборЗначения";

interface GenerateFormHandlerResult {
  clientCode: string;              // Клиентский обработчик
  serverCode?: string;             // Серверный метод (если нужен)
}
```

#### 3.3.7. generate.subscription
Генерация подписки на событие.

```typescript
interface GenerateSubscriptionParams {
  name: string;
  event: SubscriptionEvent;
  sources: string[];               // Объекты-источники
  handlerModule: string;
  description: string;
}

type SubscriptionEvent =
  | "ПередЗаписью" | "ПриЗаписи" | "ПередУдалением"
  | "ОбработкаПроверкиЗаполнения" | "ОбработкаЗаполнения";

interface GenerateSubscriptionResult {
  subscriptionXml: string;
  handlerCode: string;
}
```

#### 3.3.8. generate.scheduled_job
Генерация регламентного задания.

```typescript
interface GenerateScheduledJobParams {
  name: string;
  description: string;
  handlerModule: string;
  schedule?: ScheduleInfo;
}

interface ScheduleInfo {
  repeatPeriod?: number;           // Секунды
  dailyPeriod?: { from: string; to: string };
  weekDays?: number[];
  months?: number[];
}

interface GenerateScheduledJobResult {
  jobXml: string;
  handlerCode: string;
}
```

---

### 3.4. Группа: query — Работа с запросами

#### 3.4.1. query.parse
Разбор запроса.

```typescript
interface QueryParseParams {
  query: string;
}

interface QueryParseResult {
  valid: boolean;
  errors?: QueryError[];
  structure?: QueryStructure;
}

interface QueryError {
  message: string;
  line: number;
  column: number;
}

interface QueryStructure {
  type: "SELECT" | "SELECT_INTO" | "DROP";
  sources: QuerySourceInfo[];
  fields: QueryFieldInfo[];
  conditions: string[];
  groupBy: string[];
  orderBy: QueryOrderInfo[];
  unions: QueryStructure[];
  parameters: string[];
  tempTables: string[];
}

interface QuerySourceInfo {
  name: string;                    // Имя таблицы
  alias?: string;
  type: "Table" | "TempTable" | "Subquery" | "VirtualTable";
  virtualTableParams?: string[];
  joins: QueryJoinInfo[];
}

interface QueryJoinInfo {
  type: "INNER" | "LEFT" | "RIGHT" | "FULL";
  source: QuerySourceInfo;
  condition: string;
}

interface QueryFieldInfo {
  expression: string;
  alias?: string;
  aggregation?: "SUM" | "COUNT" | "AVG" | "MAX" | "MIN";
}

interface QueryOrderInfo {
  expression: string;
  direction: "ASC" | "DESC";
}
```

#### 3.4.2. query.validate
Валидация запроса с проверкой метаданных.

```typescript
interface QueryValidateParams {
  query: string;
}

interface QueryValidateResult {
  valid: boolean;
  syntaxErrors: QueryError[];
  metadataErrors: QueryMetadataError[];
  warnings: QueryWarning[];
}

interface QueryMetadataError {
  message: string;
  objectName: string;              // Несуществующий объект
  line: number;
  column: number;
}

interface QueryWarning {
  code: string;
  message: string;
  line: number;
  suggestion?: string;
}
```

#### 3.4.3. query.optimize
Оптимизация запроса.

```typescript
interface QueryOptimizeParams {
  query: string;
  profile?: "performance" | "readability";
}

interface QueryOptimizeResult {
  optimized: string;
  changes: OptimizationChange[];
  estimatedImprovement?: string;
}

interface OptimizationChange {
  type: string;                    // "index", "join", "subquery", etc.
  description: string;
  before: string;
  after: string;
}
```

#### 3.4.4. query.explain
Объяснение запроса.

```typescript
interface QueryExplainParams {
  query: string;
  language?: "ru" | "en";
}

interface QueryExplainResult {
  explanation: string;             // Текстовое описание
  steps: QueryStepExplanation[];
}

interface QueryStepExplanation {
  step: number;
  description: string;
  tables: string[];
  fields: string[];
}
```

#### 3.4.5. query.tables
Получить информацию о таблицах в запросе.

```typescript
interface QueryTablesParams {
  query: string;
  resolveMetadata?: boolean;       // Подтянуть метаданные таблиц
}

interface QueryTablesResult {
  tables: QueryTableInfo[];
  tempTables: TempTableInfo[];
}

interface QueryTableInfo {
  name: string;
  alias?: string;
  metadataObject?: string;         // Если resolveMetadata=true
  usedFields: string[];
  availableFields?: string[];      // Если resolveMetadata=true
}

interface TempTableInfo {
  name: string;
  definedAt: number;               // Номер подзапроса
  usedAt: number[];                // Где используется
  fields: string[];
}
```

---

### 3.5. Группа: template — Работа с макетами

#### 3.5.1. template.get
Получить структуру макета.

```typescript
interface TemplateGetParams {
  object: string;
  templateName: string;
}

interface TemplateGetResult {
  name: string;
  type: TemplateType;
  path: string;

  // Для табличного документа
  areas?: TemplateAreaDetail[];
  parameters?: TemplateParameterInfo[];

  // Сырые данные
  rawXml?: string;
}

interface TemplateAreaDetail {
  name: string;
  type: "Rows" | "Columns" | "Rectangle";
  range: { top: number; left: number; bottom: number; right: number };
  parameters: TemplateParameterInfo[];
  hasCondition: boolean;
}

interface TemplateParameterInfo {
  name: string;
  cell: { row: number; column: number };
  format?: string;
  expression?: string;
}
```

#### 3.5.2. template.parameters
Извлечь все параметры макета.

```typescript
interface TemplateParametersParams {
  object: string;
  templateName: string;
}

interface TemplateParametersResult {
  parameters: TemplateParameterDetail[];
}

interface TemplateParameterDetail {
  name: string;
  areas: string[];                 // В каких областях встречается
  suggestedType?: string;          // Предполагаемый тип
  usageCount: number;
}
```

#### 3.5.3. template.generate_fill_code
Сгенерировать код заполнения макета.

```typescript
interface TemplateGenerateFillCodeParams {
  object: string;
  templateName: string;
  dataSource?: string;             // Откуда данные (запрос, объект)
}

interface TemplateGenerateFillCodeResult {
  code: string;
  requiredData: RequiredDataInfo[];
}

interface RequiredDataInfo {
  parameter: string;
  suggestedSource: string;
  type: string;
}
```

---

### 3.6. Группа: runtime — Выполнение (опционально)

#### 3.6.1. runtime.connect
Подключение к базе.

```typescript
interface RuntimeConnectParams {
  connectionType: "com" | "http";

  // Для COM
  serverPath?: string;             // "Server\\Base" или путь к файловой базе

  // Для HTTP
  baseUrl?: string;

  // Общие
  user?: string;
  password?: string;
}

interface RuntimeConnectResult {
  connected: boolean;
  sessionId: string;
  serverVersion: string;
  configurationName: string;
  error?: string;
}
```

#### 3.6.2. runtime.query
Выполнить запрос.

```typescript
interface RuntimeQueryParams {
  sessionId: string;
  query: string;
  parameters?: Record<string, any>;
  limit?: number;
}

interface RuntimeQueryResult {
  success: boolean;
  columns: ColumnInfo[];
  rows: any[][];
  rowsCount: number;
  truncated: boolean;
  elapsed: number;
  error?: string;
}

interface ColumnInfo {
  name: string;
  type: string;
}
```

#### 3.6.3. runtime.eval
Выполнить произвольный код.

```typescript
interface RuntimeEvalParams {
  sessionId: string;
  code: string;
  returnResult?: boolean;
}

interface RuntimeEvalResult {
  success: boolean;
  result?: any;
  output?: string;                 // Вывод Сообщить()
  error?: string;
}
```

#### 3.6.4. runtime.call
Вызвать метод.

```typescript
interface RuntimeCallParams {
  sessionId: string;
  module: string;                  // Общий модуль
  method: string;
  params?: any[];
}

interface RuntimeCallResult {
  success: boolean;
  result?: any;
  error?: string;
}
```

#### 3.6.5. runtime.data
Получить данные объекта.

```typescript
interface RuntimeDataParams {
  sessionId: string;
  objectType: string;              // "Справочник.Сотрудники"
  reference: string;               // GUID или код/номер
  fields?: string[];               // Какие поля (все если не указано)
  includeTabular?: boolean;
}

interface RuntimeDataResult {
  success: boolean;
  data?: Record<string, any>;
  tabularSections?: Record<string, any[]>;
  error?: string;
}
```

---

### 3.7. Группа: platform — База знаний платформы

#### 3.7.1. platform.method
Получить описание метода платформы.

```typescript
interface PlatformMethodParams {
  name: string;                    // "Запрос.Выполнить" или "СокрЛП"
  context?: "global" | "object";
}

interface PlatformMethodResult {
  found: boolean;
  name: string;
  nameEn?: string;                 // Английское имя
  type: "Function" | "Procedure";
  description: string;
  syntax: string;
  parameters: PlatformParameterInfo[];
  returns?: PlatformReturnInfo;
  examples?: string[];
  availableIn: ContextAvailability;
  since?: string;                  // Версия платформы
  deprecated?: DeprecationInfo;
}

interface PlatformParameterInfo {
  name: string;
  type: string;
  description: string;
  optional: boolean;
  defaultValue?: string;
}

interface PlatformReturnInfo {
  type: string;
  description: string;
}

interface ContextAvailability {
  server: boolean;
  client: boolean;
  externalConnection: boolean;
  mobileApp: boolean;
}

interface DeprecationInfo {
  since: string;
  replacement: string;
  message: string;
}
```

#### 3.7.2. platform.type
Получить описание типа.

```typescript
interface PlatformTypeParams {
  name: string;                    // "Массив", "Соответствие", "ТаблицаЗначений"
}

interface PlatformTypeResult {
  found: boolean;
  name: string;
  nameEn?: string;
  description: string;
  constructors: ConstructorInfo[];
  properties: PropertyInfo[];
  methods: MethodSummaryInfo[];
  baseType?: string;
  implements?: string[];
}

interface ConstructorInfo {
  syntax: string;
  parameters: PlatformParameterInfo[];
}

interface PropertyInfo {
  name: string;
  type: string;
  description: string;
  readOnly: boolean;
}

interface MethodSummaryInfo {
  name: string;
  signature: string;
  description: string;
}
```

#### 3.7.3. platform.event
Получить описание события.

```typescript
interface PlatformEventParams {
  objectType: string;              // "Документ", "Справочник", "Форма"
  eventName: string;
}

interface PlatformEventResult {
  found: boolean;
  name: string;
  description: string;
  signature: string;
  parameters: EventParameterInfo[];
  context: "server" | "client" | "both";
  cancellable: boolean;
  examples?: string[];
}

interface EventParameterInfo {
  name: string;
  type: string;
  description: string;
  direction: "in" | "out" | "inout";
}
```

#### 3.7.4. platform.search
Поиск по API платформы.

```typescript
interface PlatformSearchParams {
  query: string;
  searchIn?: ("methods" | "types" | "properties" | "events")[];
  limit?: number;
}

interface PlatformSearchResult {
  results: PlatformSearchHit[];
  total: number;
}

interface PlatformSearchHit {
  type: "method" | "type" | "property" | "event";
  name: string;
  description: string;
  context?: string;                // Для методов — тип объекта
  score: number;
}
```

#### 3.7.5. platform.global_context
Получить глобальный контекст.

```typescript
interface PlatformGlobalContextParams {
  filter?: string;                 // Фильтр по имени
  category?: "methods" | "properties" | "collections";
}

interface PlatformGlobalContextResult {
  methods: GlobalMethodInfo[];
  properties: GlobalPropertyInfo[];
  collections: GlobalCollectionInfo[];
}

interface GlobalMethodInfo {
  name: string;
  nameEn: string;
  signature: string;
  description: string;
  category: string;
}

interface GlobalPropertyInfo {
  name: string;
  nameEn: string;
  type: string;
  description: string;
  readOnly: boolean;
}

interface GlobalCollectionInfo {
  name: string;
  nameEn: string;
  itemType: string;
  description: string;
}
```

---

### 3.8. Группа: config — Настройки конфигурации

#### 3.8.1. config.options
Получить функциональные опции.

```typescript
interface ConfigOptionsParams {
  filter?: string;
  includeValues?: boolean;         // Требует runtime
}

interface ConfigOptionsResult {
  options: FunctionalOptionInfo[];
}

interface FunctionalOptionInfo {
  name: string;
  synonym: string;
  description: string;
  storage: string;                 // Константа или регистр
  privilegedMode: boolean;
  value?: boolean;                 // Если includeValues
  dependencies: string[];          // Зависимые опции
  affectedObjects: string[];       // Какие объекты зависят
}
```

#### 3.8.2. config.constants
Получить константы.

```typescript
interface ConfigConstantsParams {
  filter?: string;
  subsystem?: string;
  includeValues?: boolean;         // Требует runtime
}

interface ConfigConstantsResult {
  constants: ConstantInfo[];
}

interface ConstantInfo {
  name: string;
  synonym: string;
  type: string;
  description: string;
  value?: any;
  subsystems: string[];
}
```

#### 3.8.3. config.scheduled_jobs
Получить регламентные задания.

```typescript
interface ConfigScheduledJobsParams {
  filter?: string;
  includeSchedule?: boolean;
}

interface ConfigScheduledJobsResult {
  jobs: ScheduledJobInfo[];
}

interface ScheduledJobInfo {
  name: string;
  synonym: string;
  description: string;
  methodName: string;
  key: string;
  use: boolean;
  predefined: boolean;
  restartOnFailure: boolean;
  restartCount: number;
  schedule?: ScheduleDetailInfo;
}

interface ScheduleDetailInfo {
  repeatPeriod: number;
  completionTime: number;
  repeatPause: number;
  dailyPeriod?: { beginTime: string; endTime: string };
  weekDays?: number[];
  months?: number[];
  daysInMonth?: number[];
}
```

#### 3.8.4. config.event_subscriptions
Получить подписки на события.

```typescript
interface ConfigEventSubscriptionsParams {
  source?: string;                 // Фильтр по источнику
  event?: string;                  // Фильтр по событию
}

interface ConfigEventSubscriptionsResult {
  subscriptions: EventSubscriptionInfo[];
}

interface EventSubscriptionInfo {
  name: string;
  synonym: string;
  event: string;
  handler: string;                 // Модуль.Процедура
  sources: string[];               // Объекты-источники
}
```

#### 3.8.5. config.exchanges
Получить планы обмена.

```typescript
interface ConfigExchangesParams {
  filter?: string;
}

interface ConfigExchangesResult {
  exchangePlans: ExchangePlanInfo[];
}

interface ExchangePlanInfo {
  name: string;
  synonym: string;
  description: string;
  distributed: boolean;
  content: ExchangeContentInfo[];
  autoRecord: AutoRecordInfo[];
}

interface ExchangeContentInfo {
  objectType: string;
  objectName: string;
  autoRecord: "Allow" | "Deny";
}

interface AutoRecordInfo {
  objectName: string;
  mode: "Allow" | "Deny";
}
```

#### 3.8.6. config.http_services
Получить HTTP-сервисы.

```typescript
interface ConfigHttpServicesParams {
  filter?: string;
}

interface ConfigHttpServicesResult {
  services: HttpServiceInfo[];
}

interface HttpServiceInfo {
  name: string;
  synonym: string;
  rootURL: string;
  reuseSessions: boolean;
  sessionMaxAge: number;
  urlTemplates: UrlTemplateInfo[];
}

interface UrlTemplateInfo {
  name: string;
  template: string;
  methods: HttpMethodInfo[];
}

interface HttpMethodInfo {
  name: string;
  httpMethod: "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
  handler: string;
}
```

---

### 3.9. Группа: pattern — Шаблоны кода

#### 3.9.1. pattern.list
Получить список шаблонов.

```typescript
interface PatternListParams {
  category?: PatternCategory;
  tags?: string[];
}

type PatternCategory =
  | "query"                        // Запросы
  | "form"                         // Формы
  | "print"                        // Печатные формы
  | "register"                     // Работа с регистрами
  | "exchange"                     // Обмен данными
  | "background"                   // Фоновые задания
  | "api"                          // API-методы
  | "validation"                   // Проверки
  | "ui"                           // Интерфейс
  | "error_handling";              // Обработка ошибок

interface PatternListResult {
  patterns: PatternSummary[];
}

interface PatternSummary {
  id: string;
  name: string;
  category: PatternCategory;
  description: string;
  tags: string[];
  complexity: "simple" | "medium" | "complex";
}
```

#### 3.9.2. pattern.get
Получить шаблон.

```typescript
interface PatternGetParams {
  id: string;
}

interface PatternGetResult {
  id: string;
  name: string;
  category: PatternCategory;
  description: string;
  tags: string[];

  // Шаблон
  template: string;                // Код с плейсхолдерами
  placeholders: PlaceholderInfo[];

  // Примеры
  examples: PatternExample[];

  // Рекомендации
  bestPractices: string[];
  antiPatterns: string[];
}

interface PlaceholderInfo {
  name: string;
  description: string;
  type: "string" | "identifier" | "type" | "code";
  required: boolean;
  defaultValue?: string;
  validation?: string;             // Regex
}

interface PatternExample {
  title: string;
  context: string;
  filledTemplate: string;
}
```

#### 3.9.3. pattern.apply
Применить шаблон.

```typescript
interface PatternApplyParams {
  id: string;
  values: Record<string, string>;  // Значения плейсхолдеров
  context?: string;                // Объект метаданных для контекста
}

interface PatternApplyResult {
  code: string;
  warnings?: string[];             // Предупреждения о потенциальных проблемах
}
```

#### 3.9.4. pattern.suggest
Предложить шаблон по задаче.

```typescript
interface PatternSuggestParams {
  task: string;                    // Описание задачи
  context?: string;                // Объект метаданных
  limit?: number;
}

interface PatternSuggestResult {
  suggestions: PatternSuggestion[];
}

interface PatternSuggestion {
  pattern: PatternSummary;
  relevance: number;               // 0-1
  reason: string;                  // Почему этот шаблон подходит
}
```

---

## 4. Индексация и кэширование

### 4.1. Структура индекса

```typescript
interface ConfigurationIndex {
  // Метаинформация
  meta: {
    configurationName: string;
    configurationVersion: string;
    platformVersion: string;
    indexVersion: string;
    createdAt: Date;
    updatedAt: Date;
    rootPath: string;
    filesCount: number;
    objectsCount: number;
  };

  // Объекты метаданных
  objects: Map<string, IndexedObject>;

  // Индекс по типам
  byType: Map<MetadataType, string[]>;

  // Индекс синонимов
  synonyms: Map<string, string>;         // Синоним → Имя

  // Модули
  modules: Map<string, IndexedModule>;

  // Граф вызовов
  callGraph: {
    calls: Map<string, string[]>;        // Кто кого вызывает
    calledBy: Map<string, string[]>;     // Кем вызывается
  };

  // Граф ссылок метаданных
  referenceGraph: {
    references: Map<string, ReferenceInfo[]>;
    referencedBy: Map<string, ReferenceInfo[]>;
  };

  // Полнотекстовый индекс
  fullText: FullTextIndex;
}

interface IndexedObject {
  name: string;
  type: MetadataType;
  synonym: string;
  path: string;
  uuid: string;
  xmlPath: string;
  modules: string[];                     // Пути к модулям
  forms: string[];
  templates: string[];
  attributes: string[];                  // Имена реквизитов
  tabularSections: string[];
  subsystems: string[];
  lastModified: Date;
  checksum: string;                      // Для инкрементального обновления
}

interface IndexedModule {
  path: string;
  objectName: string;
  moduleType: ModuleType;
  procedures: IndexedProcedure[];
  functions: IndexedFunction[];
  calls: string[];                       // Внешние вызовы
  references: string[];                  // Ссылки на метаданные
  lastModified: Date;
  checksum: string;
}

interface IndexedProcedure {
  name: string;
  line: number;
  endLine: number;
  export: boolean;
  directive: string;
  paramsCount: number;
  isEventHandler: boolean;
}

interface IndexedFunction extends IndexedProcedure {
  // Та же структура
}
```

### 4.2. Стратегия индексации

#### 4.2.1. Первичная индексация

```
1. Сканирование директорий
   ├── Найти все типы объектов (Catalogs, Documents, ...)
   ├── Для каждого типа — найти объекты
   └── Построить карту путей

2. Парсинг метаданных (параллельно)
   ├── Прочитать XML-файлы объектов
   ├── Извлечь структуру (реквизиты, ТЧ, формы)
   └── Построить индекс объектов

3. Парсинг кода (параллельно)
   ├── Найти все .bsl файлы
   ├── Извлечь процедуры/функции
   ├── Построить граф вызовов
   └── Построить граф ссылок

4. Построение полнотекстового индекса
   └── Индексировать имена, синонимы, комментарии

5. Сохранение индекса на диск
```

#### 4.2.2. Инкрементальное обновление

```
1. File watcher отслеживает изменения

2. При изменении файла:
   ├── Проверить checksum
   ├── Если изменился — переиндексировать файл
   └── Обновить связанные графы

3. При добавлении файла:
   ├── Определить тип объекта
   ├── Добавить в индекс
   └── Обновить графы

4. При удалении файла:
   ├── Удалить из индекса
   └── Очистить связи в графах
```

### 4.3. Хранение индекса

**Опции:**
1. **SQLite** — для больших конфигураций (>1000 объектов)
2. **LevelDB** — для средних конфигураций
3. **In-Memory + JSON** — для малых конфигураций

**Расположение:**
```
{configRoot}/.mcp-1c/
├── index.db                      # Основной индекс
├── cache/                        # Кэш парсинга
│   ├── metadata/
│   └── modules/
└── config.json                   # Настройки индекса
```

---

## 5. База знаний BSL

### 5.1. Структура

```
knowledge/
├── platform/
│   ├── 8.3.24/                   # Версия платформы
│   │   ├── global-context.json   # Глобальный контекст
│   │   ├── types.json            # Типы данных
│   │   ├── methods.json          # Методы по типам
│   │   └── events.json           # События
│   └── 8.3.23/
│       └── ...
├── syntax/
│   ├── keywords.json             # Ключевые слова
│   ├── operators.json            # Операторы
│   ├── directives.json           # Директивы компиляции
│   └── preprocessor.json         # Препроцессор
├── patterns/
│   ├── queries/
│   │   ├── select-basic.json
│   │   ├── join-left.json
│   │   └── ...
│   ├── forms/
│   ├── registers/
│   └── ...
└── errors/
    ├── runtime-errors.json       # Ошибки выполнения
    └── common-mistakes.json      # Частые ошибки
```

### 5.2. Формат данных

#### 5.2.1. Глобальный контекст

```json
{
  "version": "8.3.24",
  "methods": {
    "Сообщить": {
      "nameEn": "Message",
      "type": "Procedure",
      "description": "Выводит сообщение пользователю",
      "syntax": "Сообщить(<Текст>, <Статус>)",
      "parameters": [
        {
          "name": "Текст",
          "type": "Строка",
          "description": "Текст сообщения",
          "optional": false
        },
        {
          "name": "Статус",
          "type": "СтатусСообщения",
          "description": "Статус сообщения",
          "optional": true,
          "defaultValue": "СтатусСообщения.Информация"
        }
      ],
      "availability": {
        "server": true,
        "client": true,
        "externalConnection": true
      },
      "since": "8.0"
    }
  },
  "properties": {
    "ПараметрыСеанса": {
      "nameEn": "SessionParameters",
      "type": "ПараметрыСеанса",
      "description": "Доступ к параметрам сеанса",
      "readOnly": true
    }
  },
  "collections": {
    "Справочники": {
      "nameEn": "Catalogs",
      "type": "СправочникиМенеджер",
      "description": "Доступ к справочникам конфигурации"
    }
  }
}
```

#### 5.2.2. Типы данных

```json
{
  "Массив": {
    "nameEn": "Array",
    "description": "Упорядоченная коллекция элементов",
    "constructors": [
      {
        "syntax": "Новый Массив",
        "description": "Создаёт пустой массив"
      },
      {
        "syntax": "Новый Массив(<РазмерМассива>)",
        "parameters": [
          {
            "name": "РазмерМассива",
            "type": "Число",
            "description": "Начальный размер"
          }
        ]
      }
    ],
    "properties": [
      {
        "name": "Количество",
        "nameEn": "Count",
        "type": "Число",
        "description": "Количество элементов",
        "readOnly": true
      }
    ],
    "methods": [
      {
        "name": "Добавить",
        "nameEn": "Add",
        "type": "Procedure",
        "syntax": "Добавить(<Значение>)",
        "description": "Добавляет элемент в конец массива"
      },
      {
        "name": "Найти",
        "nameEn": "Find",
        "type": "Function",
        "syntax": "Найти(<Значение>)",
        "returns": {
          "type": "Число, Неопределено",
          "description": "Индекс или Неопределено"
        }
      }
    ]
  }
}
```

#### 5.2.3. Шаблоны кода

```json
{
  "id": "query-select-with-filter",
  "name": "Запрос с отбором",
  "category": "query",
  "description": "Базовый запрос выборки с параметром отбора",
  "tags": ["запрос", "выборка", "отбор"],
  "template": "ВЫБРАТЬ\n\t${fields}\nИЗ\n\t${table} КАК Таблица\nГДЕ\n\tТаблица.${filterField} = &${parameterName}",
  "placeholders": [
    {
      "name": "fields",
      "description": "Список полей",
      "type": "code",
      "required": true,
      "defaultValue": "Таблица.Ссылка"
    },
    {
      "name": "table",
      "description": "Имя таблицы",
      "type": "identifier",
      "required": true
    },
    {
      "name": "filterField",
      "description": "Поле для отбора",
      "type": "identifier",
      "required": true
    },
    {
      "name": "parameterName",
      "description": "Имя параметра",
      "type": "identifier",
      "required": true,
      "defaultValue": "Отбор"
    }
  ],
  "examples": [
    {
      "title": "Выборка сотрудников организации",
      "context": "Справочник.Сотрудники",
      "filledTemplate": "ВЫБРАТЬ\n\tТаблица.Ссылка,\n\tТаблица.Наименование\nИЗ\n\tСправочник.Сотрудники КАК Таблица\nГДЕ\n\tТаблица.Организация = &Организация"
    }
  ],
  "bestPractices": [
    "Используйте псевдонимы для таблиц",
    "Указывайте только нужные поля вместо *"
  ],
  "antiPatterns": [
    "Избегайте ВЫБРАТЬ * — это замедляет запрос"
  ]
}
```

---

## 6. Интеграция с BSL Language Server

### 6.1. Использование BSL LS

MCP-сервер использует BSL Language Server для:
- Проверки синтаксиса
- Форматирования кода
- Статического анализа
- Получения диагностик

### 6.2. Конфигурация

```json
{
  "bslls": {
    "enabled": true,
    "path": "/usr/local/bin/bsl-language-server",
    "configPath": ".bsl-language-server.json",
    "diagnosticLanguage": "ru"
  }
}
```

### 6.3. Интеграция

```typescript
class BslLsIntegration {
  // Запуск LSP сервера
  async start(): Promise<void>;

  // Валидация файла
  async validateFile(path: string): Promise<Diagnostic[]>;

  // Валидация кода
  async validateCode(code: string): Promise<Diagnostic[]>;

  // Форматирование
  async format(code: string): Promise<string>;

  // Hover информация
  async hover(path: string, line: number, column: number): Promise<HoverInfo>;

  // Completion
  async complete(path: string, line: number, column: number): Promise<CompletionItem[]>;
}
```

---

## 7. Конфигурация MCP-сервера

### 7.1. Файл конфигурации

```json
{
  "server": {
    "name": "mcp-1c",
    "version": "1.0.0",
    "transport": "stdio"
  },

  "configuration": {
    "rootPath": "/path/to/config",
    "autoIndex": true,
    "watchChanges": true,
    "indexStorage": "sqlite"
  },

  "runtime": {
    "enabled": false,
    "type": "com",
    "connection": {
      "server": "localhost",
      "base": "MyBase",
      "user": "Admin",
      "password": ""
    }
  },

  "bslls": {
    "enabled": true,
    "path": "bsl-language-server",
    "configPath": ".bsl-language-server.json"
  },

  "knowledge": {
    "platformVersion": "8.3.24",
    "language": "ru"
  },

  "logging": {
    "level": "info",
    "file": "mcp-1c.log"
  }
}
```

### 7.2. Переменные окружения

| Переменная | Описание |
|------------|----------|
| `MCP_1C_CONFIG` | Путь к файлу конфигурации |
| `MCP_1C_ROOT` | Путь к корню конфигурации |
| `MCP_1C_LOG_LEVEL` | Уровень логирования |
| `MCP_1C_BSLLS_PATH` | Путь к BSL LS |

---

## 8. Требования к реализации

### 8.1. Технологический стек

| Компонент | Технология | Обоснование |
|-----------|------------|-------------|
| Язык | TypeScript | Типизация, экосистема MCP |
| Runtime | Node.js 20+ | LTS, производительность |
| MCP SDK | @modelcontextprotocol/sdk | Официальный SDK |
| XML парсер | fast-xml-parser | Производительность |
| BSL парсер | bsl-parser (npm) | Готовое решение |
| Индекс | better-sqlite3 | Быстрый SQLite |
| File watching | chokidar | Кроссплатформенность |
| Тестирование | vitest | Быстрые тесты |

### 8.2. Производительность

| Метрика | Требование |
|---------|------------|
| Первичная индексация | < 60 сек для конфигурации с 5000 объектов |
| Поиск по имени | < 50 мс |
| Получение метаданных объекта | < 100 мс |
| Поиск использований | < 500 мс |
| Генерация кода | < 200 мс |

### 8.3. Совместимость

| Платформа | Поддержка |
|-----------|-----------|
| Windows 10+ | Полная (включая COM) |
| macOS 12+ | Без COM |
| Linux | Без COM |
| Платформа 1С | 8.3.18 — 8.3.24 |

---

## 9. Этапы разработки

### 9.1. Фаза 1: Ядро (MVP)

**Срок: 4 недели**

**Deliverables:**
- [ ] Парсер метаданных XML
- [ ] Индексатор конфигурации
- [ ] Базовый MCP-сервер
- [ ] Tools: metadata.init, metadata.list, metadata.get, metadata.search
- [ ] Tools: code.module, code.resolve, code.usages

### 9.2. Фаза 2: Анализ кода

**Срок: 3 недели**

**Deliverables:**
- [ ] Парсер BSL (интеграция с bsl-parser)
- [ ] Граф вызовов
- [ ] Tools: code.dependencies, code.validate, code.lint
- [ ] Интеграция с BSL Language Server

### 9.3. Фаза 3: Генерация

**Срок: 3 недели**

**Deliverables:**
- [ ] Шаблонизатор кода
- [ ] База шаблонов
- [ ] Tools: generate.*, pattern.*
- [ ] Tools: query.*

### 9.4. Фаза 4: Расширенные возможности

**Срок: 3 недели**

**Deliverables:**
- [ ] Tools: template.*, config.*
- [ ] База знаний платформы
- [ ] Tools: platform.*
- [ ] Runtime (COM/HTTP) — опционально

### 9.5. Фаза 5: Оптимизация и документация

**Срок: 2 недели**

**Deliverables:**
- [ ] Оптимизация производительности
- [ ] Тестирование на реальных конфигурациях
- [ ] Документация
- [ ] Примеры использования

---

## 10. Тестирование

### 10.1. Unit-тесты

- Парсеры XML и BSL
- Индексатор
- Каждый tool

### 10.2. Интеграционные тесты

- Полный цикл индексации
- Сценарии использования

### 10.3. Тестовые конфигурации

1. **Минимальная** — 10-20 объектов (для быстрых тестов)
2. **Средняя** — ~500 объектов (типовая УТ)
3. **Большая** — ~3000 объектов (типовая ЗУП)

---

## 11. Документация

### 11.1. Для пользователей

- Установка и настройка
- Примеры использования с Claude Code
- FAQ

### 11.2. Для разработчиков

- Архитектура
- API Reference
- Добавление новых tools
- Расширение базы знаний

---

---

## 12. Skills (Быстрые команды)

Skills — это готовые сценарии для частых операций, вызываемые через `/команда`.

### 12.1. Список Skills

#### 12.1.1. /1c-query — Генерация запроса

**Назначение:** Создание запроса 1С по описанию на естественном языке.

**Вызов:**
```
/1c-query Получить всех сотрудников организации с их должностями
```

**Параметры:**
| Параметр | Описание | Обязательный |
|----------|----------|--------------|
| description | Описание запроса | Да |
| --tables | Таблицы для использования | Нет |
| --temp | Использовать временные таблицы | Нет |
| --batch | Пакетный запрос | Нет |

**Workflow:**
```
1. Анализ описания
2. Определение нужных таблиц из индекса метаданных
3. Генерация запроса
4. Валидация синтаксиса
5. Вывод запроса с пояснениями
```

**Пример вывода:**
```bsl
// Запрос: Получить всех сотрудников организации с их должностями
// Таблицы: РегистрСведений.ТекущиеКадровыеДанныеСотрудников

ВЫБРАТЬ
    КадровыеДанные.Сотрудник КАК Сотрудник,
    КадровыеДанные.Сотрудник.Наименование КАК ФИО,
    КадровыеДанные.Должность КАК Должность,
    КадровыеДанные.Подразделение КАК Подразделение
ИЗ
    РегистрСведений.ТекущиеКадровыеДанныеСотрудников КАК КадровыеДанные
ГДЕ
    КадровыеДанные.Организация = &Организация

// Параметры:
//   Организация - СправочникСсылка.Организации
```

---

#### 12.1.2. /1c-metadata — Информация об объекте

**Назначение:** Быстрый просмотр структуры объекта метаданных.

**Вызов:**
```
/1c-metadata Документ.БольничныйЛист
/1c-metadata БольничныйЛист
/1c-metadata "Больничный лист"
```

**Параметры:**
| Параметр | Описание | Обязательный |
|----------|----------|--------------|
| object | Имя объекта или синоним | Да |
| --full | Полная информация | Нет |
| --refs | Показать связи | Нет |

**Workflow:**
```
1. Поиск объекта по имени/синониму
2. Загрузка метаданных из индекса
3. Форматированный вывод структуры
```

**Пример вывода:**
```
📄 Документ.БольничныйЛист (Больничный лист)

📋 Реквизиты (15):
  • Организация: СправочникСсылка.Организации
  • Сотрудник: СправочникСсылка.Сотрудники
  • ФизическоеЛицо: СправочникСсылка.ФизическиеЛица
  • ДатаНачала: Дата
  • ДатаОкончания: Дата
  • ПричинаНетрудоспособности: ПеречислениеСсылка.ПричиныНетрудоспособности
  ...

📑 Табличные части (8):
  • Начисления (12 колонок)
  • НДФЛ (8 колонок)
  • СреднийЗаработокФСС (6 колонок)
  ...

📝 Формы (6):
  • ФормаДокумента (основная)
  • ФормаСписка
  ...

🖨️ Макеты (3):
  • ПФ_MXL_РасчетПособия
  ...

📊 Движения:
  • РегистрНакопления.НачисленияУдержанияПоСотрудникам
  • РегистрНакопления.ВзаиморасчетыССотрудниками
  ...
```

---

#### 12.1.3. /1c-handler — Генерация обработчика

**Назначение:** Создание шаблона обработчика события.

**Вызов:**
```
/1c-handler ПриЗаписи Документ.ПриемНаРаботу
/1c-handler ПриИзменении Форма.Организация
```

**Параметры:**
| Параметр | Описание | Обязательный |
|----------|----------|--------------|
| event | Имя события | Да |
| object | Объект/элемент формы | Да |
| --desc | Описание логики | Нет |

**События модуля объекта:**
- ПередЗаписью, ПриЗаписи, ПослеЗаписи
- ОбработкаЗаполнения, ОбработкаПроверкиЗаполнения
- ОбработкаПроведения, ОбработкаУдаленияПроведения
- ПередУдалением

**События формы:**
- ПриСозданииНаСервере, ПриОткрытии, ПередЗакрытием
- ПослеЗаписиНаСервере, ОбработкаОповещения

**События элементов:**
- ПриИзменении, НачалоВыбора, ОбработкаВыбора
- ПередНачаломДобавления, ПередУдалением

**Пример вывода:**
```bsl
// Обработчик события ПриЗаписи документа ПриемНаРаботу
// Модуль: Documents/ПриемНаРаботу/Ext/ObjectModule.bsl

Процедура ПриЗаписи(Отказ)

    // Проверка заполнения обязательных полей
    Если Не ЗначениеЗаполнено(Сотрудник) Тогда
        ОбщегоНазначения.СообщитьПользователю(
            НСтр("ru = 'Не заполнен сотрудник'"),
            ЭтотОбъект,
            "Сотрудник",
            ,
            Отказ);
    КонецЕсли;

    // TODO: Добавьте логику обработки

КонецПроцедуры
```

---

#### 12.1.4. /1c-print — Генерация печатной формы

**Назначение:** Создание кода печатной формы для документа/справочника.

**Вызов:**
```
/1c-print Документ.АктВыполненныхРабот "Акт выполненных работ"
```

**Параметры:**
| Параметр | Описание | Обязательный |
|----------|----------|--------------|
| object | Объект метаданных | Да |
| name | Название печатной формы | Да |
| --template | Имя существующего макета | Нет |

**Workflow:**
```
1. Анализ структуры объекта
2. Определение данных для печати
3. Генерация кода в модуле менеджера
4. Генерация структуры макета
```

**Пример вывода:**
```bsl
// Добавить в модуль менеджера: Documents/АктВыполненныхРабот/Ext/ManagerModule.bsl

#Область ПечатныеФормы

// Формирует печатную форму "Акт выполненных работ"
//
// Параметры:
//  МассивОбъектов - Массив - ссылки на документы
//  ОбъектыПечати - СписокЗначений - объекты печати (выходной)
//
// Возвращаемое значение:
//  ТабличныйДокумент - сформированная печатная форма
//
Функция ПечатьАктВыполненныхРабот(МассивОбъектов, ОбъектыПечати) Экспорт

    ТабличныйДокумент = Новый ТабличныйДокумент;
    ТабличныйДокумент.КлючПараметровПечати = "ПараметрыПечати_АктВыполненныхРабот";

    Макет = УправлениеПечатью.МакетПечатнойФормы("Документ.АктВыполненныхРабот.ПФ_MXL_Акт");

    // Получение данных
    Запрос = Новый Запрос;
    Запрос.Текст =
    "ВЫБРАТЬ
    |    Акт.Ссылка КАК Ссылка,
    |    Акт.Номер КАК Номер,
    |    Акт.Дата КАК Дата,
    |    Акт.Организация.Наименование КАК Организация,
    |    Акт.Контрагент.Наименование КАК Контрагент,
    |    Акт.Услуги.(
    |        Номенклатура.Наименование КАК Услуга,
    |        Количество,
    |        Цена,
    |        Сумма
    |    ) КАК Услуги
    |ИЗ
    |    Документ.АктВыполненныхРабот КАК Акт
    |ГДЕ
    |    Акт.Ссылка В (&МассивОбъектов)";

    Запрос.УстановитьПараметр("МассивОбъектов", МассивОбъектов);
    Выборка = Запрос.Выполнить().Выбрать();

    ПервыйДокумент = Истина;

    Пока Выборка.Следующий() Цикл

        Если Не ПервыйДокумент Тогда
            ТабличныйДокумент.ВывестиГоризонтальныйРазделительСтраниц();
        КонецЕсли;
        ПервыйДокумент = Ложь;

        НомерСтрокиНачало = ТабличныйДокумент.ВысотаТаблицы + 1;

        // Шапка
        ОбластьШапка = Макет.ПолучитьОбласть("Шапка");
        ОбластьШапка.Параметры.Заполнить(Выборка);
        ТабличныйДокумент.Вывести(ОбластьШапка);

        // Таблица услуг
        ОбластьШапкаТаблицы = Макет.ПолучитьОбласть("ШапкаТаблицы");
        ТабличныйДокумент.Вывести(ОбластьШапкаТаблицы);

        ОбластьСтрока = Макет.ПолучитьОбласть("Строка");
        ВыборкаУслуги = Выборка.Услуги.Выбрать();
        НомерСтроки = 0;

        Пока ВыборкаУслуги.Следующий() Цикл
            НомерСтроки = НомерСтроки + 1;
            ОбластьСтрока.Параметры.НомерСтроки = НомерСтроки;
            ОбластьСтрока.Параметры.Заполнить(ВыборкаУслуги);
            ТабличныйДокумент.Вывести(ОбластьСтрока);
        КонецЦикла;

        // Подвал
        ОбластьПодвал = Макет.ПолучитьОбласть("Подвал");
        ТабличныйДокумент.Вывести(ОбластьПодвал);

        УправлениеПечатью.ЗадатьОбластьПечатиДокумента(
            ТабличныйДокумент,
            НомерСтрокиНачало,
            ОбъектыПечати,
            Выборка.Ссылка);

    КонецЦикла;

    Возврат ТабличныйДокумент;

КонецФункции

#КонецОбласти
```

---

#### 12.1.5. /1c-usages — Поиск использований

**Назначение:** Найти все места использования объекта/метода.

**Вызов:**
```
/1c-usages ЗарплатаКадры.ПроверитьКорректностьДаты
/1c-usages Справочник.Сотрудники
```

**Параметры:**
| Параметр | Описание | Обязательный |
|----------|----------|--------------|
| name | Имя для поиска | Да |
| --type | Тип (call/reference/all) | Нет |
| --limit | Ограничение результатов | Нет |

**Пример вывода:**
```
🔍 Использования: ЗарплатаКадры.ПроверитьКорректностьДаты

Найдено: 47 вызовов в 23 файлах

📁 Documents/БольничныйЛист/Ext/ObjectModule.bsl
   67: ЗарплатаКадры.ПроверитьКорректностьДаты(Ссылка, ДатаНачала, "Объект.ДатаНачала", Отказ,
   74: ЗарплатаКадры.ПроверитьКорректностьДаты(Ссылка, ДатаНачалаРодственник1, ...
   95: ЗарплатаКадры.ПроверитьКорректностьДаты(Ссылка, ДатаНачалаСобытия, ...

📁 Documents/Отпуск/Ext/ObjectModule.bsl
   45: ЗарплатаКадры.ПроверитьКорректностьДаты(Ссылка, ДатаНачала, ...
   52: ЗарплатаКадры.ПроверитьКорректностьДаты(Ссылка, ДатаОкончания, ...

📁 Documents/ПриемНаРаботу/Ext/ObjectModule.bsl
   128: ЗарплатаКадры.ПроверитьКорректностьДаты(Ссылка, ДатаПриема, ...

... ещё 17 файлов
```

---

#### 12.1.6. /1c-validate — Проверка синтаксиса

**Назначение:** Проверка синтаксиса текущего файла или выделенного кода.

**Вызов:**
```
/1c-validate                    # Текущий файл
/1c-validate path/to/file.bsl   # Конкретный файл
/1c-validate --selection        # Выделенный код
```

**Параметры:**
| Параметр | Описание | Обязательный |
|----------|----------|--------------|
| path | Путь к файлу | Нет |
| --selection | Проверить выделение | Нет |
| --fix | Автоисправление | Нет |

**Пример вывода:**
```
🔍 Проверка: Documents/БольничныйЛист/Ext/ObjectModule.bsl

❌ Ошибки (2):
  Строка 145: Переменная "ДатаОкончания" не определена
  Строка 267: Ожидается "КонецЕсли"

⚠️ Предупреждения (5):
  Строка 45: Неиспользуемая переменная "ВременнаяПеременная"
  Строка 89: Функция "УстаревшийМетод" устарела, используйте "НовыйМетод"
  Строка 156: Цикломатическая сложность процедуры превышает 20
  ...

ℹ️ Информация (3):
  Строка 12: Отсутствует описание параметра "Отказ"
  ...
```

---

#### 12.1.7. /1c-deps — Граф зависимостей

**Назначение:** Показать зависимости модуля/объекта.

**Вызов:**
```
/1c-deps Документ.БольничныйЛист
/1c-deps CommonModules/ЗарплатаКадры --depth 2
```

**Параметры:**
| Параметр | Описание | Обязательный |
|----------|----------|--------------|
| object | Объект для анализа | Да |
| --depth | Глубина графа | Нет |
| --direction | calls/calledBy/both | Нет |

**Пример вывода:**
```
📊 Зависимости: Документ.БольничныйЛист

→ Вызывает (15 модулей):
  ├── CommonModules/ЗарплатаКадры (12 вызовов)
  │   ├── ЗаполнитьПоОснованиюСотрудником
  │   ├── ПроверитьКорректностьДаты
  │   └── ...
  ├── CommonModules/ОбщегоНазначения (8 вызовов)
  │   ├── ЗначенияРеквизитовОбъекта
  │   └── ...
  ├── CommonModules/КадровыйУчет (5 вызовов)
  ├── Documents/ВходящийЗапросФССДляРасчетаПособия (2 вызова)
  └── InformationRegisters/СведенияОбЭЛН (1 вызов)

← Вызывается из (8 модулей):
  ├── DataProcessors/НачислениеЗарплатыИВзносов
  ├── Reports/РасчетныйЛисток
  └── ...

📈 Регистры движений:
  ├── AccumulationRegisters/НачисленияУдержанияПоСотрудникам
  ├── AccumulationRegisters/ВзаиморасчетыССотрудниками
  └── InformationRegisters/ДанныеОВремениПоСотрудникам
```

---

#### 12.1.8. /1c-movement — Генерация движений

**Назначение:** Создание кода движений документа по регистрам.

**Вызов:**
```
/1c-movement Документ.ПриемНаРаботу
```

**Параметры:**
| Параметр | Описание | Обязательный |
|----------|----------|--------------|
| document | Документ | Да |
| --registers | Конкретные регистры | Нет |

**Пример вывода:**
```bsl
// Движения документа ПриемНаРаботу
// Добавить в процедуру ОбработкаПроведения

Движения.ТекущиеКадровыеДанныеСотрудников.Записывать = Истина;

// Регистр сведений: ТекущиеКадровыеДанныеСотрудников
Движение = Движения.ТекущиеКадровыеДанныеСотрудников.Добавить();
Движение.Период = Дата;
Движение.Сотрудник = Сотрудник;
Движение.Организация = Организация;
Движение.Должность = Должность;
Движение.Подразделение = Подразделение;
Движение.ВидЗанятости = ВидЗанятости;
Движение.ГрафикРаботы = ГрафикРаботы;

// Регистр сведений: СведенияОТрудовойДеятельности
Движения.СведенияОТрудовойДеятельности.Записывать = Истина;
Движение = Движения.СведенияОТрудовойДеятельности.Добавить();
Движение.Период = ДатаПриема;
Движение.ФизическоеЛицо = ФизическоеЛицо;
Движение.Организация = Организация;
Движение.ВидСобытия = Перечисления.ВидыКадровыхСобытий.Прием;
// ...
```

---

#### 12.1.9. /1c-format — Форматирование кода

**Назначение:** Форматирование BSL-кода по стандартам.

**Вызов:**
```
/1c-format                      # Текущий файл
/1c-format --selection          # Выделенный код
```

**Параметры:**
| Параметр | Описание | Обязательный |
|----------|----------|--------------|
| --selection | Форматировать выделение | Нет |
| --style | Стиль (1c-standard/custom) | Нет |

---

#### 12.1.10. /1c-explain — Объяснение кода

**Назначение:** Объяснение работы выделенного кода или запроса.

**Вызов:**
```
/1c-explain                     # Выделенный код
/1c-explain --query             # Объяснить запрос
```

---

### 12.2. Конфигурация Skills

```yaml
# .claude/skills/1c.yaml

skills:
  1c-query:
    description: "Генерация запроса 1С"
    tools:
      - metadata.search
      - metadata.attributes
      - query.generate
      - query.validate

  1c-metadata:
    description: "Информация об объекте метаданных"
    tools:
      - metadata.get
      - metadata.references
      - metadata.registers

  1c-handler:
    description: "Генерация обработчика события"
    tools:
      - metadata.get
      - code.module
      - generate.handler
      - platform.event

  1c-print:
    description: "Генерация печатной формы"
    tools:
      - metadata.get
      - metadata.templates
      - template.parameters
      - generate.print

  1c-usages:
    description: "Поиск использований"
    tools:
      - code.usages
      - code.resolve

  1c-validate:
    description: "Проверка синтаксиса"
    tools:
      - code.validate
      - code.lint

  1c-deps:
    description: "Граф зависимостей"
    tools:
      - code.dependencies
      - metadata.references
```

---

## 13. Agents (Автономные агенты)

Agents — это автономные процессы для сложных многошаговых задач.

### 13.1. 1C-Explore — Исследование конфигурации

**Назначение:** Глубокий анализ конфигурации, поиск логики, понимание архитектуры.

**Когда использовать:**
- "Как работает расчёт отпускных?"
- "Где хранятся данные о стаже?"
- "Найди всю логику связанную с НДФЛ"
- "Какие документы влияют на регистр взаиморасчётов?"

**Доступные tools:**
- Все tools группы `metadata.*`
- Все tools группы `code.*`
- `platform.method`, `platform.type`

**Workflow:**
```
1. Анализ запроса пользователя
2. Поиск релевантных объектов метаданных
3. Анализ связей и зависимостей
4. Чтение и анализ кода модулей
5. Построение понимания логики
6. Формирование отчёта с примерами кода
```

**Пример использования:**
```
User: Как работает расчёт больничного?

Agent 1C-Explore:
  1. metadata.search("больничн") → Документ.БольничныйЛист
  2. metadata.get("Документ.БольничныйЛист") → структура документа
  3. code.module("Документ.БольничныйЛист", "ManagerModule") → модуль менеджера
  4. code.dependencies("Документ.БольничныйЛист") → граф зависимостей
  5. Анализ ключевых процедур:
     - ПровестиПоУчетам
     - РассчитатьПособие
     - ЗаполнитьСреднийЗаработок
  6. metadata.registers("Документ.БольничныйЛист") → регистры движений

Output:
  ## Расчёт больничного листа

  ### Основные этапы:
  1. Определение периода нетрудоспособности
  2. Расчёт среднего заработка (ЗарплатаКадрыРасширенный.РассчитатьСреднийЗаработокФСС)
  3. Расчёт пособия с учётом стажа
  4. Формирование движений по регистрам

  ### Ключевые модули:
  - Documents/БольничныйЛист/Ext/ManagerModule.bsl:1245 — основной расчёт
  - CommonModules/РасчетЗарплатыРасширенный — алгоритмы
  ...
```

**Конфигурация агента:**
```typescript
interface Explore1CAgentConfig {
  name: "1C-Explore";
  description: "Исследование конфигурации 1С";

  tools: [
    "metadata.init",
    "metadata.list",
    "metadata.get",
    "metadata.search",
    "metadata.tree",
    "metadata.attributes",
    "metadata.registers",
    "metadata.references",
    "code.module",
    "code.procedure",
    "code.resolve",
    "code.usages",
    "code.dependencies",
    "platform.method",
    "platform.type",
    "platform.search"
  ];

  maxTurns: 20;

  systemPrompt: `
    Ты — эксперт по конфигурациям 1С:Предприятие.

    Твоя задача — исследовать конфигурацию и объяснить пользователю,
    как работает интересующий его функционал.

    Правила:
    1. Начинай с поиска релевантных объектов метаданных
    2. Анализируй связи между объектами
    3. Читай код ключевых процедур
    4. Строй понимание логики шаг за шагом
    5. Давай конкретные ответы с ссылками на код
    6. Используй примеры из реального кода конфигурации
  `;
}
```

---

### 13.2. 1C-Implement — Реализация функционала

**Назначение:** Пошаговая реализация нового функционала или доработок.

**Когда использовать:**
- "Добавь новый вид начисления Премия за KPI"
- "Создай отчёт по остаткам отпусков"
- "Добавь проверку при проведении документа"
- "Реализуй печатную форму акта"

**Доступные tools:**
- Все tools группы `metadata.*`
- Все tools группы `code.*`
- Все tools группы `generate.*`
- Все tools группы `template.*`
- `pattern.*`

**Workflow:**
```
1. Анализ требований
2. Исследование существующего функционала
3. Планирование изменений
4. Генерация кода
5. Валидация
6. Предоставление инструкций по внедрению
```

**Пример использования:**
```
User: Добавь проверку при проведении ПриемНаРаботу —
      сотрудник не может быть принят если у него есть активный договор

Agent 1C-Implement:
  1. metadata.get("Документ.ПриемНаРаботу") → структура
  2. code.module("Документ.ПриемНаРаботу", "ObjectModule") → текущий код
  3. code.procedure(..., "ОбработкаПроведения") → существующая проверка
  4. metadata.search("трудовой договор") → связанные объекты
  5. generate.query("найти активные договоры сотрудника")
  6. Генерация кода проверки

Output:
  ## Реализация проверки

  ### Изменения в модуле объекта
  Файл: Documents/ПриемНаРаботу/Ext/ObjectModule.bsl

  Добавить в процедуру ОбработкаПроверкиЗаполнения:

  ```bsl
  // Проверка отсутствия активного договора
  Если ЕстьАктивныйТрудовойДоговор(Сотрудник, Организация, ДатаПриема) Тогда
      ОбщегоНазначения.СообщитьПользователю(
          НСтр("ru = 'У сотрудника есть активный трудовой договор'"),
          ЭтотОбъект,
          "Сотрудник",
          ,
          Отказ);
  КонецЕсли;
  ```

  Добавить функцию:

  ```bsl
  Функция ЕстьАктивныйТрудовойДоговор(Сотрудник, Организация, ДатаПроверки)

      Запрос = Новый Запрос;
      Запрос.Текст =
      "ВЫБРАТЬ ПЕРВЫЕ 1
      |    ИСТИНА
      |ИЗ
      |    РегистрСведений.ТрудовыеДоговорыСотрудников.СрезПоследних(&ДатаПроверки,
      |        Сотрудник = &Сотрудник
      |        И Организация = &Организация) КАК Договоры
      |ГДЕ
      |    Договоры.Статус = ЗНАЧЕНИЕ(Перечисление.СтатусыТрудовыхДоговоров.Действует)";

      Запрос.УстановитьПараметр("Сотрудник", Сотрудник);
      Запрос.УстановитьПараметр("Организация", Организация);
      Запрос.УстановитьПараметр("ДатаПроверки", ДатаПроверки);

      Возврат Не Запрос.Выполнить().Пустой();

  КонецФункции
  ```
```

**Конфигурация агента:**
```typescript
interface Implement1CAgentConfig {
  name: "1C-Implement";
  description: "Реализация функционала 1С";

  tools: [
    // Исследование
    "metadata.*",
    "code.*",
    // Генерация
    "generate.*",
    "template.*",
    "pattern.*",
    "query.*",
    // Знания
    "platform.*"
  ];

  maxTurns: 30;

  systemPrompt: `
    Ты — опытный разработчик 1С:Предприятие.

    Твоя задача — реализовать функционал по запросу пользователя.

    Правила:
    1. Сначала изучи существующий код и архитектуру
    2. Следуй стандартам разработки 1С
    3. Используй существующие механизмы БСП когда возможно
    4. Генерируй код, готовый к использованию
    5. Объясняй куда и как добавить код
    6. Проверяй синтаксис сгенерированного кода
  `;
}
```

---

### 13.3. 1C-Debug — Отладка и диагностика

**Назначение:** Поиск и исправление ошибок, анализ проблем.

**Когда использовать:**
- "Почему неправильно считается НДФЛ?"
- "Документ не проводится, выдаёт ошибку..."
- "Отчёт показывает неверные данные"
- "Найди причину расхождения в регистре"

**Доступные tools:**
- Все tools группы `metadata.*`
- Все tools группы `code.*`
- `query.parse`, `query.validate`, `query.explain`
- `runtime.*` (если подключена база)

**Workflow:**
```
1. Анализ симптомов проблемы
2. Локализация проблемного кода
3. Анализ логики
4. Поиск причины
5. Предложение исправления
```

**Конфигурация агента:**
```typescript
interface Debug1CAgentConfig {
  name: "1C-Debug";
  description: "Отладка и диагностика 1С";

  tools: [
    "metadata.*",
    "code.*",
    "query.parse",
    "query.validate",
    "query.explain",
    "query.tables",
    "runtime.query",
    "runtime.eval",
    "platform.*"
  ];

  maxTurns: 25;

  systemPrompt: `
    Ты — эксперт по отладке 1С:Предприятие.

    Твоя задача — найти и исправить проблему.

    Правила:
    1. Собери информацию о симптомах
    2. Сформулируй гипотезы
    3. Проверь каждую гипотезу анализом кода
    4. Найди корневую причину
    5. Предложи исправление с объяснением
  `;
}
```

---

### 13.4. 1C-Configure — Настройка типовой

**Назначение:** Помощь в настройке типовых конфигураций.

**Когда использовать:**
- "Как настроить обмен с бухгалтерией?"
- "Включи функционал грейдов"
- "Настрой расчёт отпусков по новым правилам"
- "Какие константы нужно заполнить для расчёта больничных?"

**Доступные tools:**
- `config.*`
- `metadata.search`, `metadata.get`
- `code.module` (для анализа логики настроек)

**Workflow:**
```
1. Определение области настройки
2. Поиск релевантных функциональных опций и констант
3. Анализ зависимостей
4. Формирование инструкции по настройке
```

**Конфигурация агента:**
```typescript
interface Configure1CAgentConfig {
  name: "1C-Configure";
  description: "Настройка типовой конфигурации";

  tools: [
    "config.options",
    "config.constants",
    "config.scheduled_jobs",
    "config.event_subscriptions",
    "config.exchanges",
    "metadata.search",
    "metadata.get",
    "code.module"
  ];

  maxTurns: 15;

  systemPrompt: `
    Ты — консультант по настройке типовых конфигураций 1С.

    Твоя задача — помочь пользователю настроить конфигурацию.

    Правила:
    1. Определи что именно нужно настроить
    2. Найди все связанные настройки
    3. Объясни влияние каждой настройки
    4. Дай пошаговую инструкцию
    5. Предупреди о возможных проблемах
  `;
}
```

---

### 13.5. Регистрация агентов

```typescript
// agents/index.ts

export const agents: AgentDefinition[] = [
  {
    name: "1C-Explore",
    subagentType: "1c-explore",
    description: "Исследование конфигурации 1С. Используй для вопросов 'как работает...', 'где находится...', 'найди логику...'",
    model: "sonnet",
    tools: [...exploreTools]
  },
  {
    name: "1C-Implement",
    subagentType: "1c-implement",
    description: "Реализация функционала. Используй для задач 'добавь...', 'создай...', 'реализуй...'",
    model: "opus",
    tools: [...implementTools]
  },
  {
    name: "1C-Debug",
    subagentType: "1c-debug",
    description: "Отладка и диагностика. Используй для 'почему не работает...', 'найди ошибку...', 'исправь...'",
    model: "sonnet",
    tools: [...debugTools]
  },
  {
    name: "1C-Configure",
    subagentType: "1c-configure",
    description: "Настройка типовой. Используй для 'настрой...', 'включи функционал...', 'какие настройки...'",
    model: "haiku",
    tools: [...configureTools]
  }
];
```

---

## 14. Интеграция Skills и Agents

### 14.1. Автоматический выбор

Claude Code автоматически выбирает между Skill и Agent:

```
┌─────────────────────────────────────────────────────────┐
│                    User Request                          │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│              Intent Classification                       │
│  • Конкретная операция → Skill                          │
│  • Исследование/анализ → 1C-Explore Agent               │
│  • Реализация → 1C-Implement Agent                      │
│  • Отладка → 1C-Debug Agent                             │
│  • Настройка → 1C-Configure Agent                       │
└─────────────────────────────────────────────────────────┘
```

### 14.2. Примеры маршрутизации

| Запрос | Выбор | Причина |
|--------|-------|---------|
| "Сгенерируй запрос для получения сотрудников" | /1c-query | Конкретная операция |
| "Покажи структуру документа БольничныйЛист" | /1c-metadata | Конкретная операция |
| "Как работает расчёт отпускных?" | 1C-Explore | Требует исследования |
| "Добавь новое начисление" | 1C-Implement | Требует реализации |
| "Почему документ не проводится?" | 1C-Debug | Требует отладки |
| "Настрой обмен с бухгалтерией" | 1C-Configure | Настройка |

### 14.3. Комбинирование

Agents могут вызывать Skills внутри своей работы:

```
1C-Implement Agent:
  │
  ├── Вызов /1c-metadata для получения структуры
  ├── Вызов /1c-usages для анализа связей
  ├── Генерация кода
  └── Вызов /1c-validate для проверки
```

---

## 15. Лицензия

MIT License

---

## 16. Ссылки

- [MCP Specification](https://spec.modelcontextprotocol.io/)
- [BSL Language Server](https://github.com/1c-syntax/bsl-language-server)
- [1C:EDT](https://edt.1c.ru/)
- [OneScript](https://oscript.io/)
- [Стандарты разработки 1С](https://its.1c.ru/db/v8std)
