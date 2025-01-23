# Xero MCP

A Model Context Protocol server that provides access to Xero's accounting API. This server enables LLMs to interact with Xero's financial data, reports, and accounting resources.

## Components

### Tools

#### Financial Reports
- `xero_get_balance_sheet`
  - Retrieve balance sheet report with assets, liabilities, and equity
  - Input: `date` (string): Report date in YYYY-MM-DD format
  - Optional: `periods`, `timeframe`, `tracking_options`

- `xero_get_profit_and_loss`
  - Retrieve profit and loss statement
  - Input: `from_date`, `to_date` (string): Date range in YYYY-MM-DD format
  - Optional: `periods`, `timeframe`, `tracking_categories`

- `xero_get_bank_summary`
  - Get bank account balances and movements
  - Optional: `from_date`, `to_date` for specific period

#### Data Access
- `xero_get_accounts`
  - List all accounts in the chart of accounts
  - Optional: `where` filter condition

- `xero_get_contacts`
  - Retrieve customer and supplier contacts
  - Optional: `where`, `page`, `search_term`, `include_archived`

- `xero_get_bank_transactions`
  - View bank transactions
  - Optional: `where`, `order`, `page`, `modified_after`

- `xero_get_invoices`
  - Access invoice data
  - Optional: Multiple filter options including `where`, `order`, `page`, `statuses`

#### Aging Reports
- `xero_get_aged_payables_by_contact`
  - View aged payables for a specific contact
  - Input: `contact_id` (string)
  - Optional: `date`, `from_date`, `to_date`

- `xero_get_aged_receivables_by_contact`
  - View aged receivables for a specific contact
  - Input: `contact_id` (string)
  - Optional: `date`, `from_date`, `to_date`

## Usage with Claude Desktop

To use this server with Claude Desktop, add the following configuration to the "mcpServers" section of your `claude_desktop_config.json`:

### Using uvx (Recommended)

```json
{
  "mcpServers": {
    "Xero App": {
      "command": "~/.cargo/bin/uvx",
      "args": [
        "--from",
        "git+https://github.com/semicolonio/xero-mcp.git",
        "xero-mcp"
      ],
      "env": {
        "XERO_CLIENT_ID": "your_client_id",
        "XERO_CLIENT_SECRET": "your_client_secret"
      }
    }
  }
}
```

Notes:
- Replace `~/.cargo/bin/uvx` with your actual uvx path
  - Unix/macOS: `~/.cargo/bin/uvx`
  - Windows: `%USERPROFILE%\.cargo\bin\uvx`
- Replace `your_client_id` and `your_client_secret` with your Xero API credentials
- The server requires OAuth2 authentication on first use

## Prerequisites

1. Install uvx:
```bash
cargo install uvx
```

2. Get Xero API Credentials:
- Go to [Xero Developer Portal](https://developer.xero.com)
- Create a new app
- Set redirect URI to: `http://localhost:8000/callback`
- Copy Client ID and Client Secret

## Authentication

The server handles OAuth2 authentication automatically:
1. On first use, it opens your browser
2. Log in to your Xero account
3. Grant requested permissions
4. Tokens are securely stored and auto-refreshed

## Example Usage

```python
# Get all bank accounts
accounts = await xero_get_accounts(where='Type=="BANK"')

# Get balance sheet for specific date
balance_sheet = await xero_get_balance_sheet(date="2024-01-31")

# Get recent bank transactions
transactions = await xero_get_bank_transactions(
    where='Type=="SPEND"',
    order="Date DESC",
    page=1
)
```

## Data Storage

The server maintains a local SQLite database (`config/xero_analytics.db`) for:
- Token management
- Sync statistics
- Cache optimization

## Error Handling

Built-in handling for common issues:
- API rate limits
- Network connectivity
- Authentication failures
- Invalid parameters

## License

This project is licensed under the MIT License.