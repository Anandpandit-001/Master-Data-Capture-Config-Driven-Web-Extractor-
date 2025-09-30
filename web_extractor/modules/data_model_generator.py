from typing import Dict, Type, Any
from pydantic import BaseModel, create_model
from .pydantic_type_map import PYTHON_TYPE_MAP


def create_scraped_data_model(schema: Dict[str, Any]) -> Type[BaseModel]:
    """Dynamically creates a Pydantic model from the extraction schema."""
    field_definitions = {}
    for field_name, details in schema.items():
        # Pydantic's create_model expects a tuple of (type, default_value)
        # We use a helper map to convert our YAML type strings to Python types
        field_type_info = PYTHON_TYPE_MAP.get(details.type.lower(), (Any, ...))
        field_definitions[field_name] = field_type_info

    # The ** unpacks the dictionary into keyword arguments for create_model
    return create_model('ScrapedDataModel', **field_definitions)