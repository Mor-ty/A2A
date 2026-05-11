# Agent Card Input Parameter Standard

Define how agents receive and validate input through a structured parameter system.

## Minimal Setup Basic Examples

### Simple String
```python
p_name = SkillInputParameter(
    name="project_name",
    data_type=DataType.STRING,
    description="Name of the project",
    sample="my-awesome-project",
    required=True
)
```

### Number with Range
```python
p_count = SkillInputParameter(
    name="iteration_count",
    data_type=DataType.NUMBER,
    description="Number of iterations",
    sample=5,
    config=InputConfig(min_value=1, max_value=100)
)
```

### Dropdown/Enum
```python
p_mode = SkillInputParameter(
    name="execution_mode",
    display_name="Execution Mode", 
    data_type=DataType.ENUM,
    description="How to execute",
    sample="staging",
    config=InputConfig(options=["dev", "staging", "prod"]),  # Fixed list of choices
    default_value="dev"  # Pre-select this option
)
```
**What it does:** User sees a dropdown with 3 fixed options. They **must** pick one. Defaults to "dev" if not specified.

### Dynamic Parameter with Display Name
```python
p_projects = SkillInputParameter(
    name="project_id",
    display_name="Select Project", 
    data_type=DataType.ARRAY,
    description="Available project",
    sample="proj-123",
    source_priority=[DataSource.AGENT, DataSource.USER],
    config=InputConfig(
        dynamic=True  # This parameter should be resolved dynamically at runtime
    )
)
```
**What it does:** UI displays "Select Project" instead of "project_id". The `dynamic=True` flag signals that this parameter's value should be fetched at runtime by the agent. The agent will use its configuration layer to retrieve available options.

## Advanced Examples

### Default Value vs Static Value

**`default_value`** - Suggested value, user can change it
```python
p_branch = SkillInputParameter(
    name="branch_name",
    data_type=DataType.STRING,
    description="Git branch",
    sample="main",
    default_value="main"  # Pre-filled, but user can change it
)
```
User sees: `[main]` but can type something else like `develop`

**`static_value`** - Fixed value, user cannot change it
```python
p_api_version = SkillInputParameter(
    name="api_version",
    data_type=DataType.STRING,
    description="API version",
    sample="v2.0",
    static_value="v2.0"  # Always v2.0, no user choice
)
```
User sees: Nothing to input. Always uses `v2.0`

**When to use:**
- `default_value` - User usually needs this value, but might override it occasionally
- `static_value` - Never ask user, always use this (hardcoded config)

---

### String with Validation
```python
p_repo = SkillInputParameter(
    name="repository_url",
    data_type=DataType.STRING,
    description="Git repository URL",
    sample="https://github.com/company/repo.git",
    config=InputConfig(
        pattern="^https?://.*\\.git$",  # Must match this regex
        custom_validators=["valid_git_url"]  # Run custom validation
    ),
    source_priority=[DataSource.BLUEPRINT, DataSource.ENV, DataSource.USER]
)
```
**What it does:** Validates input is a valid Git URL. Tries blueprint config first, then environment variable, then asks user. Rejects invalid URLs.

### Array with Options
```python
p_environments = SkillInputParameter(
    name="environments",
    data_type=DataType.ARRAY,
    description="Target environments",
    sample=["dev", "staging"],
    config=InputConfig(
        options=["dev", "staging", "prod"],  # Can only pick these
        min_value=1,  # At least 1 item required
        max_value=3   # Can't pick more than 3
    )
)
```
**What it does:** User multi-selects from 3 fixed options. Must pick 1-3 items. Can't be empty or exceed 3.

### Dependent Parameter
```python
p_branch = SkillInputParameter(
    name="branch_name",
    data_type=DataType.STRING,
    description="Git branch",
    sample="main",
    default_value="main",
    dependent_on="repository_url",  # Only required if repository_url is provided
    config=InputConfig(pattern="^[a-z0-9_/-]+$")
)
```
**What it does:** Only appears/required if `repository_url` is filled. Uses "main" as default. Validates branch name format.

### Static Value (No User Input)
```python
p_api_version = SkillInputParameter(
    name="api_version",
    data_type=DataType.STRING,
    description="API version",
    sample="v2.0",
    static_value="v2.0",  # Always use this value
    source_priority=[DataSource.BLUEPRINT]
)
```
**What it does:** Never asks user. Always uses "v2.0". Useful for hardcoded config that shouldn't change.

### Complex Object
```python
p_config = SkillInputParameter(
    name="alm_details",
    data_type=DataType.OBJECT,
    description="ALM configuration",
    sample={"ProjectID": 12345, "ProjectName": "MyProject", "ALMType": "Jira"},
    config=InputConfig(
        schema={  # Full JSON Schema validation
            "type": "object",
            "properties": {
                "ProjectID": {"type": "number"},
                "ProjectName": {"type": "string"},
                "ALMType": {"type": "string", "enum": ["Jira", "Octane", "ADO"]}
            },
            "required": ["ProjectID"]  # Must include ProjectID
        }
    )
)
```
**What it does:** Accepts complex nested object. Validates structure against JSON schema. Requires ProjectID field. Validates ALMType is one of 3 options.

## Assign Parameters to Skills

```python
skill = AgentSkill(
    id="my_skill",
    name="My Skill",
    description="Does something"
)

extended_card = AgentCard(
    id="my_agent",
    name="My Agent",
    description="An agent",
    skills=[skill],
    skill_input_enrichments={
        skill.id: SkillInputEnrichment(
            parameters=[p_name, p_count, p_mode]
        )
    }
)
```

## Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `name` | str | Parameter identifier (required) |
| `display_name` | str | Human-friendly name for UI display - defaults to name if not provided |
| `data_type` | DataType | One of 8 types: string, number, bool, object, array, file, datetime, enum |
| `description` | str | User-friendly description (required) |
| `required` | bool | Is this required? Default: True |
| `default_value` | Any | Fallback value if not provided |
| `sample` | Any | Example value showing expected format (required) |
| `static_value` | Any | Fixed value - never ask user |
| `source_priority` | List[DataSource] | Order to try: user → blueprint → env → agent |
| `dependent_on` | str | Parameter name this depends on |
| `config` | InputConfig | Type-specific validation rules |

## Config Field Reference

| Config | Types | Example |
|--------|-------|---------|
| `dynamic` | all | `True` - Parameter should be resolved at runtime |
| `options` | enum, array, string | `["a", "b", "c"]` |
| `pattern` | string | `"^https?://.*"` |
| `min_value` | number, string, array | `1` (min length/value/items) |
| `max_value` | number, string, array | `100` |
| `custom_validators` | string | `["valid_git_url"]` |
| `file_extensions` | file | `[".pdf", ".docx"]` |
| `schema` | object | Full JSON schema |

## Data Source Priority

Try in this order:
1. **user** - User provides at runtime
2. **blueprint** - From agent blueprint config
3. **env** - From environment variable
4. **agent** - Fetched/computed by agent at runtime

Default: `[DataSource.USER]`

---

## Using DataSource.AGENT

When you need to fetch values at runtime (from APIs, databases, other agents, etc.), use `DataSource.AGENT`:

```python
p_project_ids = SkillInputParameter(
    name="project_ids",
    data_type=DataType.ARRAY,
    description="Available project IDs",
    sample=[101, 102],
    source_priority=[DataSource.AGENT, DataSource.USER]
)
```

