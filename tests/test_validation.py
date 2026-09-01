# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Unit tests for validation logic from main.py module.

Tests input validation, locale validation, and JSON parsing.
"""
import io
import json
import pytest
from fastapi import UploadFile
import backend.main as main
from backend.main import _validate_policy_uploads, VALID_LOCALES


class TestValidatePolicyUploads:
    """Tests for persistent policy PDF upload validation helper."""

    @pytest.mark.asyncio
    async def test_validate_policy_uploads_accepts_valid_pdf(self):
        from unittest.mock import Mock, AsyncMock

        upload_file = Mock(spec=UploadFile)
        upload_file.filename = "policy.pdf"
        upload_file.content_type = "application/pdf"
        upload_file.read = AsyncMock(return_value=b"%PDF-test")

        result, error = await _validate_policy_uploads([upload_file], "/test")

        assert error is None
        assert result == [{"filename": "policy.pdf", "bytes": b"%PDF-test"}]

    @pytest.mark.asyncio
    async def test_validate_policy_uploads_rejects_non_pdf(self):
        from unittest.mock import Mock, AsyncMock

        upload_file = Mock(spec=UploadFile)
        upload_file.filename = "policy.txt"
        upload_file.content_type = "text/plain"
        upload_file.read = AsyncMock(return_value=b"not a pdf")

        result, error = await _validate_policy_uploads([upload_file], "/test")

        assert result is None
        assert error is not None
        assert error.status_code == 400

    @pytest.mark.asyncio
    async def test_validate_policy_uploads_rejects_empty_pdf(self):
        from unittest.mock import Mock, AsyncMock

        empty_file = Mock(spec=UploadFile)
        empty_file.filename = "empty.pdf"
        empty_file.content_type = "application/pdf"
        empty_file.read = AsyncMock(return_value=b"")

        result, error = await _validate_policy_uploads([empty_file], "/test")

        assert result is None
        assert error is not None
        assert error.status_code == 400


class TestLocaleValidation:
    """Tests for locale validation."""
    
    def test_valid_locales_contains_expected_values(self):
        """Test that VALID_LOCALES contains all expected locales."""
        expected_locales = {
            "en-US", "en-GB", "en-AU", "en-CA",
            "es-ES", "es-MX", "es-AR", "es-CO",
            "fr-FR", "fr-CA"
        }
        
        assert VALID_LOCALES == expected_locales
    
    def test_valid_locale_check(self):
        """Test checking valid locales."""
        valid_examples = ["en-US", "es-ES", "fr-FR"]
        
        for locale in valid_examples:
            assert locale in VALID_LOCALES
    
    def test_invalid_locale_check(self):
        """Test checking invalid locales."""
        invalid_examples = ["en-ZZ", "es", "fr-XX", "invalid"]
        
        for locale in invalid_examples:
            assert locale not in VALID_LOCALES
    
    def test_case_sensitive_locale(self):
        """Test that locale validation is case-sensitive."""
        # These should not be valid (wrong case)
        assert "en-us" not in VALID_LOCALES  # lowercase
        assert "EN-US" not in VALID_LOCALES  # uppercase
        assert "en-US" in VALID_LOCALES      # correct case


class TestNIMHealthCache:
    @pytest.mark.asyncio
    async def test_health_nims_returns_cached_result_without_downstream_checks(self, monkeypatch):
        cached = {"llm": "healthy", "embeddings": "healthy"}
        monkeypatch.setattr(main, "_nim_health_cache", cached)
        monkeypatch.setattr(main, "_nim_health_cache_expires_at", main.time.monotonic() + 60)
        monkeypatch.setattr(main, "get_config", lambda: pytest.fail("cache should avoid config lookup"))

        response = await main.health_nims()

        assert json.loads(response.body.decode()) == cached


class TestFAQValidation:
    """Tests for FAQ endpoint input validation."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "manual_knowledge",
        ['{"battery": 5}', "[1, 2, 3]", "5"],
    )
    async def test_rejects_invalid_manual_knowledge_shape(self, manual_knowledge):
        response = await main.generate_faqs(
            title="x",
            description="",
            categories="[]",
            tags="[]",
            colors="[]",
            locale="en-US",
            manual_knowledge=manual_knowledge,
        )

        assert response.status_code == 400
        assert json.loads(response.body.decode()) == {
            "detail": "Invalid manual_knowledge."
        }


class TestJSONParsing:
    """Tests for JSON parsing in endpoint handlers."""
    
    def test_parse_valid_json_string(self):
        """Test parsing valid JSON string."""
        json_str = '{"title": "Test", "price": 19.99}'
        parsed = json.loads(json_str)
        
        assert isinstance(parsed, dict)
        assert parsed["title"] == "Test"
        assert parsed["price"] == 19.99
    
    def test_parse_valid_json_array(self):
        """Test parsing valid JSON array."""
        json_str = '["item1", "item2", "item3"]'
        parsed = json.loads(json_str)
        
        assert isinstance(parsed, list)
        assert len(parsed) == 3
        assert "item1" in parsed
    
    def test_parse_invalid_json_raises_error(self):
        """Test that invalid JSON raises JSONDecodeError."""
        invalid_json = '{invalid: json}'
        
        with pytest.raises(json.JSONDecodeError):
            json.loads(invalid_json)
    
    def test_parse_empty_string_raises_error(self):
        """Test that empty string raises JSONDecodeError."""
        with pytest.raises(json.JSONDecodeError):
            json.loads("")
    
    def test_parse_nested_json(self):
        """Test parsing nested JSON structures."""
        json_str = '{"product": {"title": "Test", "tags": ["tag1", "tag2"]}}'
        parsed = json.loads(json_str)
        
        assert isinstance(parsed, dict)
        assert "product" in parsed
        assert isinstance(parsed["product"]["tags"], list)
        assert len(parsed["product"]["tags"]) == 2
    
    def test_parse_json_with_unicode(self):
        """Test parsing JSON with Unicode characters."""
        json_str = '{"title": "Café au Lait", "description": "Crème brûlée"}'
        parsed = json.loads(json_str)
        
        assert parsed["title"] == "Café au Lait"
        assert parsed["description"] == "Crème brûlée"
    
    def test_parse_json_with_escaped_characters(self):
        """Test parsing JSON with escaped characters."""
        json_str = r'{"description": "Line 1\nLine 2\tTabbed"}'
        parsed = json.loads(json_str)
        
        assert "\n" in parsed["description"]
        assert "\t" in parsed["description"]


class TestCategoriesValidation:
    """Tests for categories validation logic."""
    
    def test_categories_as_list(self):
        """Test that categories can be parsed as list."""
        categories_json = '["bags", "kitchen"]'
        categories = json.loads(categories_json)
        
        assert isinstance(categories, list)
        assert "bags" in categories
        assert "kitchen" in categories
    
    def test_empty_categories_list(self):
        """Test handling of empty categories list."""
        categories_json = '[]'
        categories = json.loads(categories_json)
        
        assert isinstance(categories, list)
        assert len(categories) == 0
    
    def test_single_category(self):
        """Test single category in list."""
        categories_json = '["bags"]'
        categories = json.loads(categories_json)
        
        assert isinstance(categories, list)
        assert len(categories) == 1
        assert categories[0] == "bags"


class TestTagsValidation:
    """Tests for tags validation logic."""
    
    def test_tags_as_list(self):
        """Test that tags can be parsed as list."""
        tags_json = '["leather", "gold hardware", "evening bag"]'
        tags = json.loads(tags_json)
        
        assert isinstance(tags, list)
        assert len(tags) == 3
        assert "leather" in tags
    
    def test_empty_tags_list(self):
        """Test handling of empty tags list."""
        tags_json = '[]'
        tags = json.loads(tags_json)
        
        assert isinstance(tags, list)
        assert len(tags) == 0
    
    def test_tags_with_special_characters(self):
        """Test tags with special characters."""
        tags_json = '["24/7 wear", "eco-friendly", "size: large"]'
        tags = json.loads(tags_json)
        
        assert isinstance(tags, list)
        assert "24/7 wear" in tags
        assert "eco-friendly" in tags


class TestColorsValidation:
    """Tests for colors validation logic."""
    
    def test_colors_as_list(self):
        """Test that colors can be parsed as list."""
        colors_json = '["black", "gold", "silver"]'
        colors = json.loads(colors_json)
        
        assert isinstance(colors, list)
        assert len(colors) == 3
        assert "black" in colors
    
    def test_empty_colors_list(self):
        """Test handling of empty colors list."""
        colors_json = '[]'
        colors = json.loads(colors_json)
        
        assert isinstance(colors, list)
        assert len(colors) == 0
    
    def test_single_color(self):
        """Test single color in list."""
        colors_json = '["red"]'
        colors = json.loads(colors_json)
        
        assert isinstance(colors, list)
        assert len(colors) == 1
        assert colors[0] == "red"
