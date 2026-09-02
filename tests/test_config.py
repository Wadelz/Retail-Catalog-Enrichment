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


class TestVLMConfig:
    """Tests for VLM configuration retrieval."""
    
    def test_get_vlm_config_success(self, tmp_path, sample_config_dict, monkeypatch):
        """Test successful VLM config retrieval."""
        # These now override config.yaml, so an exported value in the
        # developer's shell would otherwise fail this test.
        monkeypatch.delenv("NVIDIA_API_BASE_URL", raising=False)
        monkeypatch.delenv("VLM_MODEL", raising=False)
        config_file = tmp_path / "config.yaml"
        with open(config_file, 'w') as f:
            yaml.dump(sample_config_dict, f)
        
        config = Config(config_path=str(config_file))
        vlm_config = config.get_vlm_config()
        
        assert vlm_config["url"] == "http://test-vlm:8000/v1"
        assert vlm_config["model"] == "test-vlm-model"
    
    def test_get_vlm_config_missing_section(self, tmp_path):
        """Test error when VLM section is missing."""
        config_data = {"llm": {"url": "test", "model": "test"}}
        config_file = tmp_path / "config.yaml"
        with open(config_file, 'w') as f:
            yaml.dump(config_data, f)
        
        config = Config(config_path=str(config_file))
        
        with pytest.raises(ValueError) as exc_info:
            config.get_vlm_config()
        
        assert "VLM configuration section not found" in str(exc_info.value)
    
    def test_get_vlm_config_missing_url(self, tmp_path):
        """Test error when VLM url is missing."""
        config_data = {"vlm": {"model": "test-model"}}
        config_file = tmp_path / "config.yaml"
        with open(config_file, 'w') as f:
            yaml.dump(config_data, f)
        
        config = Config(config_path=str(config_file))
        
        with pytest.raises(ValueError) as exc_info:
            config.get_vlm_config()
        
        assert "VLM url not configured" in str(exc_info.value)
    
    def test_get_vlm_config_missing_model(self, tmp_path):
        """Test error when VLM model is missing."""
        config_data = {"vlm": {"url": "http://test:8000"}}
        config_file = tmp_path / "config.yaml"
        with open(config_file, 'w') as f:
            yaml.dump(config_data, f)
        
        config = Config(config_path=str(config_file))
        
        with pytest.raises(ValueError) as exc_info:
            config.get_vlm_config()
        
        assert "VLM model not configured" in str(exc_info.value)


class TestLLMConfig:
    """Tests for LLM configuration retrieval."""
    
    def test_get_llm_config_success(self, tmp_path, sample_config_dict, monkeypatch):
        """Test successful LLM config retrieval."""
        # These now override config.yaml, so an exported value in the
        # developer's shell would otherwise fail this test.
        monkeypatch.delenv("NVIDIA_API_BASE_URL", raising=False)
        monkeypatch.delenv("LLM_MODEL", raising=False)
        config_file = tmp_path / "config.yaml"
        with open(config_file, 'w') as f:
            yaml.dump(sample_config_dict, f)
        
        config = Config(config_path=str(config_file))
        llm_config = config.get_llm_config()
        
        assert llm_config["url"] == "http://test-llm:8000/v1"
        assert llm_config["model"] == "test-llm-model"
    
    def test_get_llm_config_missing_section(self, tmp_path):
        """Test error when LLM section is missing."""
        config_data = {"vlm": {"url": "test", "model": "test"}}
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


class TestFluxConfig:
    """Tests for FLUX configuration retrieval."""
    
    def test_get_flux_config_success(self, tmp_path, sample_config_dict):
        """Test successful FLUX config retrieval."""
        config_file = tmp_path / "config.yaml"
        with open(config_file, 'w') as f:
            yaml.dump(sample_config_dict, f)
        
        config = Config(config_path=str(config_file))
        flux_config = config.get_flux_config()
        
        assert flux_config["url"] == "http://test-flux:8000/v1/infer"
    
    def test_get_flux_config_missing_section(self, tmp_path):
        """Test error when FLUX section is missing."""
        config_data = {"vlm": {"url": "test", "model": "test"}}
        config_file = tmp_path / "config.yaml"
        with open(config_file, 'w') as f:
            yaml.dump(config_data, f)
        
        config = Config(config_path=str(config_file))
        
        with pytest.raises(ValueError) as exc_info:
            config.get_flux_config()
        
        assert "FLUX configuration section not found" in str(exc_info.value)
    
    def test_get_flux_config_missing_url(self, tmp_path):
        """Test error when FLUX url is missing."""
        # Empty dict is treated as "section not found" because empty dict is falsy
        config_data = {"flux": {}}
        config_file = tmp_path / "config.yaml"
        with open(config_file, 'w') as f:
            yaml.dump(config_data, f)
        
        config = Config(config_path=str(config_file))
        
        with pytest.raises(ValueError) as exc_info:
            config.get_flux_config()
        
        # Empty dict triggers "section not found" error
        assert "configuration section not found" in str(exc_info.value).lower()


class TestTrellisConfig:
    """Tests for TRELLIS configuration retrieval."""
    
    def test_get_trellis_config_success(self, tmp_path, sample_config_dict):
        """Test successful TRELLIS config retrieval."""
        config_file = tmp_path / "config.yaml"
        with open(config_file, 'w') as f:
            yaml.dump(sample_config_dict, f)
        
        config = Config(config_path=str(config_file))
        trellis_config = config.get_trellis_config()
        
        assert trellis_config["url"] == "http://test-trellis:8000/v1/infer"
    
    def test_get_trellis_config_missing_section(self, tmp_path):
        """Test error when TRELLIS section is missing."""
        config_data = {"vlm": {"url": "test", "model": "test"}}
        config_file = tmp_path / "config.yaml"
        with open(config_file, 'w') as f:
            yaml.dump(config_data, f)
        
        config = Config(config_path=str(config_file))
        
        with pytest.raises(ValueError) as exc_info:
            config.get_trellis_config()
        
        assert "TRELLIS configuration section not found" in str(exc_info.value)
    
    def test_get_trellis_config_missing_url(self, tmp_path):
        """Test error when TRELLIS url is missing."""
        # Empty dict is treated as "section not found" because empty dict is falsy
        config_data = {"trellis": {}}
        config_file = tmp_path / "config.yaml"
        with open(config_file, 'w') as f:
            yaml.dump(config_data, f)
        
        config = Config(config_path=str(config_file))
        
        with pytest.raises(ValueError) as exc_info:
            config.get_trellis_config()
        
        # Empty dict triggers "section not found" error
        assert "configuration section not found" in str(exc_info.value).lower()


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


class TestNimEndpointOverrides:
    """Environment overrides that switch NIM sections to hosted endpoints.

    config.yaml holds the self-hosted defaults; these variables redirect them
    without editing a committed file.
    """

    def _config(self, tmp_path, data):
        config_file = tmp_path / "config.yaml"
        with open(config_file, 'w') as f:
            yaml.dump(data, f)
        return Config(config_path=str(config_file))

    @pytest.fixture
    def clean_env(self, monkeypatch):
        for var in ("NVIDIA_API_BASE_URL", "VLM_MODEL", "LLM_MODEL", "EMBEDDINGS_MODEL"):
            monkeypatch.delenv(var, raising=False)
        return monkeypatch

    @pytest.mark.parametrize("section,getter", [("vlm", "get_vlm_config"), ("llm", "get_llm_config")])
    def test_base_url_override_redirects_section(self, tmp_path, clean_env, section, getter):
        clean_env.setenv("NVIDIA_API_BASE_URL", "https://integrate.api.nvidia.com/v1")
        cfg = self._config(tmp_path, {section: {"url": f"http://nim-{section}:8000/v1", "model": "m"}})

        result = getattr(cfg, getter)()

        assert result["url"] == "https://integrate.api.nvidia.com/v1"
        assert result["model"] == "m", "model must not change when only the URL is overridden"

    @pytest.mark.parametrize("section,getter,var", [
        ("vlm", "get_vlm_config", "VLM_MODEL"),
        ("llm", "get_llm_config", "LLM_MODEL"),
    ])
    def test_model_override_is_per_section(self, tmp_path, clean_env, section, getter, var):
        clean_env.setenv(var, "nvidia/hosted-catalog-id")
        cfg = self._config(tmp_path, {section: {"url": "http://x:8000/v1", "model": "from-yaml"}})

        result = getattr(cfg, getter)()

        assert result["model"] == "nvidia/hosted-catalog-id"
        assert result["url"] == "http://x:8000/v1", "model override must not touch the URL"

    def test_vlm_and_llm_models_override_independently(self, tmp_path, clean_env):
        clean_env.setenv("VLM_MODEL", "vlm-override")
        cfg = self._config(tmp_path, {
            "vlm": {"url": "http://v:8000/v1", "model": "vlm-yaml"},
            "llm": {"url": "http://l:8000/v1", "model": "llm-yaml"},
        })

        assert cfg.get_vlm_config()["model"] == "vlm-override"
        assert cfg.get_llm_config()["model"] == "llm-yaml", "VLM_MODEL must not leak into the LLM section"

    def test_yaml_used_when_env_absent(self, tmp_path, clean_env):
        cfg = self._config(tmp_path, {"llm": {"url": "http://nim-llm:8000/v1", "model": "yaml-model"}})

        result = cfg.get_llm_config()

        assert result == {"url": "http://nim-llm:8000/v1", "model": "yaml-model"}

    def test_embeddings_model_override(self, tmp_path, clean_env):
        clean_env.setenv("EMBEDDINGS_MODEL", "nvidia/llama-3.2-nv-embedqa-1b-v1")
        cfg = self._config(tmp_path, {"embeddings": {"url": "http://embedqa:8000/v1", "model": "nvidia/nv-embedqa-e5-v5"}})

        assert cfg.get_embeddings_config()["model"] == "nvidia/llama-3.2-nv-embedqa-1b-v1"

    def test_required_keys_still_validated_under_override(self, tmp_path, clean_env):
        """An override must not paper over a malformed config section."""
        clean_env.setenv("NVIDIA_API_BASE_URL", "https://integrate.api.nvidia.com/v1")
        cfg = self._config(tmp_path, {"llm": {"url": "http://nim-llm:8000/v1"}})  # no model

        with pytest.raises(ValueError, match="LLM model not configured"):
            cfg.get_llm_config()
