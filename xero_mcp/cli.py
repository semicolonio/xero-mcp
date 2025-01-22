import click

from .app import mcp

@click.command()
def run():
    """Run the Xero MCP server"""
    mcp.run()

if __name__ == '__main__':
    run() 