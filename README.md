

```bash
# Initialize configuration
python -m app.cli init

# Generate policy
python -m app.cli generate --prompt-file app/user_input/test_1.mdx

# Validate policy
python -m app.cli validate --policy-file app/results/generated_policy.polar

# List available models
python -m app.cli list-models
```

