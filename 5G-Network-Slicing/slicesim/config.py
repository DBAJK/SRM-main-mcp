#!/usr/bin/env python3
"""
5G Network Slicing - Configuration Module

This module handles system settings and parameters for the 5G network slicing system.
It includes default configurations and methods to load and save configurations.
"""

import os
import json
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_CONFIG = {
    "system": {
        "log_level": "INFO",
        "results_dir": "results",
        "models_dir": "models"
    },
    "slices": {
        "types": ["eMBB", "URLLC", "mMTC"],
        "default_allocation": [0.4, 0.4, 0.2],  # Default allocation for eMBB, URLLC, mMTC
        "qos_thresholds": {
            "eMBB": 0.9,    # High bandwidth, moderate latency
            "URLLC": 1.2,   # Low latency, high reliability
            "mMTC": 0.8     # Many connections, low bandwidth per device
        },
        "emergency_allocation": [0.2, 0.7, 0.1]  # Emergency allocation prioritizing URLLC
    },
    "simulation": {
        "duration": 100,        # Default simulation duration in steps
        "emergency_duration": 20,  # Duration of emergency events
        "emergency_probability": 0.1,  # Probability of emergency event
        "traffic_patterns": {
            "eMBB": {
                "base_level": 0.4,
                "variance": 0.2,
                "emergency_factor": 0.8  # Reduced during emergency
            },
            "URLLC": {
                "base_level": 0.3,
                "variance": 0.1,
                "emergency_factor": 2.0  # Increased during emergency
            },
            "mMTC": {
                "base_level": 0.2,
                "variance": 0.15,
                "emergency_factor": 0.9  # Slightly reduced during emergency
            }
        }
    },
    "model": {
        "type": "single_step",  # 'single_step' or 'autoregressive'
        "input_dim": 11,        # Input dimension (3 slices * 3 metrics + 2 context)
        "sequence_length": 10,  # Number of past steps to consider
        "out_steps": 1,         # Number of future steps to predict
        "lstm_units": 64,       # Number of LSTM units
        "batch_size": 32,       # Batch size for training
        "epochs": 50,           # Number of training epochs
        "learning_rate": 0.001, # Learning rate
        "train_test_split": 0.8 # Train/test split ratio
    },
    "visualization": {
        "dpi": 100,
        "figsize": [12, 8],
        "save_format": "png"
    }
}


class Config:
    """
    Configuration handler for the 5G network slicing system.
    
    This class handles loading, saving, and accessing configuration parameters.
    """
    
    def __init__(self, config_path=None):
        """
        Initialize the configuration handler.
        
        Args:
            config_path (str, optional): Path to the configuration file
        """
        self.config = DEFAULT_CONFIG.copy()
        self.config_path = config_path
        
        if config_path and os.path.exists(config_path):
            self.load(config_path)
        else:
            logger.info("Using default configuration")
    
    def load(self, config_path):
        """
        Load configuration from a file.
        
        Args:
            config_path (str): Path to the configuration file
        
        Returns:
            bool: Whether the configuration was loaded successfully
        """
        try:
            with open(config_path, 'r') as f:
                loaded_config = json.load(f)
            
            # Update configuration with loaded values
            self._update_config(self.config, loaded_config)
            self.config_path = config_path
            logger.info(f"Configuration loaded from {config_path}")
            return True
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            return False
    
    def _update_config(self, base_config, new_config):
        """
        Recursively update configuration.
        
        Args:
            base_config (dict): Base configuration
            new_config (dict): New configuration to apply
        """
        for key, value in new_config.items():
            if key in base_config and isinstance(base_config[key], dict) and isinstance(value, dict):
                self._update_config(base_config[key], value)
            else:
                base_config[key] = value
    
    def save(self, config_path=None):
        """
        Save configuration to a file.
        
        Args:
            config_path (str, optional): Path to save the configuration file
        
        Returns:
            bool: Whether the configuration was saved successfully
        """
        if config_path is None:
            config_path = self.config_path
        
        if config_path is None:
            logger.error("No configuration path specified")
            return False
        
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(os.path.abspath(config_path)), exist_ok=True)
            
            with open(config_path, 'w') as f:
                json.dump(self.config, f, indent=4)
            
            logger.info(f"Configuration saved to {config_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            return False
    
    def get(self, *keys, default=None):
        """
        Get a configuration value.
        
        Args:
            *keys: Sequence of keys to access nested configuration
            default: Default value if the key doesn't exist
        
        Returns:
            The configuration value or the default value
        """
        config = self.config
        for key in keys:
            if isinstance(config, dict) and key in config:
                config = config[key]
            else:
                return default
        return config
    
    def set(self, value, *keys):
        """
        Set a configuration value.
        
        Args:
            value: Value to set
            *keys: Sequence of keys to access nested configuration
        
        Returns:
            bool: Whether the value was set successfully
        """
        if not keys:
            return False
        
        config = self.config
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            elif not isinstance(config[key], dict):
                config[key] = {}
            config = config[key]
        
        config[keys[-1]] = value
        return True
    
    def ensure_directories(self):
        """
        Ensure that the directories specified in the configuration exist.
        
        Returns:
            bool: Whether all directories were created successfully
        """
        try:
            # Create results directory
            results_dir = self.get("system", "results_dir")
            if results_dir:
                os.makedirs(results_dir, exist_ok=True)
            
            # Create models directory
            models_dir = self.get("system", "models_dir")
            if models_dir:
                os.makedirs(models_dir, exist_ok=True)
            
            logger.info("Directories created successfully")
            return True
        except Exception as e:
            logger.error(f"Error creating directories: {e}")
            return False


# Global configuration instance
config = Config()


def load_config(config_path):
    """
    Load configuration from a file.
    
    Args:
        config_path (str): Path to the configuration file
    
    Returns:
        bool: Whether the configuration was loaded successfully
    """
    global config
    config = Config(config_path)
    return True


def get_config():
    """
    Get the global configuration instance.
    
    Returns:
        Config: Global configuration instance
    """
    return config


# Example usage
if __name__ == "__main__":
    # Create a configuration instance
    cfg = Config()
    
    # Get a configuration value
    print(f"Default allocation: {cfg.get('slices', 'default_allocation')}")
    
    # Set a configuration value
    cfg.set([0.3, 0.5, 0.2], 'slices', 'default_allocation')
    print(f"Updated allocation: {cfg.get('slices', 'default_allocation')}")
    
    # Save configuration to a file
    cfg.save("config_example.json")
    
    # Load configuration from a file
    new_cfg = Config("config_example.json")
    print(f"Loaded allocation: {new_cfg.get('slices', 'default_allocation')}")
    
    # Clean up example file
    if os.path.exists("config_example.json"):
        os.remove("config_example.json")
        print("Example file removed") 