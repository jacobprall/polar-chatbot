import os
from openai import OpenAI
from typing import Optional
from dotenv import load_dotenv
import subprocess
from pathlib import Path

load_dotenv()

def resolve_file_path(file_path: str, base_dir: str = None) -> Optional[Path]:
    """
    Resolve a file path to an absolute Path object.
    
    Args:
        file_path (str): The file path (can be relative or absolute)
        base_dir (str): Base directory for relative paths (default: current working directory)
    
    Returns:
        Optional[Path]: Resolved absolute Path object, or None if file doesn't exist
    """
    try:
        if base_dir is None:
            base_dir = os.getcwd()
        
        # Convert to Path object
        path = Path(file_path)
        
        # If it's already absolute, use as is
        if path.is_absolute():
            resolved_path = path
        else:
            # Resolve relative to base directory
            resolved_path = Path(base_dir) / path
        
        # Check if file exists
        if resolved_path.exists():
            return resolved_path.resolve()
        else:
            print(f"Error: File '{file_path}' not found at {resolved_path}")
            return None
            
    except Exception as e:
        print(f"Error resolving file path '{file_path}': {e}")
        return None

def find_file_by_name(filename: str, search_dirs: list[str] = None) -> Optional[Path]:
    """
    Find a file by name in specified directories or current directory tree.
    
    Args:
        filename (str): The name of the file to find
        search_dirs (list[str]): Directories to search in (default: current directory)
    
    Returns:
        Optional[Path]: Absolute Path to the file, or None if not found
    """
    try:
        if search_dirs is None:
            search_dirs = [os.getcwd()]
        
        for search_dir in search_dirs:
            search_path = Path(search_dir)
            if search_path.exists():
                for file_path in search_path.rglob(filename):
                    if file_path.is_file():
                        return file_path.resolve()
        
        print(f"Error: File '{filename}' not found in search directories")
        return None
        
    except Exception as e:
        print(f"Error finding file '{filename}': {e}")
        return None

def read_file(file_path: str, base_dir: str = None) -> Optional[str]:
    """
    Read a file and return its content as a string.
    
    Args:
        file_path (str): Path to the file to read (can be relative or absolute)
        base_dir (str): Base directory for relative paths
    
    Returns:
        Optional[str]: The content of the file as a string, or None if there's an error
    """
    try:
        # Resolve the file path
        resolved_path = resolve_file_path(file_path, base_dir)
        if resolved_path is None:
            return None
        
        # Read the file
        with open(resolved_path, 'r', encoding='utf-8') as file:
            content = file.read()
        return content
        
    except Exception as e:
        print(f"Error reading file '{file_path}': {e}")
        return None

def call_openai(system_prompt: str, user_input: str, model: str = "gpt-4.1") -> Optional[str]:
    """
    Make a call to OpenAI API with the given system prompt and user input.
    
    Args:
        system_prompt (str): The system prompt to set the context
        user_input (str): The user's input/message
        model (str): The OpenAI model to use (default: gpt-4.1)
    
    Returns:
        Optional[str]: The response from OpenAI, or None if there's an error
    """
    try:
        # Initialize the OpenAI client
        client = OpenAI(api_key=os.getenv("OPENAI_APIKEY"))
        
        # Make the API call
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ]
        )
        
        # Extract and return the response content
        return response.choices[0].message.content
        
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        return None

def write_polar_file(content: str, directory: str, filename: str = "policy.polar") -> Optional[Path]:
    """
    Write a string to a .polar file in the specified directory.
    
    Args:
        content (str): The content to write to the .polar file
        directory (str): The directory where the .polar file should be created
        filename (str): The name of the .polar file (default: "policy.polar")
    
    Returns:
        Optional[Path]: The full Path to the created file, or None if there's an error
    """
    try:
        # Clean up the content (remove markdown formatting if present)
        cleaned_content = content.strip()
        if cleaned_content.startswith("```polar"):
            cleaned_content = cleaned_content[8:]
        elif cleaned_content.startswith("```"):
            cleaned_content = cleaned_content[3:]
        if cleaned_content.endswith("```"):
            cleaned_content = cleaned_content[:-3]
        cleaned_content = cleaned_content.strip()
        
        # Create directory path
        dir_path = Path(directory)
        dir_path.mkdir(parents=True, exist_ok=True)
        
        # Create file path
        file_path = dir_path / filename
        
        # Ensure the filename ends with .polar
        if not filename.endswith('.polar'):
            file_path = file_path.with_suffix('.polar')
        
        # Write the content to the file
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(cleaned_content)
        
        print(f"Successfully wrote .polar file to: {file_path}")
        return file_path.resolve()
        
    except Exception as e:
        print(f"Error writing .polar file: {e}")
        return None

def retry_on_error(file_path: str, error_message: str) -> Optional[str]:
    """
    Retry fixing polar code when validation fails by sending the error to OpenAI.
    
    Args:
        polar_code (str): The original polar code that failed validation
        error_message (str): The error message from validation
    
    Returns:
        Optional[str]: The fixed polar code, or None if fixing failed
    """
    try:
        # Find the handle_error.mdx file
        handle_error_path = find_file_by_name("handle_error.mdx")
        fix_prompt = read_file(str(handle_error_path))
        print(f"fix prompt {fix_prompt}")
        polar_code = read_file(str(file_path))
        if fix_prompt is None:
            return None
        
        user_input = f"{fix_prompt}\n{error_message}\n{polar_code}"
        
        # Call OpenAI to fix the code
        print("Attempting to fix Polar syntax error...")
        fixed_code = call_openai(
            system_prompt="You are a Polar policy syntax expert. Fix syntax errors in Polar code and return only the corrected code.",
            user_input=user_input
        )
        
        if fixed_code is None:
            print("Error: Failed to get fix from OpenAI API.")
        
        return fixed_code
        
    except Exception as e:
        print(f"Error in retry_on_error function: {e}")
        return None

def run_cli_command(command: list[str], command_name: str) -> Optional[str]:
    """
    Run a CLI command and handle common errors.
    
    Args:
        command (list[str]): The command to run
        command_name (str): Name of the command for error messages
    
    Returns:
        Optional[str]: Command output or error message
    """
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True
        )
        return None
    except subprocess.CalledProcessError as e:
        print(f"Error running {command_name}: {e}")
        print(f"stderr: {e.stderr}")
        return e.stderr
    except FileNotFoundError:
        print(f"Error: {command_name} not found. Make sure it's installed and in your PATH")
        return None
    except Exception as e:
        print(f"Unexpected error running {command_name}: {e}")
        return None

def validate_polar_syntax(file_path: str) -> Optional[str]:
    """
    Validate a file using the oso-cloud CLI validate function.
    
    Args:
        file_path (str): Path to the file to validate
    
    Returns:
        Optional[str]: The validation result from oso-cloud CLI, or None if there's an error
    """
    resolved_path = resolve_file_path(file_path)
    if resolved_path is None:
        return "File not found"
    
    return run_cli_command(["oso-cloud", "validate", str(resolved_path)], "oso-cloud validate")

def run(file_paths: list[str], prompt: str, output_directory: str = "./results", output_filename: str = "generated_policy.polar") -> Optional[str]:
    """
    Read files from paths, concatenate them, send to OpenAI with prompt, 
    write result to .polar file, and validate it.
    
    Args:
        file_paths (list[str]): List of file paths to read
        prompt (str): The prompt to send to OpenAI along with the concatenated file contents
        output_directory (str): Directory to write the .polar file to
        output_filename (str): Name of the output .polar file
    
    Returns:
        Optional[str]: Error message if validation fails, None if successful
    """
    try:
        # Step 1: Read and concatenate all files
        concatenated_content = ""
        for file_path in file_paths:
            content = read_file(file_path)
            if content is None:
                print(f"Error: Could not read file '{file_path}'. Skipping...")
                continue
            concatenated_content += content + "\n\n"
        
        if not concatenated_content.strip():
            print("Error: No valid content was read from any of the provided files.")
            return "No valid content found"
        
        # Step 2: Call OpenAI with the concatenated content as system prompt
        print("Calling OpenAI API...")
        openai_response = call_openai(concatenated_content, prompt)
        
        if openai_response is None:
            print("Error: Failed to get response from OpenAI API.")
            return "OpenAI API call failed"
        
        # Step 3: Write the OpenAI response to a .polar file
        print("Writing response to .polar file...")
        file_path = write_polar_file(openai_response, output_directory, output_filename)
        
        if file_path is None:
            print("Error: Failed to write .polar file.")
            return "Failed to write .polar file"
        
        # Step 4: Validate the generated .polar file
        print("Validating .polar file...")
        validation_result = validate_polar_syntax(str(file_path))
        
        if validation_result is None:
            print("Validation success")
            return

        print("Validation failed, attempting to fix...")
        # Try to fix the code
        fixed_code = retry_on_error(file_path, validation_result)
        if fixed_code:
            # Write the fixed code
            fixed_file_path = write_polar_file(fixed_code, output_directory, f"fixed_{output_filename}")

            # Validate the fixed code
            validation_result = validate_polar_syntax(str(fixed_file_path))
            if not validation_result:
                print("Fixed code validation successful!")
                return
            else:
                print(f"{validation_result}")
        return
        
    except Exception as e:
        print(f"Unexpected error in run function: {e}")
        return


default_system_prompts = [
    "app/system_prompts/output_instructions.mdx", 
    "app/system_prompts/polar_reference.mdx", 
    "app/system_prompts/polar_syntax.mdx",
    "app/system_prompts/sample_1.polar"
]