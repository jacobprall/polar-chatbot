```bash
# Install oso cli
curl -L https://cloud.osohq.com/install.sh | bash

# Install dependencies
pip install -r requirements.txt

# Initialize configuration
python -m app.cli init

# Generate policy
python -m app.cli generate --prompt-file data/user_requirements/test_1.mdx

# Validate policy
python -m app.cli validate --policy-file results/generated_policy.polar

# List available models
python -m app.cli list-models
```

