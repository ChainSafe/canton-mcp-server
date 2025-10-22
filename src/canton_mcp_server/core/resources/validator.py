"""
Schema Validator for Canton Canonical Resources

Validates YAML resource files against JSON schemas.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import jsonschema
import yaml

logger = logging.getLogger(__name__)


class SchemaValidationError(Exception):
    """Raised when schema validation fails"""
    
    def __init__(self, message: str, errors: List[str] = None):
        super().__init__(message)
        self.errors = errors or []


class ResourceSchemaValidator:
    """Validates resource files against JSON schemas"""
    
    def __init__(self, schemas_dir: str = "schemas"):
        self.schemas_dir = Path(schemas_dir)
        self._schemas: Dict[str, Dict[str, Any]] = {}
        self._load_schemas()
    
    def _load_schemas(self) -> None:
        """Load all JSON schemas from the schemas directory"""
        if not self.schemas_dir.exists():
            logger.warning(f"Schemas directory not found: {self.schemas_dir}")
            return
        
        schema_files = {
            "pattern": "pattern.schema.json",
            "anti-pattern": "anti-pattern.schema.json", 
            "rule": "rule.schema.json",
            "doc": "doc.schema.json"
        }
        
        for resource_type, filename in schema_files.items():
            schema_path = self.schemas_dir / filename
            if schema_path.exists():
                try:
                    with open(schema_path, 'r', encoding='utf-8') as f:
                        schema = json.load(f)
                    self._schemas[resource_type] = schema
                    logger.debug(f"Loaded schema for {resource_type}")
                except (json.JSONDecodeError, IOError) as e:
                    logger.error(f"Failed to load schema {schema_path}: {e}")
            else:
                logger.warning(f"Schema file not found: {schema_path}")
    
    def validate_resource(self, resource_data: Dict[str, Any], resource_type: str) -> bool:
        """
        Validate resource data against the appropriate schema
        
        Args:
            resource_data: The resource data to validate
            resource_type: Type of resource (pattern, anti-pattern, rule, doc)
            
        Returns:
            True if validation passes
            
        Raises:
            SchemaValidationError: If validation fails
        """
        if resource_type not in self._schemas:
            raise SchemaValidationError(f"No schema found for resource type: {resource_type}")
        
        schema = self._schemas[resource_type]
        
        try:
            jsonschema.validate(resource_data, schema)
            logger.debug(f"Schema validation passed for {resource_type} resource")
            return True
        except jsonschema.ValidationError as e:
            errors = self._format_validation_errors(e)
            error_msg = f"Schema validation failed for {resource_type} resource: {e.message}"
            logger.error(error_msg)
            raise SchemaValidationError(error_msg, errors)
        except jsonschema.SchemaError as e:
            error_msg = f"Schema error for {resource_type}: {e.message}"
            logger.error(error_msg)
            raise SchemaValidationError(error_msg)
    
    def validate_yaml_file(self, file_path: Path, resource_type: str) -> bool:
        """
        Validate a YAML file against the appropriate schema
        
        Args:
            file_path: Path to the YAML file
            resource_type: Type of resource (pattern, anti-pattern, rule, doc)
            
        Returns:
            True if validation passes
            
        Raises:
            SchemaValidationError: If validation fails
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            if not data:
                raise SchemaValidationError(f"Empty YAML file: {file_path}")
            
            return self.validate_resource(data, resource_type)
            
        except yaml.YAMLError as e:
            error_msg = f"YAML parsing error in {file_path}: {e}"
            logger.error(error_msg)
            raise SchemaValidationError(error_msg)
        except IOError as e:
            error_msg = f"Failed to read file {file_path}: {e}"
            logger.error(error_msg)
            raise SchemaValidationError(error_msg)
    
    def _format_validation_errors(self, error: jsonschema.ValidationError) -> List[str]:
        """Format validation errors into a readable list"""
        errors = []
        
        def _collect_errors(err: jsonschema.ValidationError, path: str = ""):
            current_path = f"{path}.{err.relative_path[0]}" if err.relative_path else path
            if not current_path:
                current_path = "root"
            
            error_msg = f"{current_path}: {err.message}"
            errors.append(error_msg)
            
            for suberror in err.context:
                _collect_errors(suberror, current_path)
        
        _collect_errors(error)
        return errors
    
    def get_schema(self, resource_type: str) -> Optional[Dict[str, Any]]:
        """Get the schema for a resource type"""
        return self._schemas.get(resource_type)
    
    def list_supported_types(self) -> List[str]:
        """List all supported resource types"""
        return list(self._schemas.keys())
    
    def is_schema_loaded(self, resource_type: str) -> bool:
        """Check if a schema is loaded for the given resource type"""
        return resource_type in self._schemas


# Global validator instance
_validator: Optional[ResourceSchemaValidator] = None


def get_validator() -> ResourceSchemaValidator:
    """Get the global schema validator instance"""
    global _validator
    if _validator is None:
        _validator = ResourceSchemaValidator()
    return _validator


def validate_resource_data(data: Dict[str, Any], resource_type: str) -> bool:
    """Validate resource data using the global validator"""
    validator = get_validator()
    return validator.validate_resource(data, resource_type)


def validate_yaml_file(file_path: Union[str, Path], resource_type: str) -> bool:
    """Validate a YAML file using the global validator"""
    validator = get_validator()
    return validator.validate_yaml_file(Path(file_path), resource_type)
