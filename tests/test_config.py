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
Unit tests for configuration loading and validation in config.py module.

Tests Config class with various valid and invalid configurations.
"""
import pytest
import yaml
from pathlib import Path
from backend.config import Config, get_config


class TestConfigLoading:
    """Tests for Config class initialization and loading."""
    
    def test_load_valid_config(self, tmp_path, sample_config_dict):
        """Test loading a valid configuration file."""
        config_file = tmp_path / "config.yaml"
        with open(config_file, 'w') as f:
            yaml.dump(sample_config_dict, f)
        
        config = Config(config_path=str(config_file))
        
        assert config._config_data == sample_config_dict
        assert config.config_path == config_file
    
    def test_load_config_file_not_found(self, tmp_path):
        """Test error handling when config file doesn't exist."""
        non_existent = tmp_path / "nonexistent.yaml"
        
        with pytest.raises(FileNotFoundError) as exc_info:
            Config(config_path=str(non_existent))
        
        assert "Configuration file not found" in str(exc_info.value)
    
    def test_load_empty_config(self, tmp_path):
        """Test loading an empty configuration file."""
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")
        
        config = Config(config_path=str(config_file))
        
        assert config._config_data == {}
    
    def test_load_malformed_yaml(self, tmp_path):
        """Test error handling for malformed YAML."""
        config_file = tmp_path / "malformed.yaml"
        config_file.write_text("invalid: yaml: content: [[[")
        
        with pytest.raises(yaml.YAMLError):
            Config(config_path=str(config_file))


class TestLLMConfig:
    """Tests for LLM configuration retrieval."""
    
    def test_get_llm_config_success(self, tmp_path, sample_config_dict):
        """Test successful LLM config retrieval."""
        config_file = tmp_path / "config.yaml"
        with open(config_file, 'w') as f:
            yaml.dump(sample_config_dict, f)
        
        config = Config(config_path=str(config_file))
        llm_config = config.get_llm_config()
        
        assert llm_config["url"] == "http://test-llm:8000/v1"
        assert llm_config["model"] == "test-llm-model"
    
    def test_get_llm_config_missing_section(self, tmp_path):
        """Test error when LLM section is missing."""
        config_data = {"embeddings": {"url": "test", "model": "test"}}
        config_file = tmp_path / "config.yaml"
        with open(config_file, 'w') as f:
            yaml.dump(config_data, f)
        
        config = Config(config_path=str(config_file))
        
        with pytest.raises(ValueError) as exc_info:
            config.get_llm_config()
        
        assert "LLM configuration section not found" in str(exc_info.value)
    
    def test_get_llm_config_missing_fields(self, tmp_path):
        """Test error when LLM required fields are missing."""
        config_data = {"llm": {"url": "http://test:8000"}}
        config_file = tmp_path / "config.yaml"
        with open(config_file, 'w') as f:
            yaml.dump(config_data, f)
        
        config = Config(config_path=str(config_file))
        
        with pytest.raises(ValueError) as exc_info:
            config.get_llm_config()
        
        assert "LLM model not configured" in str(exc_info.value)


class TestGetConfigSingleton:
    """Tests for get_config() singleton function."""
    
    def test_get_config_returns_singleton(self):
        """Test that get_config returns the same instance."""
        # Note: This test may fail if config file doesn't exist at default location
        # In a real scenario, we'd need to mock the default config path
        # For now, we'll skip this test if the default config doesn't exist
        try:
            config1 = get_config()
            config2 = get_config()
            assert config1 is config2
        except FileNotFoundError:
            pytest.skip("Default config file not found")
    
    def test_get_config_loads_default_path(self):
        """Test that get_config uses default path."""
        try:
            config = get_config()
            # Should have loaded from default path
            assert config.config_path.name == "config.yaml"
            assert "shared" in str(config.config_path)
        except FileNotFoundError:
            pytest.skip("Default config file not found")

