# Xero MCP Integration

A powerful integration that connects Claude with your Xero accounting data, enabling intelligent financial analysis and insights.

## Features

### 1. Financial Dashboard
- Quick access to financial overview
- Real-time bank balances
- Key performance metrics
- Executive summaries

### 2. Financial Reports
- Balance Sheet analysis
- Profit & Loss statements
- Cash flow tracking
- Budget variance analysis

### 3. Account Management
- Chart of accounts access
- Receivables monitoring
- Payables tracking
- Account reconciliation

### 4. Transaction Analysis
- Recent transaction review
- Bank transaction history
- Payment tracking
- Invoice management

## Getting Started

1. Set up your Xero credentials:
   - Create a `.env` file in the root directory
   - Add your Xero API credentials:
     ```
     XERO_CLIENT_ID=your_client_id
     XERO_CLIENT_SECRET=your_client_secret
     ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the integration:
   ```bash
   python -m xero_mcp.app
   ```

## Using the Integration

### Available Resources

Access financial data through organized resource paths:

- `xero://dashboard/overview` - Comprehensive financial overview
- `xero://reports/balance_sheet` - Balance sheet reports
- `xero://reports/profit_and_loss` - P&L statements
- `xero://accounts/chart` - Chart of accounts
- `xero://accounts/receivables` - Receivables summary
- `xero://accounts/payables` - Payables summary
- `xero://transactions/recent` - Recent transactions

### Financial Analysis Prompts

Use these prompts for intelligent financial analysis:

1. **Financial Health Analysis**
   - Comprehensive financial health assessment
   - Key metrics and ratios
   - Industry benchmarks
   - Actionable recommendations

2. **Cash Flow Analysis**
   - Cash flow patterns
   - Working capital management
   - Forecasting and planning
   - Optimization strategies

3. **Receivables Management**
   - Collection health metrics
   - Risk analysis
   - Action plans
   - Performance tracking

4. **Budget Analysis**
   - Variance analysis
   - Performance tracking
   - Trend identification
   - Strategic planning

## Example Usage

Ask Claude questions like:

- "How is our overall financial health looking?"
- "Analyze our cash flow for the last 3 months"
- "Review our aged receivables and suggest collection strategies"
- "Compare our budget performance against actuals"
- "What are our key financial metrics trending towards?"

## Security

This integration:
- Uses secure OAuth2 authentication
- Stores credentials securely
- Implements token refresh
- Maintains secure connections

## Support

For issues or questions:
1. Check the documentation
2. Review the troubleshooting guide
3. Submit an issue on GitHub

## Future Enhancements

Planned features:
- Additional financial analysis tools
- Custom report generation
- Advanced forecasting capabilities
- Integration with other financial services
