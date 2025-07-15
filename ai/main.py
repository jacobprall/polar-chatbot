import os
from openai import OpenAI
from typing import Optional
import subprocess



def call_openai(system_prompt: str, user_input: str, model: str = "gpt-3.5-turbo") -> Optional[str]:
    """
    Make a call to OpenAI API with the given system prompt and user input.
    
    Args:
        system_prompt (str): The system prompt to set the context
        user_input (str): The user's input/message
        model (str): The OpenAI model to use (default: gpt-3.5-turbo)
    
    Returns:
        Optional[str]: The response from OpenAI, or None if there's an error
    """
    try:
        # Initialize the OpenAI client
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
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

def read_mdx_file(file_path: str) -> Optional[str]:
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
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error running oso-cloud validate: {e}")
        print(f"stderr: {e.stderr}")
        return None
    except FileNotFoundError:
        print("Error: oso-cloud CLI not found. Make sure it's installed and in your PATH")
        return None
    except Exception as e:
        print(f"Unexpected error running oso-cloud validate: {e}")
        return None

