import os
from pathlib import Path
from typing import Optional

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