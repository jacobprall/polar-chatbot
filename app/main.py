import os
from openai import OpenAI
from typing import Optional
from dotenv import load_dotenv
import subprocess

load_dotenv()

def read_file(file_path: str) -> Optional[str]:
    """
    Read an MDX file and return its content as a string.
    
    Args:
        file_path (str): Path to the MDX file to read
    
    Returns:
        Optional[str]: The content of the MDX file as a string, or None if there's an error
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        return content
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found")
        return None
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


def write_polar_file(content: str, directory: str, filename: str = "policy.polar") -> Optional[str]:
    """
    Write a string to a .polar file in the specified directory.
    
    Args:
        content (str): The content to write to the .polar file
        directory (str): The directory where the .polar file should be created
        filename (str): The name of the .polar file (default: "policy.polar")
    
    Returns:
        Optional[str]: The full path to the created file, or None if there's an error
    """
    try:
        # Ensure the directory exists
        os.makedirs(directory, exist_ok=True)
        
        # Create the full file path
        file_path = os.path.join(directory, filename)
        
        # Ensure the filename ends with .polar
        if not filename.endswith('.polar'):
            file_path += '.polar'
        
        # Write the content to the file
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(content)
        
        print(f"Successfully wrote .polar file to: {file_path}")
        return file_path
        
    except PermissionError:
        print(f"Error: Permission denied when writing to directory '{directory}'")
        return None
    except Exception as e:
        print(f"Error writing .polar file: {e}")
        return None

def retry_on_error(polar_code: str, error_message: str) -> Optional[str]:
    """
    Retry fixing polar code when validation fails by sending the error to OpenAI.
    
    Args:
        polar_code (str): The original polar code that failed validation
        error_message (str): The error message from validation
    
    Returns:
        Optional[str]: The fixed polar code, or None if fixing failed
    """
    try:
        fix_prompt = read_file("./system_prompts/handle_error.mdx")
        user_input = f"{fix_prompt} \n {error_message} \n {polar_code})"
        # Call OpenAI to fix the code
        print("Attempting to fix Polar syntax error...")
        fixed_code = call_openai(
            system_prompt="You are a Polar policy syntax expert. Fix syntax errors in Polar code and return only the corrected code.",
            user_input=user_input
        )
        
        if fixed_code is None:
            print("Error: Failed to get fix from OpenAI API.")
            return None
        
        print("Code fix attempt completed.")
        return fixed_code
        
    except Exception as e:
        print(f"Error in retry_on_error function: {e}")
        return None


def validate_polar_syntax(file_path: str) -> Optional[str]:
    """
    Validate a file using the oso-cloud CLI validate function.
    
    Args:
        file_path (str): Path to the file to validate
    
    Returns:
        Optional[str]: The validation result from oso-cloud CLI, or None if there's an error
    """
    try:
        # Run the oso-cloud validate command
        result = subprocess.run(
            ["oso-cloud", "validate", file_path],
            capture_output=True,
            text=True,
            check=True
        )
        return None
    except subprocess.CalledProcessError as e:
        print(f"Error running oso-cloud validate: {e}")
        print(f"stderr: {e.stderr}")
        print("Retrying with added context")
        return e.stderr
    except FileNotFoundError:
        print("Error: oso-cloud CLI not found. Make sure it's installed and in your PATH")
        return None
    except Exception as e:
        print(f"Unexpected error running oso-cloud validate: {e}")
        return None


def run(file_paths: list[str], prompt: str, output_directory: str = "./policies", output_filename: str = "generated_policy.polar") -> None:
    """
    Read files from paths, concatenate them, send to OpenAI with prompt, 
    write result to .polar file, and validate it.
    
    Args:
        file_paths (list[str]): List of file paths to read
        prompt (str): The prompt to send to OpenAI along with the concatenated file contents
        output_directory (str): Directory to write the .polar file to (default: "./policies")
        output_filename (str): Name of the output .polar file (default: "generated_policy.polar")
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
            return
        
        # Step 2: Call OpenAI with the concatenated content as system prompt
        print("Calling OpenAI API...")
        openai_response = call_openai(concatenated_content, prompt)
        
        if openai_response is None:
            print("Error: Failed to get response from OpenAI API.")
            return
        
        # Step 3: Write the OpenAI response to a .polar file
        print("Writing response to .polar file...")
        file_path = write_polar_file(openai_response, output_directory, output_filename)
        
        if file_path is None:
            print("Error: Failed to write .polar file.")
            return
        
        # Step 4: Validate the generated .polar file
        print("Validating .polar file...")
        validation_result = validate_polar_syntax(file_path)
        
        if validation_result is not None:
            print("Error: Failed to validate .polar file.")
            retry_on_error(read_file(file_path), validation_result)
            retry_validation_result = validate_polar_syntax(file_path)
            print(f"Retry validation result: {retry_validation_result}")

            return
        
        print("Validation successful!")
        print(f"Validation result: {validation_result}")
        
        print("Complete")
        
    except Exception as e:
        print(f"Unexpected error in run function: {e}")
        return
