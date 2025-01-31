from contextlib import contextmanager
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
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
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


class AuthCallbackHandler(BaseHTTPRequestHandler):
    def __init__(self, xero_client, state, success_template, *args, **kwargs):
        self.xero_client = xero_client
        self.state = state
        self.success_template = success_template
        super().__init__(*args, **kwargs)

    def do_GET(self):
        """Handle OAuth callback"""
        try:
            # Parse query parameters
            from urllib.parse import urlparse, parse_qs
            query = parse_qs(urlparse(self.path).query)
            
            # Verify state to prevent CSRF
            if query.get('state', [''])[0] != self.state:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Invalid state parameter")
                return

            # Exchange code for token
            code = query.get('code', [''])[0]
            if not code:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"No code provided")
                return

            # Exchange code for token
            self.xero_client.exchange_code(code)

            # Return success page
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(self.success_template.encode())

        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode())


class AuthServer:
    def __init__(self, xero_client):
        self.xero_client = xero_client
        self.state = secrets.token_urlsafe(32)
        self.current_port = 8000
        self.server = None

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

    def get_auth_url(self, port: int = 8000) -> str:
        """Get Xero OAuth authorization URL"""
        params = {
            "response_type": "code",
            "client_id": self.xero_client.auth_config.client_id,
            "redirect_uri": self.get_redirect_uri(port),
            "scope": " ".join(self.xero_client.auth_config.scope),
            "state": self.state,
        }
        return f"https://login.xero.com/identity/connect/authorize?{urlencode(params)}"

    def start(self, port: int = 8000, max_retries: int = 3) -> int:
        """Start local auth server with retry logic"""
        for retry in range(max_retries):
            try:
                self.current_port = port + retry
                handler = lambda *args: AuthCallbackHandler(self.xero_client, self.state, self.success_template, *args)
                self.server = HTTPServer(('localhost', self.current_port), handler)
                return self.current_port
            except OSError as e:
                if e.errno == 48 and retry < max_retries - 1:  # Address in use
                    continue
                raise  # Re-raise if we're out of retries or different error

    def cleanup(self) -> None:
        """Cleanup server resources"""
        if self.server:
            self.server.server_close()

    def get_redirect_uri(self, port: int = 8000) -> str:
        """Get redirect URI for auth flow"""
        return f"http://localhost:{port}/callback"

    @contextmanager
    def setup_server(self, port: int = 8000):
        """Setup server and cleanup when exiting context"""
        try:
            self.current_port = port
            port = self.start(port)
            yield self
        finally:
            self.cleanup()

    def wait_until_auth_complete(self):
        """Wait until authentication is complete"""
        if self.server:
            self.server.handle_request()  # Handle one request and return


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

    def ensure_client(self) -> ApiClient:
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

    def get_tenant_id(self) -> str:
        """Get the tenant ID for the authenticated organization"""
        if not self._tenant_id:
            api_client = self.ensure_client()
            identity_api = IdentityApi(api_client)
            connections = identity_api.get_connections()
            for connection in connections:
                if connection.tenant_type == "ORGANISATION":
                    self._tenant_id = connection.tenant_id
                    break
        return self._tenant_id

    def start_auth_flow(self, port: int = 8000) -> bool:
        """Start complete OAuth flow with local server"""
        self.ensure_auth_config()

        with self.auth_server.setup_server(port=8000) as server:
            try:
                # Open browser with actual port
                auth_url = self.auth_server.get_auth_url(server.current_port)
                webbrowser.open(auth_url)

                # Wait for callback
                server.wait_until_auth_complete()
                return True

            except Exception as e:
                raise Exception(f"Authentication failed: {str(e)}")

    def exchange_code(self, code: str) -> XeroToken:
        """Exchange authorization code for tokens"""
        self.ensure_auth_config()

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

    def refresh_if_needed(self):
        """Refresh token if expired"""
        self.ensure_auth_config()

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

    def ensure_auth_config(self):
        """Ensure auth config is available"""
        if not self.auth_config:
            raise ValueError(
                "Xero credentials not configured. Please set XERO_CLIENT_ID and XERO_CLIENT_SECRET in .env file"
            )


# Auth tools
@mcp.tool(description="Tool to start Xero OAuth flow and automatically handle callback")
def xero_authenticate(ctx: Context) -> str:
    """Start Xero OAuth flow and automatically handle callback"""
    ctx.info("Starting Xero OAuth flow")
    # Initialize Xero client
    xero = XeroClient()
    if xero.token and xero.token.expires_at > datetime.utcnow().timestamp():
        return "Already authenticated"

    try:
        with xero.auth_server.setup_server() as server:
            # Open browser with actual port
            auth_url = xero.auth_server.get_auth_url(server.current_port)
            webbrowser.open(auth_url)
            
            # Wait for callback
            server.wait_until_auth_complete()
            return "Authentication completed successfully"
    except Exception as e:
        return f"Authentication failed: {str(e)}"


@mcp.tool(description="Tool to check current authentication status")
def xero_get_auth_status(ctx: Context) -> str:
    """Check current authentication status"""
    ctx.info("Checking Xero authentication status")
    xero = XeroClient()
    if not xero.token:
        return "Not authenticated"

    expires_in = xero.token.expires_at - datetime.utcnow().timestamp()
    if expires_in < 0:
        return "Token expired"
    return f"Authenticated (token expires in {int(expires_in)} seconds)"


def xero_call_endpoint(endpoint: str, params: dict | None = None):
    """Call a specific Xero API endpoint"""
    xero = XeroClient()
    xero.refresh_if_needed()
    api_client = xero.ensure_client()
    accounting_api = AccountingApi(api_client)
    tenant_id = xero.get_tenant_id()
    params = params or {}
    func = getattr(accounting_api, endpoint)
    if not func:
        raise ValueError(f"Endpoint {endpoint} not found")
    response = func(tenant_id, **params)
    if not response:
        raise ValueError(f"No data returned from endpoint {endpoint}")
    return response


@mcp.tool(description="Tool to retrieve accounts from Xero")
def xero_get_accounts(where: str = None) -> str:
    """Get all accounts from Xero"""
    params = {"where": where} if where else None
    response = xero_call_endpoint("get_accounts", params=params)
    return json.dumps(serialize_list(response.accounts), indent=2)


@mcp.tool(description="Tool to retrieve contacts from Xero")
def xero_get_contacts(
    where: str = None,
    page: int = None,
    search_term: str = None,
    contact_ids: str = None,
    include_archived: bool = False,
    summary_only: bool = False,
) -> str:
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

    return xero_call_endpoint("get_contacts", params=params)


@mcp.tool(description="Tool to retrieve a Balance Sheet report from Xero")
def xero_get_balance_sheet(
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

    response = xero_call_endpoint("get_report_balance_sheet", params=params)
    return json.dumps(serialize_list(response.reports), indent=2)


@mcp.tool(description="Tool to retrieve a Profit and Loss report from Xero")
def xero_get_profit_and_loss(
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

    response = xero_call_endpoint("get_report_profit_and_loss", params=params)
    return json.dumps(serialize_list(response.reports), indent=2)


@mcp.tool(description="Tool to retrieve an Aged Payables by Contact report from Xero")
def xero_get_aged_payables_by_contact(
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

    response = xero_call_endpoint("get_report_aged_payables_by_contact", params=params)
    return json.dumps(serialize_list(response.reports), indent=2)


@mcp.tool(description="Tool to retrieve an Aged Receivables by Contact report from Xero")
def xero_get_aged_receivables_by_contact(
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

    response = xero_call_endpoint("get_report_aged_receivables_by_contact", params=params)
    return json.dumps(serialize_list(response.reports), indent=2)


@mcp.tool(description="Tool to retrieve a Bank Summary report from Xero")
def xero_get_bank_summary(
    from_date: str = None,
    to_date: str = None,
) -> str:
    params = {}

    if from_date:
        params["from_date"] = from_date
    if to_date:
        params["to_date"] = to_date

    response = xero_call_endpoint("get_report_bank_summary", params=params)
    return json.dumps(serialize_list(response.reports), indent=2)


@mcp.tool(description="Tool to retrieve a Budget Summary report from Xero")
def xero_get_budget_summary(
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

    response = xero_call_endpoint("get_report_budget_summary", params=params)
    return json.dumps(serialize_list(response.reports), indent=2)


@mcp.tool(description="Tool to retrieve an Executive Summary report from Xero")
def xero_get_executive_summary(
    date: str = None,
) -> str:
    params = {}

    if date:
        params["date"] = date

    response = xero_call_endpoint("get_report_executive_summary", params=params)
    return json.dumps(serialize_list(response.reports), indent=2)


@mcp.tool(description="Tool to retrieve bank transactions from Xero")
def xero_get_bank_transactions(
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

    response = xero_call_endpoint("get_bank_transactions", params=params)
    return json.dumps(serialize_list(response.bank_transactions), indent=2)


@mcp.tool(description="Tool to retrieve payments from Xero")
def xero_get_payments(
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

    response = xero_call_endpoint("get_payments", params=params)
    return json.dumps(serialize_list(response.payments), indent=2)


@mcp.tool(description="Tool to retrieve invoices from Xero")
def xero_get_invoices(
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

    response = xero_call_endpoint("get_invoices", params=params)
    return json.dumps(serialize_list(response.invoices), indent=2)


@mcp.tool(description="Tool to retrieve configuration and debug information")
def xero_get_config_info() -> str:
    """Get configuration and debug information"""
    try:
        # Get environment variables status
        env_vars = {
            "XERO_CLIENT_ID": bool(os.getenv("XERO_CLIENT_ID")),
            "XERO_CLIENT_SECRET": bool(os.getenv("XERO_CLIENT_SECRET")),
            "CONFIG_DIR": os.getenv("CONFIG_DIR"),
        }

        # Get config directory info
        config_info = {
            "config_dir": str(CONFIG_DIR),
            "config_dir_exists": CONFIG_DIR.exists(),
            "config_dir_is_dir": CONFIG_DIR.is_dir() if CONFIG_DIR.exists() else None,
        }

        # Get token file status
        token_path = CONFIG_DIR / "token.json"
        token_info = {
            "token_file_path": str(token_path),
            "token_file_exists": token_path.exists(),
            "token_file_size": token_path.stat().st_size if token_path.exists() else None,
            "token_file_modified": datetime.fromtimestamp(token_path.stat().st_mtime).isoformat() if token_path.exists() else None,
        }

        # Get database file status
        db_path = CONFIG_DIR / "xero_analytics.db"
        db_info = {
            "db_file_path": str(db_path),
            "db_file_exists": db_path.exists(),
            "db_file_size": db_path.stat().st_size if db_path.exists() else None,
            "db_file_modified": datetime.fromtimestamp(db_path.stat().st_mtime).isoformat() if db_path.exists() else None,
        }

        # Get auth config status
        xero = XeroClient()
        auth_info = {
            "auth_config_loaded": bool(xero.auth_config),
            "token_loaded": bool(xero.token),
            "token_expired": bool(xero.token and datetime.utcnow().timestamp() >= xero.token.expires_at) if xero.token else None,
        }

        debug_info = {
            "environment_variables": env_vars,
            "config_directory": config_info,
            "token_file": token_info,
            "database_file": db_info,
            "authentication": auth_info,
            "timestamp": datetime.utcnow().isoformat(),
        }

        return json.dumps(debug_info, indent=2)
    except Exception as e:
        return json.dumps({
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }, indent=2)


# Resources for commonly accessed Xero data
@mcp.resource("xero://accounts/chart")
def get_chart_of_accounts() -> str:
    """Get the organization's chart of accounts"""
    try:
        accounts = xero_call_endpoint("get_accounts")
        return json.dumps(serialize_list(accounts.accounts), indent=2)
    except Exception as e:
        return f"Error retrieving chart of accounts: {str(e)}"


# Sample prompt for financial analysis
@mcp.prompt()
def analyze_financial_data(report_type: str, date: str) -> str:
    """Create a prompt for analyzing Xero financial data.

    Args:
        report_type: Type of report to analyze (e.g. "balance_sheet", "profit_and_loss")
        date: Report date in YYYY-MM-DD format
    """
    return f"""Please analyze this {report_type} report from {date}.
Focus on:
1. Key financial metrics and ratios
2. Notable trends or changes
3. Areas that need attention
4. Recommendations for improvement

Report data will be provided separately through the appropriate Xero API call."""


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


# Resources for commonly accessed Xero data
@mcp.resource("xero://accounts/{account_type}")
def get_accounts_by_type(account_type: str) -> str:
    """Get accounts filtered by type (e.g. BANK, REVENUE, EXPENSE, etc.)"""
    try:
        accounts = xero_call_endpoint(
            "get_accounts", params={"where": f'Type=="{account_type}"'}
        )
        return json.dumps(serialize_list(accounts.accounts), indent=2)
    except Exception as e:
        return f"Error retrieving accounts: {str(e)}"


@mcp.resource("xero://reports/current_month")
def get_current_month_reports() -> str:
    """Get key financial reports for the current month"""
    try:
        today = datetime.now()
        first_of_month = today.replace(day=1).strftime("%Y-%m-%d")
        last_of_month = today.strftime("%Y-%m-%d")

        # Get both P&L and balance sheet
        pl = xero_call_endpoint(
            "get_report_profit_and_loss",
            params={"from_date": first_of_month, "to_date": last_of_month},
        )
        bs = xero_call_endpoint(
            "get_report_balance_sheet", params={"date": last_of_month}
        )

        return json.dumps(
            {
                "profit_and_loss": serialize_list(pl.reports),
                "balance_sheet": serialize_list(bs.reports),
            },
            indent=2,
        )
    except Exception as e:
        return f"Error retrieving reports: {str(e)}"


@mcp.resource("xero://dashboard/overview")
def get_financial_overview() -> str:
    """Get a comprehensive financial overview including bank balances and key metrics"""
    try:
        # Get bank summary
        bank_summary = xero_call_endpoint("get_report_bank_summary")

        # Get executive summary
        exec_summary = xero_call_endpoint(
            "get_report_executive_summary",
            params={"date": datetime.now().strftime("%Y-%m-%d")},
        )

        return json.dumps(
            {
                "bank_summary": serialize_list(bank_summary.reports),
                "executive_summary": serialize_list(exec_summary.reports),
            },
            indent=2,
        )
    except Exception as e:
        return f"Error retrieving overview: {str(e)}"


# Enhanced prompts for financial analysis
@mcp.prompt()
def analyze_cash_flow(from_date: str, to_date: str) -> str:
    """Create a prompt for analyzing cash flow.

    Args:
        from_date: Start date in YYYY-MM-DD format
        to_date: End date in YYYY-MM-DD format
    """
    return f"""Please analyze the cash flow situation from {from_date} to {to_date}.
Focus on:
1. Operating cash flow trends
2. Major cash inflows and outflows
3. Working capital management
4. Cash flow forecasting
5. Recommendations for improving cash position

Consider:
- Bank account balances and movements
- Accounts receivable aging
- Accounts payable commitments
- Upcoming payment obligations"""


@mcp.prompt()
def review_financial_health() -> str:
    """Create a prompt for reviewing overall financial health"""
    return """Please analyze the organization's overall financial health.
Focus on:
1. Profitability Analysis
   - Gross profit margins
   - Operating margins
   - Net profit trends

2. Liquidity Assessment
   - Current ratio
   - Quick ratio
   - Working capital

3. Efficiency Metrics
   - Accounts receivable turnover
   - Accounts payable turnover
   - Inventory turnover (if applicable)

4. Growth Analysis
   - Revenue growth
   - Profit growth
   - Market share trends

5. Risk Assessment
   - Debt levels
   - Credit risk
   - Operating leverage

Please provide:
- Key strengths and weaknesses
- Comparison to industry benchmarks (if available)
- Specific recommendations for improvement
- Areas requiring immediate attention"""


@mcp.prompt()
def analyze_aged_receivables(contact_id: str = None) -> str:
    """Create a prompt for analyzing aged receivables.

    Args:
        contact_id: Optional specific contact to analyze
    """
    base_prompt = """Please analyze the aged receivables report.
Focus on:
1. Overall Collection Health
   - Total outstanding receivables
   - Age distribution of receivables
   - Collection efficiency metrics

2. Risk Assessment
   - Identify high-risk accounts
   - Analyze payment patterns
   - Flag potential bad debts

3. Action Items
   - Prioritized collection targets
   - Recommended follow-up actions
   - Suggested policy changes

4. Trends and Patterns
   - Historical collection trends
   - Seasonal patterns
   - Customer payment behaviors"""

    if contact_id:
        return (
            base_prompt + f"\n\nPlease focus specifically on contact ID: {contact_id}"
        )
    return base_prompt


@mcp.prompt()
def budget_variance_analysis(date: str) -> str:
    """Create a prompt for analyzing budget variances.

    Args:
        date: Report date in YYYY-MM-DD format
    """
    return f"""Please analyze the budget variances as of {date}.
Focus on:
1. Significant Variances
   - Major favorable and unfavorable variances
   - Root cause analysis of variances
   - Impact on overall financial performance

2. Trend Analysis
   - Recurring variance patterns
   - Seasonal factors
   - Progressive changes over time

3. Performance Assessment
   - Department/category performance
   - Cost control effectiveness
   - Revenue target achievement

4. Recommendations
   - Budget adjustment needs
   - Control improvement opportunities
   - Strategic implications

Please provide actionable insights and specific recommendations for addressing variances."""
