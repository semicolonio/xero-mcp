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

    async def start(self, port: int = 8000) -> None:
        """Start local auth server"""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "localhost", port)
        await self.site.start()

    async def cleanup(self) -> None:
        """Cleanup server resources"""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()

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

        # Start local server
        await self.auth_server.start(port)

        # Create future to wait for callback
        self.auth_server.auth_future = asyncio.Future()

        # Open browser
        auth_url = self.get_auth_url(port)
        webbrowser.open(auth_url)

        try:
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
    """Get contacts from Xero's accounting system

    Parameters:
        where: Filter using optimized fields only. Examples:
            'Name="ABC Limited"'
            'EmailAddress="email@example.com"'
            'AccountNumber="ABC-100"'
        page: Page number for paginated results (100 contacts per page)
        search_term: Text search across Name, FirstName, LastName, ContactNumber,
                    CompanyNumber, EmailAddress
        contact_ids: Comma-separated list of ContactIDs to retrieve
        include_archived: Include archived contacts in response
        summary_only: Return lightweight response excluding heavy computation fields

    Returns:
        str: JSON string containing list of contacts with their details
    """
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
    description="""Tool to retrieve a Balance Sheet report from Xero.
    Use this tool to get a Balance Sheet report showing:
    - Assets
    - Liabilities 
    - Equity
    
    Parameters allow you to:
    - Specify report date
    - Compare multiple periods
    - Filter by tracking categories
    - Choose between standard and custom layouts
    - Get cash basis reporting
    
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
    """Get Balance Sheet report from Xero
    
    Parameters:
        date: The date of the Balance Sheet report (YYYY-MM-DD)
        periods: Number of periods to compare
        timeframe: Period size to compare (MONTH, QUARTER, YEAR)
        tracking_option_id_1: First tracking category ID to filter by
        tracking_option_id_2: Second tracking category ID to filter by
        standard_layout: Use standard layout (True) or custom layout (False)
        payments_only: Return cash basis Balance Sheet (True) or accrual basis (False)
    
    Returns:
        str: JSON string containing Balance Sheet report data
    """
    params = {
        "date": date,
        "standard_layout": str(standard_layout).lower(),
        "payments_only": str(payments_only).lower()
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
    description="""Tool to retrieve a Profit and Loss report from Xero.
    Use this tool to get a Profit and Loss report showing:
    - Revenue
    - Expenses
    - Net Profit/Loss
    
    Parameters allow you to:
    - Specify date range
    - Compare multiple periods
    - Filter by tracking categories
    - Choose between standard and custom layouts
    - Get cash basis reporting
    
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
    """Get Profit and Loss report from Xero
    
    Parameters:
        from_date: Start date of the report (YYYY-MM-DD)
        to_date: End date of the report (YYYY-MM-DD)
        periods: Number of periods to compare (1-12)
        timeframe: Period size to compare (MONTH, QUARTER, YEAR)
        tracking_category_id: First tracking category ID to filter by
        tracking_category_id_2: Second tracking category ID to filter by
        tracking_option_id: First tracking option ID to filter by
        tracking_option_id_2: Second tracking option ID to filter by
        standard_layout: Use standard layout (True) or custom layout (False)
        payments_only: Return cash basis P&L (True) or accrual basis (False)
    
    Returns:
        str: JSON string containing Profit and Loss report data
    """
    params = {
        "from_date": from_date,
        "to_date": to_date,
        "standard_layout": str(standard_layout).lower(),
        "payments_only": str(payments_only).lower()
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


# @mcp.tool(
#     description="""Tool to retrieve all bank transactions from Xero.
#     Use this tool to get details about bank transactions including:
#     - Deposits
#     - Withdrawals
#     - Bank transfers
#     - Reconciled and unreconciled transactions
#     Each transaction contains:
#     - Date
#     - Amount
#     - Reference
#     - Account details
#     - Contact information
#     - Reconciliation status
#     This is useful when you need to:
#     - Review banking activity
#     - Check transaction details
#     - Verify reconciliation status
#     - Track money movement between accounts
#     Returns a JSON string containing the bank transactions list."""
# )
# async def xero_get_bank_transactions(where: str) -> str:
#     """Get all bank transactions from Xero

#     Parameters:
#         where: A string of filters to apply to the bank transactions.
#             Example1: 'BankAccountID = "1234567890"'
#             Example2: 'BankAccountID = "1234567890" AND TransactionDate = "2024-01-01"'
#             Example3: 'BankAccountID = "1234567890" AND TransactionDate = "2024-01-01" AND Amount = 1000'
#             Example4: 'TransactionDate >= "2024-01-01" AND TransactionDate <= "2024-01-31"'

#     Returns:
#         str: JSON string containing list of bank transactions with their details
#     """
#     return await xero_call_endpoint("get_bank_transactions", params={"where": where})

# @mcp.tool(
#     description="""Tool to retrieve all payment records from Xero.
#     Use this tool to get details about payments including:
#     - Invoice payments
#     - Bill payments
#     - Prepayments
#     - Overpayments
#     Each payment record contains:
#     - Date
#     - Amount
#     - Payment type (cash, credit card, bank transfer etc)
#     - Account paid from/to
#     - Invoice/bill reference
#     - Status
#     This is useful when you need to:
#     - Track payment history
#     - Verify payment details
#     - Check payment methods used
#     - Review payment allocations
#     Returns a JSON string containing the payments list."""
# )
# async def xero_get_payments(where: str) -> str:
#     """Get all payments from Xero

#     Parameters:
#         where: A string of filters to apply to the payments.
#             Example1: 'Date = "2024-01-01"'
#             Example2: 'Date = "2024-01-01" AND ContactID = "1234567890"'
#             Example3: 'Date = "2024-01-01" AND ContactID = "1234567890" AND Amount = 1000'
#             Example4: 'Date >= "2024-01-01" AND Date <= "2024-01-31"'

#     Returns:
#         str: JSON string containing list of payments with their details
#     """
#     return await xero_call_endpoint("get_payments", params={"where": where})


def _get_endpoint_details(func, model_finder):
    doc = func.__doc__
    if doc is None or doc.strip() == "":
        return "No documentation available", "Unknown", ""

    if ":return: " not in doc:
        return doc, "Unknown", ""

    return_type_list = return_type = doc.split(":return: ")[1].strip()
    return_type_single = return_type_list[:-1]  # remove the last s character
    # Get the model class if it exists
    try:
        model_class_list = model_finder.find_model(return_type_list)
        model_class_single = model_finder.find_model(return_type_single)

        # Get fields from model
        if hasattr(model_class_list, "openapi_types"):
            fields = model_class_list.openapi_types
            field_info = "\n    Returned Object Fields:\n"
            for field, type_info in fields.items():
                field_info += f"      - {field}: {type_info}\n"

            if hasattr(model_class_single, "openapi_types"):
                fields = model_class_single.openapi_types
                field_info += f"\n    {return_type_single} Fields:\n"
                for field, type_info in fields.items():
                    field_info += f"      - {field}: {type_info}\n"
        else:
            field_info = "\n    Fields: Not available"
    except (ImportError, AttributeError):
        field_info = "\n    Fields: Not available"
    except (TypeError, AttributeError):
        return_type = "Unknown"
        field_info = ""

    return doc, return_type, field_info


# @mcp.tool(
#     description="""Tool to get a comprehensive list of available Xero API endpoints with their return types and field definitions.
#     Use this tool when you need to:
#     - Discover available Xero API endpoints
#     - Understand what data each endpoint returns
#     - View the structure and fields of returned objects
#     - Plan which endpoints to use for specific data needs
#     Returns a formatted string containing endpoint details including:
#     - Endpoint name
#     - Return type
#     - Available fields and their data types
#     - Brief description of functionality"""
# )
# async def xero_get_existing_endpoints() -> str:
#     """List all available Xero API endpoints with their return types and fields

#     Parameters:
#         No parameters required. This tool lists all available endpoints.

#     Returns:
#         str: Formatted string containing endpoint details, return types, and field definitions
#     """
#     api_client = await xero.ensure_client()
#     accounting_api = AccountingApi(api_client)

#     endpoints = ["get_accounts", "get_contacts", "get_bank_transactions", "get_payments", "get_invoices"]

#     model_finder = accounting_api.get_model_finder()
#     result = []
#     for endpoint in endpoints:
#         func = getattr(accounting_api, endpoint)
#         doc, return_type, field_info = _get_endpoint_details(func, model_finder)
#         result.append(f"{endpoint} -> {return_type}{field_info}")

#     return "\n".join(result)

# @mcp.tool(
#     description="""Tool to get detailed documentation for a specific Xero API endpoint.
#     Use this tool when you need to:
#     - Understand exactly how an endpoint works
#     - View all available parameters and options
#     - See the complete data structure returned
#     - Check field definitions and data types
#     - Verify endpoint requirements and constraints

#     Parameters:
#     - endpoint: The name of the endpoint to get documentation for (e.g. "get_accounts")

#     Returns a formatted string containing:
#     - Full endpoint documentation
#     - Return type details
#     - Complete field listing with types
#     - Usage examples if available"""
# )
# async def xero_get_endpoint_docs(endpoint: str, ctx: Context) -> str:
#     """Get detailed documentation for a specific Xero API endpoint

#     Parameters:
#         endpoint (str): Name of the endpoint to get documentation for.
#             Must be a valid endpoint name like:
#             - get_accounts
#             - get_contacts
#             - get_bank_transactions
#             - get_payments
#             - get_invoices

#     Returns:
#         str: Formatted string containing full endpoint documentation, return types, and field definitions

#     Raises:
#         AttributeError: If the endpoint name is not valid
#     """
#     ctx.info(f"Getting documentation for endpoint: {endpoint}")
#     api_client = await xero.ensure_client()
#     accounting_api = AccountingApi(api_client)
#     func = getattr(accounting_api, endpoint)
#     model_finder = accounting_api.get_model_finder()
#     doc, return_type, field_info = _get_endpoint_details(func, model_finder)
#     return f"Function: {endpoint}\nReturn Type: {return_type}\n{field_info}\n\nDocs:\n{doc}"

# @mcp.tool(
#     description="""Tool to get detailed field definitions for a specific Xero API model.
#     Use this tool when you need to:
#     - View all available fields in a model
#     - Check field data types and constraints
#     - Understand model structure
#     - Verify required vs optional fields

#     Parameters:
#     - model: The name of the model to get fields for (e.g. "Account", "Contact")

#     Returns a dictionary mapping field names to their OpenAPI type definitions."""
# )
# async def xero_get_model_fields(model: str, ctx: Context) -> str:
#     """Get detailed field definitions for a specific Xero API model

#     Parameters:
#         model (str): Name of the model to get field definitions for.
#             Must be a valid model name like:
#             - Account
#             - Contact
#             - BankTransaction
#             - Payment
#             - Invoice

#     Returns:
#         str: Dictionary mapping field names to their OpenAPI type definitions

#     Raises:
#         ImportError: If the model name is not valid
#         AttributeError: If the model does not have OpenAPI type definitions
#     """
#     ctx.info(f"Getting fields for model: {model}")
#     api_client = await xero.ensure_client()
#     accounting_api = AccountingApi(api_client)
#     model_finder = accounting_api.get_model_finder()
#     model_class = model_finder.find_model(model)
#     return json.dumps(model_class.openapi_types, indent=2)


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
