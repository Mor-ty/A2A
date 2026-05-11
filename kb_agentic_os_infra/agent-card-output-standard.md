# Agent Card Output Standard

Define how agents produce and expose output for consumption by other agents in a chain.

## Minimal Setup Basic Examples

### Simple String Output
```python
out_status = SkillOutputParameter(
    name="status",
    data_type=DataType.STRING,
    description="Execution status",
    required=True
)
```

### Array Output
```python
out_results = SkillOutputParameter(
    name="test_results",
    data_type=DataType.ARRAY,
    description="List of test results",
    required=True,
    config=OutputConfig(
        sample=[{"test": "login", "passed": True}]
    )
)
```

### Object Output
```python
out_summary = SkillOutputParameter(
    name="execution_summary",
    data_type=DataType.OBJECT,
    description="Summary of execution",
    required=True
)
```

## Advanced Examples

### Structured JSON Output with Schema
```python
out_report = SkillOutputParameter(
    name="test_report",
    data_type=DataType.JSON,
    description="Complete test execution report",
    required=True,
    config=OutputConfig(
        schema={
            "type": "object",
            "properties": {
                "total_tests": {"type": "number"},
                "passed": {"type": "number"},
                "failed": {"type": "number"},
                "tests": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "status": {"type": "string", "enum": ["pass", "fail"]},
                            "duration": {"type": "number"}
                        }
                    }
                }
            },
            "required": ["total_tests", "passed", "failed"]
        },
        sample={
            "total_tests": 10,
            "passed": 8,
            "failed": 2,
            "tests": [
                {"name": "test_login", "status": "pass", "duration": 1.2},
                {"name": "test_logout", "status": "fail", "duration": 0.8}
            ]
        }
    )
)
```
**What it does:** Validates output structure before passing to next agent. Provides schema so downstream agents know what to expect.

### File Output
```python
out_artifacts = SkillOutputParameter(
    name="generated_files",
    data_type=DataType.ARRAY,
    description="Generated artifact files",
    required=False,
    config=OutputConfig(
        sample=["test_login.py", "test_logout.py", "test_data.json"]
    )
)
```
**What it does:** Produces list of files created. Other agents can consume these files as input.

### Conditional Output

### Conditional Outputs (Different Based on Mode)
```python
# Same agent produces DIFFERENT outputs based on input parameter
# Input parameter: generation_mode (enum: "robot" or "pytest")

out_robot_script = SkillOutputParameter(
    name="robot_script",
    data_type=DataType.STRING,
    description="Generated Robot Framework script",
    required=False  # Only if mode = 'robot'
)

out_pytest_script = SkillOutputParameter(
    name="pytest_script",
    data_type=DataType.STRING,
    description="Generated pytest Python script",
    required=False  # Only if mode = 'pytest'
)

# Both in same enrichment - agent chooses which to populate
skill = AgentSkill(id="test_generator", name="Test Generator")
extended_card = AgentCard(
    skills=[skill],
    skill_output_enrichments={
        skill.id: SkillOutputEnrichment(
            outputs=[
                out_robot_script,  # Populated if generation_mode='robot'
                out_pytest_script   # Populated if generation_mode='pytest'
            ]
        )
    }
)
```
**What it does:** Agent produces EITHER `robot_script` OR `pytest_script` depending on the `generation_mode` input parameter. Both are defined in outputs, but only one gets populated at runtime. Next agent checks which output exists before consuming it.

## Assign Outputs to Skills

```python
skill = AgentSkill(
    id="test_executor",
    name="Test Executor",
    description="Runs tests"
)

extended_card = AgentCard(
    id="test_agent",
    name="Test Agent",
    skills=[skill],
    skill_enrichments={...},  # inputs
    skill_output_enrichments={
        skill.id: SkillOutputEnrichment(
            outputs=[out_status, out_results, out_report]
        )
    }
)
```

---

### Simple String Output

| Field | Type | Description |
|-------|------|-------------|
| `name` | str | Output identifier (required) |
| `data_type` | DataType | One of 8 types |
| `description` | str | What this output contains |
| `required` | bool | Always produced? Default: True |
| `config` | OutputConfig | Schema, format, sample |

## Output Config Reference

| Config | Purpose | Example |
|--------|---------|---------|
| `schema` | JSON Schema validation | Full schema definition |
| `format` | Output format hint | "json", "csv", "xml" |
| `sample` | Example output | `{"status": "pass"}` |
