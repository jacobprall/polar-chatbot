# How to Guide: Running main.py

## Overview

The `main.py` file contains a Polar policy generation system that:
1. Reads system prompts and sample files
2. Sends them to OpenAI with a user prompt
3. Generates Polar policy code
4. Validates the generated code
5. Saves results to a file

## Prerequisites

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

## Running the Script

### Basic Usage
```bash
python main.py
```

This runs the default `test_run()` function with predefined files.

## Understanding the `run` Function

```python
def run(file_paths: list[str], prompt: str, output_directory: str = "./results", output_filename: str = "generated_policy.polar")
```

**Parameters:**
- `file_paths`: List of file paths to read (system prompts, samples, etc.)
- `prompt`: Your specific request for the AI
- `output_directory`: Where to save the generated file (default: "./results")
- `output_filename`: Name of the output file (default: "generated_policy.polar")

The function will validate if the polar policy is syntactically correct. If it isn't, there is a single retry mechanism that feeds in the error code.

## Creating Different Tests
Using this script, you can update any of the inputs into the LLM, including additional Sample files and custom prompts

## Ideas to explore
* Add lengthy and highly-curated sample files
* Try different formats and complexity for user input, with varying degrees of completeness
* Modify system prompts to steer consistently broken behavior (negation, fact "=" assignment)

To modify the tests, make sure to update your test Function
```python
def ecommerce_test():
    run(
        [
            "./system_prompts/output_instructions.mdx",
            "./system_prompts/polar_reference.mdx",
            "./system_prompts/sample_1.polar",
            "./system_prompts/sample_2.polar",
            "./system_prompts/sample_3.polar"  # New sample
        ],
        read_file("./user_input/ecommerce_prompt.mdx"),
        "./results",
        "ecommerce_policy.polar"
    )

if __name__ == "__main__":
    ecommerce_test()
```

## File Structure

```
polar-chatbot/
├── main.py
├── .env
├── system_prompts/
│   ├── output_instructions.mdx
│   ├── polar_reference.mdx
│   ├── polar_syntax.mdx
│   ├── sample_1.polar
│   ├── sample_2.polar
│   └── sample_3.polar
├── user_input/
│   ├── test_1.mdx
│   └── ecommerce_prompt.mdx
└── results/
    └── generated_policy.polar
```

## Troubleshooting

### Common Issues:

1. **"oso-cloud CLI not found"**
   - Make sure you installed the Oso CLI correctly
   - Add `~/.local/bin` to your PATH

2. **"OPENAI_APIKEY not found"**
   - Check your `.env` file exists
   - Verify the API key is correct

3. **"File not found"**
   - Ensure all file paths in your test function exist
   - Check file permissions

4. **Validation errors**
   - The system will attempt to auto-fix syntax errors
   - Check the generated `.polar` file for issues

## Best Practices

1. **Use descriptive filenames** for your output files
2. **Include timestamps** in filenames for versioning
3. **Test with small prompts first** before complex ones
4. **Review generated policies** before using in production
5. **Keep your system prompts updated** with the latest Polar syntax

## Example Workflow

1. Create your prompt in `user_input/my_prompt.mdx`
2. Add relevant samples to `system_prompts/`
3. Create a test function in `main.py`
4. Run: `python main.py`
5. Check the generated file in `results/`
6. Validate the policy manually if needed

This system allows you to experiment with different prompts, samples, and configurations to generate various types of Polar policies for your authorization needs.