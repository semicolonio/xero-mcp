from fastmcp import FastMCP
import sqlite3

mcp = FastMCP("Xero Analytics")

@mcp.resource("schema://tables")
def get_schema() -> str:
    """Provide the database schema as context"""
    conn = sqlite3.connect("xero_analytics.db")
    schema = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return "\n".join(sql[0] for sql in schema if sql[0])

@mcp.tool()
def analyze_data(sql: str) -> str:
    """Execute read-only SQL queries safely"""
    conn = sqlite3.connect("xero_analytics.db")
    try:
        # Ensure query is read-only
        if any(keyword in sql.upper() for keyword in ["INSERT", "UPDATE", "DELETE", "DROP"]):
            raise ValueError("Only SELECT queries are allowed")
            
        result = conn.execute(sql).fetchall()
        return "\n".join(str(row) for row in result)
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.prompt()
def cash_flow_analysis(date_range: str) -> str:
    """Create a prompt template for cash flow analysis"""
    return f"""Please analyze the cash flow for {date_range}.
Available tables and schema:
{get_schema()}

Consider:
1. Net cash movement
2. Major income sources
3. Significant expenses
4. Cash flow trends.""" 