# Polar Policy Generator - README

## Overview

This tool generates Polar authorization policies using OpenAI's API. It reads system prompts and sample files, sends them to OpenAI with your specific requirements, generates Polar code, validates the syntax, and optionally runs tests.

## Quick Start

### 1. Install Dependencies
```bash
pip install openai python-dotenv
```

### 2. Install Oso CLI
```bash
curl -L https://cloud.osohq.com/install.sh | bash
```

### 3. Set up Environment Variables
Create a `.env` file in your project root:
```env
OPENAI_APIKEY=your_openai_api_key_here
```

### 4. Run the Generator
```bash
python tests/your_test_file.py
```


### Directory structure
```
polar-chatbot/
├── app/
│   ├── main.py                 # Main generator script
│   ├── system_prompts/         # System instructions and samples
│   │   ├── output_instructions.mdx
│   │   ├── polar_reference.mdx
│   │   ├── sample_1.polar
│   ├── user_input/             # Your specific test prompts
│   │   └── my_custom_prompt.mdx
│   └── results/                # Generated policies
│       └── generated_policy.polar
├── tests/                      # Test runner files
│   └── your_test.polar
├── .env                        # Environment variables
└── README.md                  
```

## Adding/Editing Test Inputs

### 1. System Prompts (`app/system_prompts/`)
These files provide context and instructions to the AI.

### 2. Sample Policies (`app/system_prompts/`)
These provide examples for the AI to learn from:

**`sample_1.polar`**
```polar
actor User {}

resource Document {
    permissions = ["read", "write", "delete"];
    roles = ["owner", "editor", "viewer"];
}

allow(user: User, "read", document: Document) if
    user in document.viewer;

allow(user: User, "write", document: Document) if
    user in document.editor;

allow(user: User, "delete", document: Document) if
    user in document.owner;
```

### 3. User Inputs (`app/user_input/`)
These contain your specific requirements:

**`test_1.mdx`**
```markdown
Create a Polar policy for a SaaS application with:
1. User roles: admin, manager, employee
2. Resources: projects, documents, reports
3. Permissions: read, write, delete, share
4. Include comprehensive test cases
```

## The `run()` Function

### Function Signature
```python
def run(
    file_paths: list[str], 
    prompt: str, 
    output_directory: str = "app/results", 
    output_filename: str = "generated_policy.polar"
) -> Optional[str]
```

### Parameters
- `file_paths`: List of file paths to read (system prompts, samples, etc.)
- `prompt`: Your specific requirements for the AI
- `output_directory`: Where to save the generated file (default: "./results")
- `output_filename`: Name of the output file (default: "generated_policy.polar")

### Return Value
- `None`: Success (no validation errors)
- `str`: Error message if validation fails


## Troubleshooting

### Common Issues

1. **"oso-cloud CLI not found"**
   - Make sure Oso CLI is installed
   - Add `~/.local/bin` to your PATH

2. **"OPENAI_APIKEY not found"**
   - Check your `.env` file exists
   - Verify the API key is correct

3. **"File not found"**
   - Ensure all file paths exist
   - Check file permissions

4. **Validation errors**
   - The system will attempt to auto-fix syntax errors
   - Check the generated `.polar` file for issues

### Debugging

**Validate manually**
   ```bash
   oso-cloud validate app/results/generated_policy.polar
   oso-cloud test app/results/generated_policy.polar
   ```

## Example Workflow

1. **Create your prompt** in `app/user_input/my_requirements.mdx`
2. **Add relevant samples** to `app/system_prompts/`
3. **Run the generator**:
   ```python
   from app.main import run
   
   result = run(
       ["system_prompts/polar_reference.mdx", "system_prompts/sample_1.polar"],
       read_file("user_input/my_requirements.mdx"),
       "app/results",
       "my_policy.polar"
   )
   ```
4. **Check the generated file** in `app/results/my_policy.polar`
5. **Run tests manually** if needed:
   ```bash
   oso-cloud test app/results/my_policy.polar
   ```

This system allows you to experiment with different prompts, samples, and configurations to generate various types of Polar policies for your authorization needs.