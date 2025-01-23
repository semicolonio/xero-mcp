import sqlite3
from venv import logger
from fastmcp import FastMCP, Context
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
import json
import os
from pathlib import Path
import webbrowser
import asyncio
from aiohttp import web
import secrets
from dotenv import load_dotenv
from urllib.parse import urlencode

# Import Xero SDK components
from xero_python.accounting import AccountingApi
from xero_python.identity import IdentityApi
from xero_python.api_client import ApiClient
from xero_python.api_client.configuration import Configuration
from xero_python.api_client.oauth2 import OAuth2Token
from xero_python.api_client.serializer import serialize_list
from authlib.integrations.requests_client import OAuth2Session

# Constants for OAuth2
AUTHORIZATION_URL = "https://login.xero.com/identity/connect/authorize"
TOKEN_URL = "https://identity.xero.com/connect/token"

# Setup config directory
if os.getenv("CONFIG_DIR"):
    CONFIG_DIR = Path(os.getenv("CONFIG_DIR"))
else:
    CONFIG_DIR = Path(__file__).parent / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv()


# Models for type safety and validation
class XeroAuth(BaseModel):
    client_id: str
    client_secret: str
    redirect_uri: str = "http://localhost:8000/callback"
    scope: List[str] = [
        "offline_access",
        "openid",
        "profile",
        "email",
        "accounting.transactions.read",
        "accounting.contacts.read",
        "accounting.settings.read",
        "accounting.reports.read",
    ]

    @classmethod
    def from_env(cls) -> "XeroAuth":
        """Create XeroAuth from environment variables"""
        client_id = os.getenv("XERO_CLIENT_ID")
        client_secret = os.getenv("XERO_CLIENT_SECRET")

        if not client_id or not client_secret:
            raise ValueError(
                "Missing Xero credentials. Please set XERO_CLIENT_ID and XERO_CLIENT_SECRET in .env file"
            )

        return cls(client_id=client_id, client_secret=client_secret)


class XeroToken(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: float
    token_type: str = "Bearer"
    scope: List[str] = []


class AuthServer:
    def __init__(self, xero_client):
        self.xero_client = xero_client
        self.app = web.Application()
        self.app.router.add_get("/callback", self.handle_callback)
        self.auth_future: Optional[asyncio.Future] = None
        self.state = secrets.token_urlsafe(32)
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None

        # Read the HTML template
        template_path = Path(__file__).parent / "auth_success.html"
        try:
            self.success_template = template_path.read_text()
        except Exception as e:
            logger.error(f"Failed to read auth success template: {e}")
            self.success_template = """
                <html><body>
                    <h1>Authentication Successful!</h1>
                    <p>You can close this window now.</p>
                    <script>window.close()</script>
                </body></html>
            """

    async def handle_callback(self, request: web.Request) -> web.Response:
        """Handle OAuth callback"""
        try:
            # Verify state to prevent CSRF
            if request.query.get("state") != self.state:
                return web.Response(text="Invalid state parameter", status=400)

            # Exchange code for token
            code = request.query.get("code")
            if not code:
                return web.Response(text="No code provided", status=400)

            await self.xero_client.exchange_code(code)

            # Return the HTML template
            self.auth_future.set_result(True)
            return web.Response(text=self.success_template, content_type="text/html")

        except Exception as e:
            self.auth_future.set_exception(e)
            return web.Response(text=str(e), status=500)

    async def start(self, port: int = 8000, max_retries: int = 3) -> int:
        """Start local auth server with retry logic"""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        # Try ports in sequence if default is taken
        for retry in range(max_retries):
            try:
                current_port = port + retry
                self.site = web.TCPSite(self.runner, "localhost", current_port)
                await self.site.start()
                return current_port
            except OSError as e:
                if e.errno == 48 and retry < max_retries - 1:  # Address in use
                    continue
                raise  # Re-raise if we're out of retries or different error

    async def cleanup(self) -> None:
        """Cleanup server resources"""
        try:
            if self.site:
                await self.site.stop()
            if self.runner:
                await self.runner.cleanup()
        except Exception as e:
            logger.error(f"Error during auth server cleanup: {e}")

    def get_redirect_uri(self, port: int = 8000) -> str:
        """Get redirect URI for auth flow"""
        return f"http://localhost:{port}/callback"


mcp = FastMCP(
    "Xero App",
    dependencies=[
        "aiohttp",
        "xero-python",
        "python-dotenv",
        "pydantic",
        "authlib",
        "aiohttp",
        "requests",
    ],
)


# Auth management
class XeroClient:
    def __init__(self):
        self.token_path = CONFIG_DIR / "token.json"
        self.auth_server = AuthServer(self)
        self._token: Optional[XeroToken] = None
        self._api_client: Optional[ApiClient] = None
        self._tenant_id: Optional[str] = None

        # Load client credentials from .env
        try:
            self.auth_config = XeroAuth.from_env()
        except ValueError as e:
            print(f"Error loading Xero credentials: {e}")
            self.auth_config = None

    @property
    def token(self) -> Optional[XeroToken]:
        if not self._token and self.token_path.exists():
            try:
                data = json.loads(self.token_path.read_text())
                self._token = XeroToken(**data)
            except (json.JSONDecodeError, OSError) as e:
                print(f"Error loading token: {e}")
                return None
        return self._token

    @token.setter
    def token(self, value: XeroToken):
        self._token = value
        try:
            self.token_path.write_text(value.json())
        except OSError as e:
            print(f"Error saving token: {e}")

    async def ensure_client(self) -> ApiClient:
        """Get or create authenticated API client"""
        if not self._api_client:
            config = Configuration(
                debug=False,  # Set to False to avoid excessive logging
                oauth2_token=OAuth2Token(
                    client_id=self.auth_config.client_id,
                    client_secret=self.auth_config.client_secret,
                ),
            )

            # Initialize with current token if available
            if self.token:
                config.access_token = self.token.access_token

            self._api_client = ApiClient(config)

            # Set up token management
            @self._api_client.oauth2_token_getter
            def obtain_xero_oauth2_token():
                if not self.token:
                    return None
                return {
                    "access_token": self.token.access_token,
                    "refresh_token": self.token.refresh_token,
                    "expires_in": int(
                        self.token.expires_at - datetime.utcnow().timestamp()
                    ),
                    "token_type": self.token.token_type,
                    "scope": self.token.scope,
                }

            @self._api_client.oauth2_token_saver
            def store_xero_oauth2_token(token):
                # Update the token when refreshed
                self.token = XeroToken(
                    access_token=token["access_token"],
                    refresh_token=token["refresh_token"],
                    expires_at=datetime.utcnow().timestamp() + token["expires_in"],
                    token_type=token["token_type"],
                    scope=(
                        token.get("scope", "").split()
                        if isinstance(token.get("scope"), str)
                        else []
                    ),
                )

        # Ensure we have a valid token and it's set in the configuration
        if self.token:
            self._api_client.configuration.access_token = self.token.access_token

        return self._api_client

    async def get_tenant_id(self) -> str:
        """Get the tenant ID for the authenticated organization"""
        if not self._tenant_id:
            api_client = await self.ensure_client()
            identity_api = IdentityApi(api_client)
            connections = identity_api.get_connections()
            for connection in connections:
                if connection.tenant_type == "ORGANISATION":
                    self._tenant_id = connection.tenant_id
                    break
        return self._tenant_id

    def get_auth_url(self, port: int = 8000) -> str:
        """Get Xero OAuth authorization URL"""
        params = {
            "response_type": "code",
            "client_id": self.auth_config.client_id,
            "redirect_uri": self.auth_server.get_redirect_uri(port),
            "scope": " ".join(self.auth_config.scope),
            "state": self.auth_server.state,
        }
        return f"https://login.xero.com/identity/connect/authorize?{urlencode(params)}"

    async def start_auth_flow(self, port: int = 8000) -> bool:
        """Start complete OAuth flow with local server"""
        await self.ensure_auth_config()

        try:
            # Start local server with retry logic
            actual_port = await self.auth_server.start(port)
            
            # Create future to wait for callback
            self.auth_server.auth_future = asyncio.Future()

            # Open browser with actual port
            auth_url = self.get_auth_url(actual_port)
            webbrowser.open(auth_url)

            # Wait for callback
            await self.auth_server.auth_future
            return True
            
        except Exception as e:
            raise Exception(f"Authentication failed: {str(e)}")
        finally:
            # Always cleanup the server
            await self.auth_server.cleanup()

    async def exchange_code(self, code: str) -> XeroToken:
        """Exchange authorization code for tokens"""
        await self.ensure_auth_config()

        # Create OAuth2 session for token exchange
        client = OAuth2Session(
            self.auth_config.client_id,
            self.auth_config.client_secret,
            scope=" ".join(self.auth_config.scope),
            redirect_uri=self.auth_server.get_redirect_uri(),
        )

        # Exchange the code for tokens
        token = client.fetch_token(
            TOKEN_URL, code=code, grant_type="authorization_code"
        )

        # Convert to our token model
        xero_token = XeroToken(
            access_token=token["access_token"],
            refresh_token=token["refresh_token"],
            expires_at=datetime.utcnow().timestamp() + token["expires_in"],
            token_type=token["token_type"],
            scope=(
                token.get("scope", "").split()
                if isinstance(token.get("scope"), str)
                else []
            ),
        )
        self.token = xero_token
        return xero_token

    async def refresh_if_needed(self):
        """Refresh token if expired"""
        await self.ensure_auth_config()

        if not self.token:
            raise ValueError("No token available")

        if datetime.utcnow().timestamp() >= self.token.expires_at:
            # Create OAuth2 session for token refresh
            client = OAuth2Session(
                self.auth_config.client_id,
                self.auth_config.client_secret,
                scope=" ".join(self.auth_config.scope),
            )

            # Refresh the token
            token = client.refresh_token(
                TOKEN_URL, refresh_token=self.token.refresh_token
            )

            # Convert to our token model
            self.token = XeroToken(
                access_token=token["access_token"],
                refresh_token=token["refresh_token"],
                expires_at=datetime.utcnow().timestamp() + token["expires_in"],
                token_type=token["token_type"],
                scope=(
                    token.get("scope", "").split()
                    if isinstance(token.get("scope"), str)
                    else []
                ),
            )

    async def ensure_auth_config(self):
        """Ensure auth config is available"""
        if not self.auth_config:
            raise ValueError(
                "Xero credentials not configured. Please set XERO_CLIENT_ID and XERO_CLIENT_SECRET in .env file"
            )


# Initialize Xero client
xero = XeroClient()


# Auth tools
@mcp.tool(description="Tool to start Xero OAuth flow and automatically handle callback")
async def xero_authenticate(ctx: Context) -> str:
    """Start Xero OAuth flow and automatically handle callback"""
    ctx.info("Starting Xero OAuth flow")
    if xero.token and xero.token.expires_at > datetime.utcnow().timestamp():
        return "Already authenticated"

    try:
        await xero.start_auth_flow()
        return "Authentication completed successfully"
    except Exception as e:
        return f"Authentication failed: {str(e)}"


@mcp.tool(description="Tool to check current authentication status")
async def xero_get_auth_status(ctx: Context) -> str:
    """Check current authentication status"""
    ctx.info("Checking Xero authentication status")
    if not xero.token:
        return "Not authenticated"

    expires_in = xero.token.expires_at - datetime.utcnow().timestamp()
    if expires_in < 0:
        return "Token expired"
    return f"Authenticated (token expires in {int(expires_in)} seconds)"


async def xero_call_endpoint(endpoint: str, params: dict | None = None):
    """Call a specific Xero API endpoint to interact with Xero's accounting data. Common endpoints include get_accounts, get_contacts, get_bank_transactions, get_payments, etc. To see all available endpoints, use xero_get_existing_endpoints(). If you need details about a specific endpoint's parameters, return types and field definitions, call xero_get_endpoint_docs() with the endpoint name. Each endpoint may require different parameters - if you're unsure about what parameters are needed, check the endpoint documentation first."""
    await xero.refresh_if_needed()
    api_client = await xero.ensure_client()
    accounting_api = AccountingApi(api_client)
    tenant_id = await xero.get_tenant_id()
    params = params or {}
    func = getattr(accounting_api, endpoint)
    if not func:
        raise ValueError(f"Endpoint {endpoint} not found")
    response = func(tenant_id, **params)
    if not response:
        raise ValueError(f"No data returned from endpoint {endpoint}")
    return response


@mcp.tool(
    description="""Tool to retrieve accounts from Xero's accounting system.
    Returns account details including:
    - Code: Customer defined alpha numeric account code (e.g. 200 or SALES)
    - Name: Name of account 
    - Type: Account type (e.g. BANK, REVENUE, CURRENT)
    - BankAccountNumber: For bank accounts only
    - Status: ACTIVE or ARCHIVED
    - Description: Account description (except bank accounts)
    - BankAccountType: For bank accounts only
    - CurrencyCode: For bank accounts only
    - TaxType: Tax type code
    - EnablePaymentsToAccount: Whether account can have payments applied
    - ShowInExpenseClaims: Whether available for expense claims
    - AccountID: Unique Xero identifier
    - Class: Account class type
    - SystemAccount: System account type if applicable
    - HasAttachments: Whether account has attachments
    - UpdatedDateUTC: Last modified date
    
    Parameters:
        where: Optional filter by any element
            Example: 'Type == "BANK"'
            
    Returns:
        str: JSON string containing list of accounts with their details
    """
)
async def xero_get_accounts(where: str = None) -> str:
    """Get all accounts from Xero"""
    params = {"where": where} if where else None
    response = await xero_call_endpoint("get_accounts", params=params)
    return json.dumps(serialize_list(response.accounts), indent=2)


@mcp.tool(
    description="""Tool to retrieve contacts (customers and suppliers) from Xero.
    Returns contact details including:
    - ContactID: Unique Xero identifier
    - ContactNumber: External system identifier (Contact Code in UI)
    - AccountNumber: User defined account number
    - Name: Full name of contact/organization
    - FirstName/LastName: Contact person name
    - EmailAddress: Contact email
    - Addresses: Physical and postal addresses
    - Phones: Contact phone numbers
    - IsSupplier/IsCustomer: Whether contact is supplier/customer
    - DefaultCurrency: Default invoice currency
    - TaxNumber: Tax/VAT/GST number
    - AccountsReceivableTaxType: Default tax for AR invoices
    - AccountsPayableTaxType: Default tax for AP invoices
    - ContactStatus: ACTIVE or ARCHIVED
    - UpdatedDateUTC: Last modified date
    
    For optimal performance:
    - Use page parameter to retrieve up to 100 contacts per call
    - Filter using optimized fields: Name, EmailAddress, AccountNumber
    - Use SearchTerm for partial text search across multiple fields
    - Use summaryOnly=true for lightweight response
    - Use IDs parameter to retrieve specific contacts
    
    Returns a JSON string containing contacts list."""
)
async def xero_get_contacts(
    where: str = None,
    page: int = None,
    search_term: str = None,
    contact_ids: str = None,
    include_archived: bool = False,
    summary_only: bool = False,
) -> str:
    """ """
    params = {}
    if where:
        params["where"] = where
    if page:
        params["page"] = page
    if search_term:
        params["search_term"] = search_term
    if contact_ids:
        params["ids"] = contact_ids
    if include_archived:
        params["include_archived"] = include_archived
    if summary_only:
        params["summary_only"] = summary_only

    return await xero_call_endpoint("get_contacts", params=params)


@mcp.tool(
    description="""Retrieves a Balance Sheet report from Xero for a specified date.

    The Balance Sheet shows the financial position at the end of the specified month, including:
    - Assets (Bank accounts, Current assets, Fixed assets etc)
    - Liabilities (Current liabilities, Non-current liabilities etc) 
    - Equity
    
    It also compares values to the same month in the previous year.

    Required parameters:
    - date: Report date in YYYY-MM-DD format (e.g. 2024-01-31)

    Optional parameters:
    - periods: Number of periods to compare (1-11)
    - timeframe: Period size to compare (MONTH, QUARTER, YEAR)
    - tracking_option_id_1: Filter by first tracking category option
    - tracking_option_id_2: Filter by second tracking category option  
    - standard_layout: Set true to ignore custom report layouts
    - payments_only: Set true to show only cash transactions

    Returns a JSON string containing the Balance Sheet report data."""
)
async def xero_get_balance_sheet(
    date: str,
    periods: int = None,
    timeframe: str = None,
    tracking_option_id_1: str = None,
    tracking_option_id_2: str = None,
    standard_layout: bool = True,
    payments_only: bool = False,
) -> str:
    params = {
        "date": date,
        "standard_layout": str(standard_layout).lower(),
        "payments_only": str(payments_only).lower(),
    }

    if periods:
        params["periods"] = periods
    if timeframe:
        params["timeframe"] = timeframe
    if tracking_option_id_1:
        params["tracking_option_id_1"] = tracking_option_id_1
    if tracking_option_id_2:
        params["tracking_option_id_2"] = tracking_option_id_2

    response = await xero_call_endpoint("get_report_balance_sheet", params=params)
    return json.dumps(serialize_list(response.reports), indent=2)


@mcp.tool(
    description="""Retrieves a Profit and Loss report from Xero for a specified date range.

    The Profit and Loss report shows the financial performance over the specified period, including:
    - Income
    - Expenses 
    - Net profit/loss

    Required parameters:
    - from_date: Start date in YYYY-MM-DD format (e.g. 2024-01-01)
    - to_date: End date in YYYY-MM-DD format (e.g. 2024-01-31)

    Optional parameters:
    - periods: Number of periods to compare (1-11)
    - timeframe: Period size to compare (MONTH, QUARTER, YEAR)
    - tracking_category_id: Filter by first tracking category, shows figures for each option
    - tracking_category_id_2: Filter by second tracking category, shows figures for each option combination
    - tracking_option_id: When used with tracking_category_id, shows figures for just one option
    - tracking_option_id_2: When used with tracking_category_id_2, shows figures for just one option
    - standard_layout: Set true to ignore custom report layouts
    - payments_only: Set true to show only cash transactions

    Note: When using periods with from_date/to_date, the date range applies to each period.
    For consistent month data across periods, start in a 31-day month.

    Returns a JSON string containing the Profit and Loss report data."""
)
async def xero_get_profit_and_loss(
    from_date: str,
    to_date: str,
    periods: int = None,
    timeframe: str = None,
    tracking_category_id: str = None,
    tracking_category_id_2: str = None,
    tracking_option_id: str = None,
    tracking_option_id_2: str = None,
    standard_layout: bool = True,
    payments_only: bool = False,
) -> str:
    params = {
        "from_date": from_date,
        "to_date": to_date,
        "standard_layout": str(standard_layout).lower(),
        "payments_only": str(payments_only).lower(),
    }

    if periods:
        params["periods"] = periods
    if timeframe:
        params["timeframe"] = timeframe
    if tracking_category_id:
        params["tracking_category_id"] = tracking_category_id
    if tracking_category_id_2:
        params["tracking_category_id_2"] = tracking_category_id_2
    if tracking_option_id:
        params["tracking_option_id"] = tracking_option_id
    if tracking_option_id_2:
        params["tracking_option_id_2"] = tracking_option_id_2

    response = await xero_call_endpoint("get_report_profit_and_loss", params=params)
    return json.dumps(serialize_list(response.reports), indent=2)


@mcp.tool(
    description="""Tool to retrieve an Aged Payables by Contact report from Xero.
    Returns aged payables report details including:
    - Date
    - Reference
    - Due Date
    - Total Amount
    - Amount Paid
    - Amount Credited 
    - Amount Due
    - Aging periods (current, overdue)
    
    Parameters:
        contactID: Required - Contact ID to get aged payables for
        date: Optional - Show payments up to this date (defaults to end of current month)
        fromDate: Optional - Show payable invoices from this date
        toDate: Optional - Show payable invoices to this date
    
    Returns:
        str: JSON string containing aged payables report with payment details
    """
)
async def xero_get_aged_payables_by_contact(
    contact_id: str,
    date: str = None,
    from_date: str = None,
    to_date: str = None,
) -> str:
    params = {"contact_id": contact_id}

    if date:
        params["date"] = date
    if from_date:
        params["from_date"] = from_date
    if to_date:
        params["to_date"] = to_date

    response = await xero_call_endpoint(
        "get_report_aged_payables_by_contact", params=params
    )
    return json.dumps(serialize_list(response.reports), indent=2)


@mcp.tool(
    description="""Tool to retrieve an Aged Receivables by Contact report from Xero.
    Returns aged receivables report details including:
    - Date
    - Reference
    - Due Date
    - Total Amount
    - Amount Paid
    - Amount Credited 
    - Amount Due
    - Aging periods (current, overdue)
    
    Parameters:
        contactID: Required - Contact ID to get aged receivables for
        date: Optional - Show payments up to this date (defaults to end of current month)
        fromDate: Optional - Show receivable invoices from this date
        toDate: Optional - Show receivable invoices to this date
    
    Returns:
        str: JSON string containing aged receivables report with payment details
    """
)
async def xero_get_aged_receivables_by_contact(
    contact_id: str,
    date: str = None,
    from_date: str = None,
    to_date: str = None,
) -> str:
    params = {"contact_id": contact_id}

    if date:
        params["date"] = date
    if from_date:
        params["from_date"] = from_date
    if to_date:
        params["to_date"] = to_date

    response = await xero_call_endpoint(
        "get_report_aged_receivables_by_contact", params=params
    )
    return json.dumps(serialize_list(response.reports), indent=2)


@mcp.tool(
    description="""Tool to retrieve a Bank Summary report from Xero.
    Returns bank account balances and cash movements including:
    - Opening balance for each bank account
    - Cash received
    - Cash spent
    - Closing balance
    - Net cash movement
    
    Optional parameters:
        from_date: Start date for the report (e.g. 2024-01-01)
        to_date: End date for the report (e.g. 2024-01-31)
    
    Returns:
        str: JSON string containing bank summary report with balances and cash movements
    """
)
async def xero_get_bank_summary(
    from_date: str = None,
    to_date: str = None,
) -> str:
    params = {}

    if from_date:
        params["from_date"] = from_date
    if to_date:
        params["to_date"] = to_date

    response = await xero_call_endpoint("get_report_bank_summary", params=params)
    return json.dumps(serialize_list(response.reports), indent=2)


@mcp.tool(
    description="""Tool to retrieve a Budget Summary report from Xero.
    Returns a summary of monthly budget including:
    - Monthly budget figures
    - Actual vs budget comparisons
    - Budget variances
    
    Optional parameters:
        date: Report date (e.g. 2024-01-31)
        periods: Number of periods to compare (integer between 1 and 12)
        timeframe: Period size to compare (1=month, 3=quarter, 12=year)
    
    Returns:
        str: JSON string containing budget summary report with monthly totals and comparisons
    """
)
async def xero_get_budget_summary(
    date: str = None,
    periods: int = None,
    timeframe: int = None,
) -> str:
    params = {}

    if date:
        params["date"] = date
    if periods:
        params["periods"] = periods
    if timeframe:
        params["timeframe"] = timeframe

    response = await xero_call_endpoint("get_report_budget_summary", params=params)
    return json.dumps(serialize_list(response.reports), indent=2)


@mcp.tool(
    description="""Tool to retrieve an Executive Summary report from Xero.
    Returns a business performance summary including:
    - Monthly totals
    - Common business ratios
    - Key performance indicators
    - Cash position
    - Profitability metrics
    
    Optional parameters:
        date: Report date (e.g. 2024-01-31)
    
    Returns:
        str: JSON string containing executive summary report with business performance metrics
    """
)
async def xero_get_executive_summary(
    date: str = None,
) -> str:
    params = {}

    if date:
        params["date"] = date

    response = await xero_call_endpoint("get_report_executive_summary", params=params)
    return json.dumps(serialize_list(response.reports), indent=2)


@mcp.tool(
    description="""Tool to retrieve bank transactions from Xero.
    Returns bank transaction details including:
    - Type (SPEND/RECEIVE/SPEND-PREPAYMENT/RECEIVE-PREPAYMENT/SPEND-OVERPAYMENT/RECEIVE-OVERPAYMENT)
    - Contact details
    - Line items
    - Bank account details
    - Date, reference, currency
    - Status and reconciliation state
    - Amounts (subtotal, tax, total)
    
    Optional parameters:
        where: Filter by any element (e.g. Type=="SPEND", Status=="AUTHORISED")
        order: Order by any element
        page: Page number for pagination (up to 100 transactions per page)
        modified_after: Only return transactions created/modified after this timestamp
    
    Returns:
        str: JSON string containing bank transactions data
    """
)
async def xero_get_bank_transactions(
    where: str = None,
    order: str = None,
    page: int = None,
    modified_after: str = None,
) -> str:
    params = {}

    if where:
        params["where"] = where
    if order:
        params["order"] = order
    if page:
        params["page"] = page
    if modified_after:
        params["modified_after"] = modified_after

    response = await xero_call_endpoint("get_bank_transactions", params=params)
    return json.dumps(serialize_list(response.bank_transactions), indent=2)


@mcp.tool(
    description="""Tool to retrieve payments from Xero.
    Returns payment details including:
    - Date and amount
    - Payment type and status
    - Reference
    - Bank account details
    - Invoice/credit note details
    - Reconciliation status
    
    Optional parameters:
        where: Filter by any element (e.g. Status=="AUTHORISED")
        order: Order by any element
        page: Page number for pagination (up to 100 payments per page)
        modified_after: Only return payments created/modified after this timestamp
    
    Returns:
        str: JSON string containing payments data
    """
)
async def xero_get_payments(
    where: str = None,
    order: str = None,
    page: int = None,
    modified_after: str = None,
) -> str:
    params = {}

    if where:
        params["where"] = where
    if order:
        params["order"] = order
    if page:
        params["page"] = page
    if modified_after:
        params["modified_after"] = modified_after

    response = await xero_call_endpoint("get_payments", params=params)
    return json.dumps(serialize_list(response.payments), indent=2)


@mcp.tool(
    description="""Tool to retrieve invoices from Xero.
    Returns invoice details including:
    - Type (ACCREC/ACCPAY)
    - Contact details
    - Line items with descriptions, quantities, amounts
    - Dates (invoice date, due date)
    - Status and amounts (due, paid, credited)
    - Currency and tax details
    
    Optional parameters:
        where: Filter by any element (e.g. Status=="AUTHORISED", Type=="ACCREC")
        order: Order by any element (optimized for: InvoiceId, UpdatedDateUTC, Date)
        page: Page number for pagination (up to 100 invoices per page)
        modified_after: Only return invoices created/modified after this timestamp
        ids: Filter by comma-separated list of invoice IDs
        invoice_numbers: Filter by comma-separated list of invoice numbers
        contact_ids: Filter by comma-separated list of contact IDs
        statuses: Filter by comma-separated list of statuses
        summary_only: Return lightweight response without payments, attachments, line items
    
    Returns:
        str: JSON string containing invoices data
    """
)
async def xero_get_invoices(
    where: str = None,
    order: str = None,
    page: int = None,
    modified_after: str = None,
    ids: str = None,
    invoice_numbers: str = None,
    contact_ids: str = None,
    statuses: str = None,
    summary_only: bool = False,
) -> str:
    params = {}
    
    if where:
        params["where"] = where
    if order:
        params["order"] = order
    if page:
        params["page"] = page
    if modified_after:
        params["modified_after"] = modified_after
    if ids:
        params["ids"] = ids
    if invoice_numbers:
        params["invoice_numbers"] = invoice_numbers
    if contact_ids:
        params["contact_ids"] = contact_ids
    if statuses:
        params["statuses"] = statuses
    if summary_only:
        params["summary_only"] = summary_only

    response = await xero_call_endpoint("get_invoices", params=params)
    return json.dumps(serialize_list(response.invoices), indent=2)



# Helper functions
def get_db_connection() -> sqlite3.Connection:
    """Get SQLite connection with proper configuration"""
    db_path = CONFIG_DIR / "xero_analytics.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_tables_exist(conn: sqlite3.Connection):
    """Ensure all required tables exist"""
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time TEXT,
            end_time TEXT,
            records_processed TEXT,
            errors TEXT
        )
    """
    )
    conn.commit()


# @mcp.prompt(
#     description="Guide users in selecting the best tools for Xero API queries."
# )
# async def xero_tool_selector(ctx: Context, query: str) -> str:
#     """
#     This prompt assists users in selecting the most appropriate tools and API endpoints for interacting with Xero's accounting system.

#     When using this prompt, consider the following steps to determine the best course of action:
#     1. Identify the type of data or action you need. Common categories include accounts, contacts, bank transactions, and payments.
#     2. Use specific keywords related to your query to narrow down the options. For example, if you need information about financial accounts, focus on terms like 'accounts', 'balances', or 'transactions'.
#     3. Refer to the available tools and endpoints that match your query. Each tool is designed to handle specific types of data or actions.
#     4. If unsure about the parameters or data structure, consult the endpoint documentation or model field definitions for detailed information.
#     5. Execute the selected tool or endpoint to retrieve or manipulate the data as needed.

#     This structured approach ensures efficient and accurate interaction with the Xero API, helping you achieve your objectives effectively.
#     """
#     return """\
#     This prompt assists users in selecting the most appropriate tools and API endpoints for interacting with Xero's accounting system.

#     When using this prompt, consider the following steps to determine the best course of action:
#     1. Identify the type of data or action you need. Common categories include accounts, contacts, bank transactions, and payments.
#     2. Use specific keywords related to your query to narrow down the options. For example, if you need information about financial accounts, focus on terms like 'accounts', 'balances', or 'transactions'.
#     3. Refer to the available tools and endpoints that match your query. Each tool is designed to handle specific types of data or actions.
#     4. If unsure about the parameters or data structure, consult the endpoint documentation or model field definitions for detailed information.
#     5. Execute the selected tool or endpoint to retrieve or manipulate the data as needed.

#     This structured approach ensures efficient and accurate interaction with the Xero API, helping you achieve your objectives effectively.\
#     """
