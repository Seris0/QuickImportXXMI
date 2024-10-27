import re
import os
import importlib

def find_and_import_xxmi_tools():
    # Get the parent directory of the current file's directory
    parent_directory = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    pattern = r'XXMI[-_]?Tools'

    def find_matching_directory(root_dir):
        for root, dirs, _ in os.walk(root_dir):
            for directory in dirs:
                if re.search(pattern, directory, re.IGNORECASE):
                    return os.path.join(root, directory)
        return None

    # Start searching from the parent directory
    matching_directory = find_matching_directory(parent_directory)

    if matching_directory is None:
        raise ImportError("XXMI Tools module not found.")

    # Convert the matching directory to a module import path
    relative_path = os.path.relpath(matching_directory, parent_directory)
    module_name = relative_path.replace(os.path.sep, '.') + ".migoto.operators"

    try:
        module = importlib.import_module(module_name)
        return getattr(module, 'Import3DMigotoFrameAnalysis'), getattr(module, 'Import3DMigotoRaw')
    except ImportError as e:
        print(f"Error importing module: {e}")
    except AttributeError as e:
        print(f"Error finding 'Import3DMigotoFrameAnalysis' or 'Import3DMigotoRaw': {e}")
    
    return None, None

# Initialize the imports
Import3DMigotoFrameAnalysis, Import3DMigotoRaw = find_and_import_xxmi_tools()