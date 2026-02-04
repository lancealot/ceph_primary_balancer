"""Configuration file support for Ceph Primary PG Balancer.

This module provides configuration file loading and management with support
for JSON and YAML formats. Configuration values follow a hierarchical precedence:
1. CLI arguments (highest priority)
2. Configuration file values
3. Built-in defaults (lowest priority)

Example:
    config = Config('my-cluster.json')
    target_cv = config.get('optimization.target_cv', 0.10)
"""

import json
from typing import Dict, Any, Optional
from pathlib import Path


class ConfigError(Exception):
    """Raised when configuration loading or parsing fails."""
    pass


class Config:
    """Load and manage configuration from JSON/YAML file.
    
    Supports hierarchical configuration with deep merging of user settings
    over default values. Provides dot-notation access for convenience.
    
    Attributes:
        settings: Complete configuration dictionary after merging defaults
                  with user-provided settings.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize configuration with optional config file.
        
        Args:
            config_path: Path to JSON or YAML configuration file. If None,
                        uses only default settings.
        
        Raises:
            ConfigError: If config file cannot be loaded or parsed.
        """
        self.settings = self._default_settings()
        if config_path:
            self.load_file(config_path)
    
    def _default_settings(self) -> Dict[str, Any]:
        """Return default configuration values.
        
        Returns:
            Dictionary with complete default configuration.
        """
        return {
            'optimization': {
                'target_cv': 0.10,
                'max_changes': None,
                'max_iterations': 10000
            },
            'scoring': {
                'weights': {
                    'osd': 0.5,
                    'host': 0.3,
                    'pool': 0.2
                }
            },
            'output': {
                'directory': None,
                'json_export': False,
                'markdown_report': False,
                'script_name': 'rebalance_primaries.sh'
            },
            'script': {
                'batch_size': 50,
                'health_check': True,
                'generate_rollback': True,
                'organized_by_pool': False
            },
            'verbosity': {
                'verbose': False,
                'quiet': False
            }
        }
    
    def load_file(self, path: str) -> None:
        """Load configuration from JSON or YAML file.
        
        Args:
            path: Path to configuration file. Supports .json, .yaml, .yml extensions.
        
        Raises:
            ConfigError: If file cannot be read, parsed, or has invalid format.
        """
        path_obj = Path(path)
        
        if not path_obj.exists():
            raise ConfigError(f"Configuration file not found: {path}")
        
        try:
            with open(path_obj, 'r') as f:
                if path_obj.suffix == '.json':
                    user_settings = json.load(f)
                elif path_obj.suffix in ('.yaml', '.yml'):
                    # Try to import yaml, fall back to JSON if not available
                    try:
                        import yaml
                        user_settings = yaml.safe_load(f)
                    except ImportError:
                        raise ConfigError(
                            "YAML support requires PyYAML. "
                            "Install with: pip install pyyaml"
                        )
                else:
                    raise ConfigError(
                        f"Unsupported configuration format: {path_obj.suffix}. "
                        "Use .json, .yaml, or .yml"
                    )
            
            if not isinstance(user_settings, dict):
                raise ConfigError(
                    f"Configuration file must contain a JSON/YAML object, "
                    f"got {type(user_settings).__name__}"
                )
            
            self._merge_settings(user_settings)
            
        except json.JSONDecodeError as e:
            raise ConfigError(f"Invalid JSON in configuration file: {e}")
        except Exception as e:
            if isinstance(e, ConfigError):
                raise
            raise ConfigError(f"Error loading configuration file: {e}")
    
    def _merge_settings(self, user_settings: Dict[str, Any]) -> None:
        """Deep merge user settings with defaults.
        
        User settings take precedence over defaults. Performs recursive
        merge for nested dictionaries.
        
        Args:
            user_settings: User-provided configuration dictionary.
        """
        self.settings = self._deep_merge(self.settings, user_settings)
    
    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively merge two dictionaries.
        
        Args:
            base: Base dictionary (defaults).
            override: Override dictionary (user settings).
        
        Returns:
            New dictionary with merged values. Override takes precedence.
        """
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Recursively merge nested dictionaries
                result[key] = self._deep_merge(result[key], value)
            else:
                # Override value
                result[key] = value
        
        return result
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation.
        
        Supports nested access like 'optimization.target_cv'.
        
        Args:
            key: Configuration key in dot notation (e.g., 'optimization.target_cv').
            default: Default value if key not found.
        
        Returns:
            Configuration value or default if not found.
        
        Example:
            >>> config = Config()
            >>> config.get('optimization.target_cv')
            0.10
            >>> config.get('scoring.weights.osd')
            0.5
        """
        keys = key.split('.')
        value = self.settings
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def to_dict(self) -> Dict[str, Any]:
        """Return complete configuration as dictionary.
        
        Returns:
            Complete configuration dictionary.
        """
        return self.settings.copy()
