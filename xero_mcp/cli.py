import click
from pathlib import Path
from dotenv import load_dotenv
from .app import mcp

@click.command()
@click.option('--env-file', type=click.Path(exists=True, path_type=Path), help='Path to .env file')
@click.option('--config-dir', type=click.Path(exists=True, dir_okay=True, path_type=Path), help='Path to config directory')
def run(env_file: Path, config_dir: Path):
    """Run the Xero MCP server with custom env and config paths"""
    if env_file:
        load_dotenv(env_file)
    
    if config_dir:
        # Update the config directory in the app
        from . import app
        app.CONFIG_DIR = config_dir
        app.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    # Run the MCP server
    mcp.run()

if __name__ == '__main__':
    run() 