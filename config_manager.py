# config_manager.py - YAML-based configuration with validation
import yaml
import os
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from pathlib import Path

@dataclass
class DatabaseConfig:
    postgres_host: str
    postgres_port: int
    postgres_database: str
    postgres_username: str
    postgres_password: str
    postgres_pool_min: int
    postgres_pool_max: int
    qdrant_host: str
    qdrant_port: int
    qdrant_collection: str
    
    @property
    def postgres_dsn(self) -> str:
        return f"postgresql://{self.postgres_username}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_database}"

@dataclass
class LLMConfig:
    model_name: str
    embedding_model: str
    vector_dimension: int
    max_retries: int
    timeout_seconds: int

@dataclass
class RobotConfig:
    waypoints: List[str]
    max_waypoints_per_command: int
    navigation_timeout_seconds: int
    stuck_detection_threshold: int

@dataclass
class SystemConfig:
    name: str
    version: str
    log_level: str
    context_update_interval: int
    telemetry_retention_hours: int
    chat_history_limit: int

@dataclass
class ServerConfig:
    host: str
    port: int
    cors_origins: List[str]
    max_concurrent_requests: int

@dataclass
class AppConfig:
    system: SystemConfig
    database: DatabaseConfig
    llm: LLMConfig
    robot: RobotConfig
    server: ServerConfig
    
    @classmethod
    def from_yaml(cls, config_path: str = "config.yaml") -> 'AppConfig':
        """Load configuration from YAML file with environment variable overrides"""
        config_file = Path(config_path)
        
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        with open(config_file, 'r') as f:
            config_data = yaml.safe_load(f)
        
        # Apply environment variable overrides
        config_data = cls._apply_env_overrides(config_data)
        
        # Build nested dataclasses
        return cls(
            system=SystemConfig(**config_data['system']),
            database=DatabaseConfig(
                postgres_host=config_data['database']['postgres']['host'],
                postgres_port=config_data['database']['postgres']['port'],
                postgres_database=config_data['database']['postgres']['database'],
                postgres_username=config_data['database']['postgres']['username'],
                postgres_password=config_data['database']['postgres']['password'],
                postgres_pool_min=config_data['database']['postgres']['pool_size']['min'],
                postgres_pool_max=config_data['database']['postgres']['pool_size']['max'],
                qdrant_host=config_data['database']['qdrant']['host'],
                qdrant_port=config_data['database']['qdrant']['port'],
                qdrant_collection=config_data['database']['qdrant']['collection_name']
            ),
            llm=LLMConfig(**config_data['llm']),
            robot=RobotConfig(
                waypoints=config_data['robot']['waypoints'],
                max_waypoints_per_command=config_data['robot']['navigation']['max_waypoints_per_command'],
                navigation_timeout_seconds=config_data['robot']['navigation']['timeout_seconds'],
                stuck_detection_threshold=config_data['robot']['navigation']['stuck_detection_threshold']
            ),
            server=ServerConfig(**config_data['server'])
        )
    
    @staticmethod
    def _apply_env_overrides(config_data: Dict) -> Dict:
        """Apply environment variable overrides"""
        env_mappings = {
            'POSTGRES_HOST': ['database', 'postgres', 'host'],
            'POSTGRES_PORT': ['database', 'postgres', 'port'],
            'POSTGRES_DB': ['database', 'postgres', 'database'],
            'POSTGRES_USER': ['database', 'postgres', 'username'],
            'POSTGRES_PASSWORD': ['database', 'postgres', 'password'],
            'LLM_MODEL': ['llm', 'model_name'],
            'LOG_LEVEL': ['system', 'log_level'],
            'SERVER_PORT': ['server', 'port']
        }
        
        for env_var, path in env_mappings.items():
            if env_var in os.environ:
                # Navigate to nested dict and set value
                current = config_data
                for key in path[:-1]:
                    current = current[key]
                
                # Convert type if needed
                value = os.environ[env_var]
                if path[-1] == 'port':
                    value = int(value)
                
                current[path[-1]] = value
        
        return config_data
    
    def validate(self) -> bool:
        """Validate configuration"""
        try:
            assert self.system.context_update_interval > 0
            assert self.llm.vector_dimension > 0
            assert len(self.robot.waypoints) > 0
            assert self.database.postgres_pool_max >= self.database.postgres_pool_min
            assert self.server.port > 0
            return True
        except AssertionError as e:
            print(f"❌ Configuration validation failed: {e}")
            return False

# Global configuration instance
config = AppConfig.from_yaml()

def get_config() -> AppConfig:
    """Get the global configuration instance"""
    return config