"""
Tests for the DisableValidation context manager.
"""
import pytest
from pydantic import BaseModel

from django_pydantic_field import DisableValidation, SchemaField
from django_pydantic_field.context import is_validation_disabled


class PersonSchema(BaseModel):
    name: str
    age: int
    email: str


@pytest.mark.django_db
def test_disable_validation_context_manager(db):
    """Test that DisableValidation properly disables validation."""
    from django.db import models
    from django.core.exceptions import ValidationError as DjangoValidationError

    # Create a test model
    class TestModel(models.Model):
        data = SchemaField(schema=PersonSchema)
        
        class Meta:
            app_label = 'test_app'

    # Create test instance with valid data
    instance = TestModel()
    
    # Test 1: Normal validation should work
    instance.data = {"name": "John", "age": 30, "email": "john@example.com"}
    assert isinstance(instance.data, PersonSchema)
    assert instance.data.name == "John"
    
    # Test 2: Invalid data should raise error without DisableValidation
    with pytest.raises(DjangoValidationError):
        instance.data = {"name": "Jane", "age": "invalid"}  # age should be int
    
    # Test 3: With DisableValidation, invalid data should be accepted
    with DisableValidation():
        # This should not raise an error
        instance.data = {"name": "Jane", "age": "invalid"}
        # Data should be raw dict, not a PersonSchema instance
        assert isinstance(instance.data, dict)
        assert instance.data["name"] == "Jane"
        assert instance.data["age"] == "invalid"


@pytest.mark.django_db  
def test_disable_validation_from_json(db):
    """Test that DisableValidation works with JSON strings."""
    from django.db import models
    
    class TestModel(models.Model):
        data = SchemaField(schema=PersonSchema)
        
        class Meta:
            app_label = 'test_app'
    
    field = TestModel._meta.get_field('data')
    
    # Test 1: Valid JSON should work normally
    valid_json = '{"name": "John", "age": 30, "email": "john@example.com"}'
    result = field.to_python(valid_json)
    assert isinstance(result, PersonSchema)
    assert result.name == "John"
    
    # Test 2: Invalid JSON should raise error without DisableValidation
    invalid_json = '{"name": "Jane", "age": "not_a_number"}'
    with pytest.raises(Exception):  # Will raise ValidationError
        field.to_python(invalid_json)
    
    # Test 3: With DisableValidation, invalid JSON should parse but not validate
    with DisableValidation():
        result = field.to_python(invalid_json)
        assert isinstance(result, dict)
        assert result["name"] == "Jane"
        assert result["age"] == "not_a_number"


def test_disable_validation_thread_safety():
    """Test that DisableValidation is thread-safe."""
    import threading
    
    results = []
    
    def check_disabled():
        # Should be False initially
        results.append(('thread_start', is_validation_disabled()))
        
    def check_in_context():
        with DisableValidation():
            results.append(('in_context', is_validation_disabled()))
        results.append(('after_context', is_validation_disabled()))
    
    # Test in main thread
    assert is_validation_disabled() is False
    
    with DisableValidation():
        assert is_validation_disabled() is True
        
        # Start another thread - should not be affected
        thread = threading.Thread(target=check_disabled)
        thread.start()
        thread.join()
    
    assert is_validation_disabled() is False
    
    # Test context in separate thread
    thread2 = threading.Thread(target=check_in_context)
    thread2.start()
    thread2.join()
    
    # Verify results
    assert ('thread_start', False) in results
    assert ('in_context', True) in results
    assert ('after_context', False) in results


def test_disable_validation_nesting():
    """Test that DisableValidation can be nested."""
    
    assert is_validation_disabled() is False
    
    with DisableValidation():
        assert is_validation_disabled() is True
        
        with DisableValidation():
            assert is_validation_disabled() is True
        
        assert is_validation_disabled() is True
    
    assert is_validation_disabled() is False


def test_disable_validation_with_exception():
    """Test that DisableValidation properly restores state even with exceptions."""
    
    assert is_validation_disabled() is False
    
    try:
        with DisableValidation():
            assert is_validation_disabled() is True
            raise ValueError("Test exception")
    except ValueError:
        pass
    
    # State should be restored even after exception
    assert is_validation_disabled() is False


@pytest.mark.django_db
def test_disable_validation_v1_fields(db):
    """Test that DisableValidation works with v1 PydanticSchemaField."""
    from django.db import models
    from django.core.exceptions import ValidationError as DjangoValidationError
    from django_pydantic_field.v1.fields import SchemaField as V1SchemaField
    
    # Create a test model
    class TestModelV1(models.Model):
        data = V1SchemaField(schema=PersonSchema)
        
        class Meta:
            app_label = 'test_app'
    
    # Create test instance with valid data
    instance = TestModelV1()
    
    # Test 1: Normal validation should work
    instance.data = {"name": "John", "age": 30, "email": "john@example.com"}
    assert isinstance(instance.data, PersonSchema)
    assert instance.data.name == "John"
    
    # Test 2: Invalid data should raise error without DisableValidation
    with pytest.raises(DjangoValidationError):
        instance.data = {"name": "Jane", "age": "invalid"}  # age should be int
    
    # Test 3: With DisableValidation, invalid data should be accepted
    with DisableValidation():
        # This should not raise an error
        instance.data = {"name": "Jane", "age": "invalid"}
        # Data should be raw dict, not a PersonSchema instance
        assert isinstance(instance.data, dict)
        assert instance.data["name"] == "Jane"
        assert instance.data["age"] == "invalid"
