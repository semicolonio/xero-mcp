import json
import os
import shutil
from pathlib import Path
from typing import Dict, Optional

class ConfigManager:
    def __init__(self, cloud_config_path: Optional[str] = None):
        self.home = str(Path.home())
        self.claude_config_dir = os.path.join(self.home, "Library/Application Support/Claude")
        self.claude_config_path = os.path.join(self.claude_config_dir, "claude_desktop_config.json")
        self.dev_config_path = "config_dev.json"
        self.prod_config_path = "config_prod.json"
        self.cloud_config_path = cloud_config_path

    def load_config(self, config_path: str) -> Dict:
        """Load a configuration file"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {"mcpServers": {}}

    def save_config(self, config: Dict, config_path: str):
        """Save a configuration file"""
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)

    def merge_configs(self, base_config: Dict, overlay_config: Dict) -> Dict:
        """Merge two configurations, with overlay_config taking precedence"""
        merged = base_config.copy()
        for server_name, server_config in overlay_config.get("mcpServers", {}).items():
            merged["mcpServers"][server_name] = server_config
        return merged

    def backup_claude_config(self):
        """Create a backup of the current Claude config"""
        if os.path.exists(self.claude_config_path):
            backup_path = f"{self.claude_config_path}.backup"
            shutil.copy2(self.claude_config_path, backup_path)
            print(f"Backup created at: {backup_path}")

    def switch_to_dev(self):
        """Switch to development configuration"""
        dev_config = self.load_config(self.dev_config_path)
        self.backup_claude_config()
        self.save_config(dev_config, self.claude_config_path)
        print("Switched to development configuration")

    def switch_to_prod(self):
        """Switch to production configuration"""
        prod_config = self.load_config(self.prod_config_path)
        self.backup_claude_config()
        self.save_config(prod_config, self.claude_config_path)
        print("Switched to production configuration")

    def merge_with_cloud(self):
        """Merge current configuration with cloud configuration"""
        if not self.cloud_config_path:
            raise ValueError("Cloud config path not specified")
        
        current_config = self.load_config(self.claude_config_path)
        cloud_config = self.load_config(self.cloud_config_path)
        merged_config = self.merge_configs(cloud_config, current_config)
        
        self.backup_claude_config()
        self.save_config(merged_config, self.claude_config_path)
        print("Merged with cloud configuration")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Manage Claude Desktop configurations")
    parser.add_argument("action", choices=["dev", "prod", "merge"], 
                      help="Action to perform: switch to dev/prod or merge with cloud")
    parser.add_argument("--cloud-config", help="Path to cloud configuration file")
    
    args = parser.parse_args()
    
    manager = ConfigManager(cloud_config_path=args.cloud_config)
    
    if args.action == "dev":
        manager.switch_to_dev()
    elif args.action == "prod":
        manager.switch_to_prod()
    elif args.action == "merge":
        if not args.cloud_config:
            parser.error("--cloud-config is required for merge action")
        manager.merge_with_cloud() 