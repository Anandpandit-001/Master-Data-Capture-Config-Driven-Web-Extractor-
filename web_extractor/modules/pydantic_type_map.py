from typing import Any, List, Optional

# A mapping from config string types to a tuple of (Python Type, Default Value)
# for dynamic Pydantic model creation. `...` means the field is required.
PYTHON_TYPE_MAP = {
    "string": (Optional[str], None),
    "list[string]": (Optional[List[str]], None),
    "integer": (Optional[int], None),
    "float": (Optional[float], None),
    "any": (Any, ...),
}