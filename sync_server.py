import sqlite3
from fastmcp import FastMCP, Context
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Union
from pydantic import BaseModel
import json
import os
from pathlib import Path
import webbrowser
import asyncio
from aiohttp import web
import secrets
from dotenv import load_dotenv
import appdirs
import logging
from urllib.parse import urlencode

# Import Xero SDK components
from xero_python.accounting import AccountingApi
from xero_python.identity import IdentityApi
from xero_python.api_client import ApiClient
from xero_python.api_client.configuration import Configuration
from xero_python.api_client.oauth2 import OAuth2Token
from authlib.integrations.requests_client import OAuth2Session

# Constants for OAuth2
AUTHORIZATION_URL = "https://login.xero.com/identity/connect/authorize"
TOKEN_URL = "https://identity.xero.com/connect/token"

# Load environment variables from .env file
load_dotenv()

# Setup config directory
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
        "accounting.transactions",
        "accounting.contacts.read",
        "accounting.settings"
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
            
        return cls(
            client_id=client_id,
            client_secret=client_secret
        )

class XeroToken(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: float
    token_type: str = "Bearer"
    scope: List[str] = []

class SyncConfig(BaseModel):
    days_back: int = 30
    batch_size: int = 100
    tables: List[str] = ["accounts", "contacts", "bank_transactions", "payments"]

class SyncStats(BaseModel):
    start_time: datetime
    end_time: Optional[datetime] = None
    records_processed: Dict[str, int] = {}
    errors: List[str] = []

class AuthServer:
    def __init__(self, xero_client):
        self.xero_client = xero_client
        self.app = web.Application()
        self.app.router.add_get('/callback', self.handle_callback)
        self.auth_future: Optional[asyncio.Future] = None
        self.state = secrets.token_urlsafe(32)
        
    async def handle_callback(self, request: web.Request) -> web.Response:
        """Handle OAuth callback"""
        try:
            # Verify state to prevent CSRF
            if request.query.get('state') != self.state:
                return web.Response(text="Invalid state parameter", status=400)
                
            # Exchange code for token
            code = request.query.get('code')
            if not code:
                return web.Response(text="No code provided", status=400)
                
            await self.xero_client.exchange_code(code)
            
            # Set result and close browser window
            html = """
                <html>
                    <body>
                        <h1>Authentication Successful!</h1>
                        <p>You can close this window now.</p>
                        <script>window.close()</script>
                    </body>
                </html>
            """
            self.auth_future.set_result(True)
            return web.Response(text=html, content_type='text/html')
            
        except Exception as e:
            self.auth_future.set_exception(e)
            return web.Response(text=str(e), status=500)
    
    async def start(self, port: int = 8000) -> None:
        """Start local auth server"""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, 'localhost', port)
        await site.start()
        
    def get_redirect_uri(self, port: int = 8000) -> str:
        """Get redirect URI for auth flow"""
        return f"http://localhost:{port}/callback"

mcp = FastMCP(
    "Xero Sync",
    dependencies=[
        "aiohttp",
        "xero-python",
        "python-dotenv",
        "pydantic",
        "appdirs",
        "authlib",
        "requests"
    ]
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
                    client_secret=self.auth_config.client_secret
                )
            )
            self._api_client = ApiClient(config)
            
            # Set up token management
            @self._api_client.oauth2_token_getter
            def obtain_xero_oauth2_token():
                if not self.token:
                    return None
                return {
                    "access_token": self.token.access_token,
                    "refresh_token": self.token.refresh_token,
                    "expires_in": int(self.token.expires_at - datetime.utcnow().timestamp()),
                    "token_type": self.token.token_type,
                    "scope": self.token.scope
                }

            @self._api_client.oauth2_token_saver
            def store_xero_oauth2_token(token):
                # Update the token when refreshed
                self.token = XeroToken(
                    access_token=token["access_token"],
                    refresh_token=token["refresh_token"],
                    expires_at=datetime.utcnow().timestamp() + token["expires_in"],
                    token_type=token["token_type"],
                    scope=token.get("scope", "").split() if isinstance(token.get("scope"), str) else []
                )

        # Ensure we have a valid token
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
            "state": self.auth_server.state
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
        
        # Wait for callback
        try:
            await self.auth_server.auth_future
            return True
        except Exception as e:
            raise Exception(f"Authentication failed: {str(e)}")

    async def exchange_code(self, code: str) -> XeroToken:
        """Exchange authorization code for tokens"""
        await self.ensure_auth_config()
        
        # Create OAuth2 session for token exchange
        client = OAuth2Session(
            self.auth_config.client_id,
            self.auth_config.client_secret,
            scope=" ".join(self.auth_config.scope),
            redirect_uri=self.auth_server.get_redirect_uri()
        )
        
        # Exchange the code for tokens
        token = client.fetch_token(
            TOKEN_URL,
            code=code,
            grant_type="authorization_code"
        )
        
        # Convert to our token model
        xero_token = XeroToken(
            access_token=token["access_token"],
            refresh_token=token["refresh_token"],
            expires_at=datetime.utcnow().timestamp() + token["expires_in"],
            token_type=token["token_type"],
            scope=token.get("scope", "").split() if isinstance(token.get("scope"), str) else []
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
                scope=" ".join(self.auth_config.scope)
            )
            
            # Refresh the token
            token = client.refresh_token(
                TOKEN_URL,
                refresh_token=self.token.refresh_token
            )
            
            # Convert to our token model
            self.token = XeroToken(
                access_token=token["access_token"],
                refresh_token=token["refresh_token"],
                expires_at=datetime.utcnow().timestamp() + token["expires_in"],
                token_type=token["token_type"],
                scope=token.get("scope", "").split() if isinstance(token.get("scope"), str) else []
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
@mcp.tool()
async def xero_authenticate() -> str:
    """Start Xero OAuth flow and automatically handle callback"""
    if xero.token and xero.token.expires_at > datetime.utcnow().timestamp():
        return "Already authenticated"

    try:
        await xero.start_auth_flow()
        return "Authentication completed successfully"
    except Exception as e:
        return f"Authentication failed: {str(e)}"

@mcp.tool()
def xero_get_auth_status() -> str:
    """Check current authentication status"""
    if not xero.token:
        return "Not authenticated"
        
    expires_in = xero.token.expires_at - datetime.utcnow().timestamp()
    if expires_in < 0:
        return "Token expired"
    return f"Authenticated (token expires in {int(expires_in)} seconds)"

@mcp.tool()
async def xero_call_endpoint(endpoint: str, params: dict = {}) -> str:
    """Call a specific Xero API endpoint to interact with Xero's accounting data. Common endpoints include get_accounts, get_contacts, get_bank_transactions, get_payments, etc. To see all available endpoints, use xero_get_existing_endpoints(). If you need details about a specific endpoint's parameters, return types and field definitions, call xero_get_endpoint_docs() with the endpoint name. Each endpoint may require different parameters - if you're unsure about what parameters are needed, check the endpoint documentation first."""
    api_client = await xero.ensure_client()
    accounting_api = AccountingApi(api_client)
    tenant_id = await xero.get_tenant_id()
    func = getattr(accounting_api, endpoint)
    if not func:
        return f"Endpoint {endpoint} not found"
    response = func(tenant_id, **params)
    if not response:
        return f"No data returned from endpoint {endpoint}"
    objects = getattr(response, endpoint.replace("get_", ""))
    return objects

def _get_endpoint_details(func, model_finder):
    doc = func.__doc__
    return_type_list = return_type = func.__doc__.split(":return: ")[1].strip()
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

@mcp.tool()
async def xero_get_existing_endpoints() -> str:
    """List existing Xero API endpoints with their return types and fields"""
    api_client = await xero.ensure_client()
    accounting_api = AccountingApi(api_client)
    
    # Get all get_ methods
    endpoints = [name for name in dir(accounting_api) if name.startswith("get_")]
    model_finder = accounting_api.get_model_finder()
    result = []
    for endpoint in endpoints:
        func = getattr(accounting_api, endpoint)
        doc, return_type, field_info = _get_endpoint_details(func, model_finder)
        result.append(f"{endpoint} -> {return_type}{field_info}")

    return "\n".join(result)

@mcp.tool()
async def xero_get_endpoint_docs(endpoint: str) -> str:
    """Provide documentation for a specific Xero API endpoint"""
    api_client = await xero.ensure_client()
    accounting_api = AccountingApi(api_client)
    func = getattr(accounting_api, endpoint)
    model_finder = accounting_api.get_model_finder()
    doc, return_type, field_info = _get_endpoint_details(func, model_finder)
    return f"Function: {endpoint}\nReturn Type: {return_type}\n{field_info}\n\nDocs:\n{doc}"

@mcp.tool()
async def xero_get_model_fields(model: str) -> str:
    """Provide fields for a specific Xero API model"""
    api_client = await xero.ensure_client()
    accounting_api = AccountingApi(api_client)
    model_finder = accounting_api.get_model_finder()
    model_class = model_finder.find_model(model)
    return model_class.openapi_types


# # Core sync tools
# @mcp.tool()
# async def xero_data_sync(days_back: int = 30, ctx: Context = None) -> str:
#     """Sync recent Xero data to local SQLite database with progress tracking"""
#     if not xero.token:
#         return "Please authenticate with Xero first using get_auth_url()"
        
#     stats = SyncStats(start_time=datetime.utcnow())
    
#     try:
#         # Initialize database
#         conn = get_db_connection()
#         ensure_tables_exist(conn)
        
#         # Get tenant ID
#         tenant_id = await xero.get_tenant_id()
        
#         # Sync core data types using optimal patterns
#         await sync_accounts(conn, tenant_id, ctx, stats)
#         await sync_contacts(conn, tenant_id, ctx, stats) 
#         await sync_bank_transactions(conn, tenant_id, days_back, ctx, stats)
#         await sync_payments(conn, tenant_id, days_back, ctx, stats)
        
#         stats.end_time = datetime.utcnow()
#         save_sync_stats(stats)
        
#         return f"Sync completed successfully in {(stats.end_time - stats.start_time).seconds} seconds"
        
#     except Exception as e:
#         stats.errors.append(str(e))
#         stats.end_time = datetime.utcnow()
#         save_sync_stats(stats)
#         raise

# @mcp.resource("xero://data/schema")
# def xero_data_schema() -> str:
#     """Provide the Xero data schema as context"""
#     conn = get_db_connection()
#     schema = conn.execute(
#         "SELECT sql FROM sqlite_master WHERE type='table'"
#     ).fetchall()
#     return "\n".join(sql[0] for sql in schema if sql[0])

# @mcp.tool()
# def xero_data_query(query: str) -> str:
#     """Query Xero data using SQL"""
#     conn = get_db_connection()
#     cur = conn.cursor()
#     cur.execute(query)
#     return cur.fetchall()


async def sync_accounts(conn: sqlite3.Connection, tenant_id: str, ctx: Context, stats: SyncStats):
    """Sync accounts using SDK"""
    if ctx:
        ctx.info("Syncing accounts...")
    
    api_client = await xero.ensure_client()
    accounting_api = AccountingApi(api_client)
    
    # Get accounts from Xero API
    accounts = accounting_api.get_accounts(tenant_id)
    
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY,
            code TEXT,
            name TEXT,
            type TEXT,
            status TEXT,
            updated_at TEXT
        )
    """)
    
    for account in accounts.accounts:
        cur.execute("""
            INSERT OR REPLACE INTO accounts 
            (id, code, name, type, status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            str(account.account_id),
            str(account.code) if account.code else None,
            str(account.name),
            str(account.type) if account.type else None,  # Convert enum to string
            str(account.status) if account.status else None,  # Convert enum to string
            datetime.utcnow().isoformat()
        ))
    
    conn.commit()
    stats.records_processed["accounts"] = len(accounts.accounts)

async def sync_contacts(conn: sqlite3.Connection, tenant_id: str, ctx: Context, stats: SyncStats):
    """Sync contacts using SDK with pagination"""
    if ctx:
        ctx.info("Syncing contacts...")
    
    api_client = await xero.ensure_client()
    accounting_api = AccountingApi(api_client)
    
    page = 1
    total_synced = 0
    
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id TEXT PRIMARY KEY,
            name TEXT,
            first_name TEXT,
            last_name TEXT,
            email TEXT,
            updated_at TEXT
        )
    """)
    
    while True:
        print(f"Syncing contacts page {page}")
        contacts = accounting_api.get_contacts(
            tenant_id,
            page=page,
            page_size=100,
            order="Name ASC"
        )
        print(f"Pagination: {contacts.pagination}")
        
        if not contacts.contacts:
            break
            
        for contact in contacts.contacts:
            cur.execute("""
                INSERT OR REPLACE INTO contacts 
                (id, name, first_name, last_name, email, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                str(contact.contact_id),
                str(contact.name),
                str(contact.first_name) if contact.first_name else None,
                str(contact.last_name) if contact.last_name else None,
                str(contact.email_address) if contact.email_address else None,
                datetime.utcnow().isoformat()
            ))
        
        conn.commit()
        total_synced += len(contacts.contacts)
        
        if ctx:
            await ctx.report_progress(total_synced, total_synced + 100)
            
        page += 1
    
    stats.records_processed["contacts"] = total_synced

async def sync_bank_transactions(
    conn: sqlite3.Connection,
    tenant_id: str,
    days_back: int,
    ctx: Context,
    stats: SyncStats
):
    """Sync bank transactions using SDK with date filtering"""
    if ctx:
        ctx.info("Syncing bank transactions...")
    
    api_client = await xero.ensure_client()
    accounting_api = AccountingApi(api_client)
    
    start_date = datetime.utcnow() - timedelta(days=days_back)
    page = 1
    total_synced = 0
    
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bank_transactions (
            id TEXT PRIMARY KEY,
            type TEXT,
            amount REAL,
            date TEXT,
            reference TEXT,
            status TEXT,
            updated_at TEXT
        )
    """)
    
    while True:
        transactions = accounting_api.get_bank_transactions(
            tenant_id,
            page=page,
            page_size=100,
            # where=f"Date >= DateTime({start_date.year}, {start_date.month}, {start_date.day})"
        )
        
        if not transactions.bank_transactions:
            break
            
        for txn in transactions.bank_transactions:
            cur.execute("""
                INSERT OR REPLACE INTO bank_transactions 
                (id, type, amount, date, reference, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                str(txn.bank_transaction_id),
                str(txn.type) if txn.type else None,  # Convert enum to string
                float(txn.total) if txn.total else 0.0,  # Convert to float
                str(txn.date) if txn.date else None,
                str(txn.reference) if txn.reference else None,
                str(txn.status) if txn.status else None,  # Convert enum to string
                datetime.utcnow().isoformat()
            ))
        
        conn.commit()
        total_synced += len(transactions.bank_transactions)
        
        if ctx:
            await ctx.report_progress(total_synced, total_synced + 100)
            
        page += 1
    
    stats.records_processed["bank_transactions"] = total_synced

async def sync_payments(
    conn: sqlite3.Connection,
    tenant_id: str,
    days_back: int,
    ctx: Context,
    stats: SyncStats
):
    """Sync payments using SDK with date filtering"""
    if ctx:
        ctx.info("Syncing payments...")
    
    api_client = await xero.ensure_client()
    accounting_api = AccountingApi(api_client)
    
    start_date = datetime.utcnow() - timedelta(days=days_back)
    page = 1
    total_synced = 0
    
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id TEXT PRIMARY KEY,
            amount REAL,
            date TEXT,
            reference TEXT,
            status TEXT,
            payment_type TEXT,
            updated_at TEXT
        )
    """)
    
    while True:
        payments = accounting_api.get_payments(
            tenant_id,
            page=page,
            page_size=100,
            # where=f"Date >= DateTime({start_date.year}, {start_date.month}, {start_date.day})"
        )
        
        if not payments.payments:
            break
            
        for payment in payments.payments:
            cur.execute("""
                INSERT OR REPLACE INTO payments 
                (id, amount, date, reference, status, payment_type, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                str(payment.payment_id),
                float(payment.amount) if payment.amount else 0.0,  # Convert to float
                str(payment.date) if payment.date else None,
                str(payment.reference) if payment.reference else None,
                str(payment.status) if payment.status else None,  # Convert enum to string
                str(payment.payment_type) if payment.payment_type else None,  # Convert enum to string
                datetime.utcnow().isoformat()
            ))
        
        conn.commit()
        total_synced += len(payments.payments)
        
        if ctx:
            await ctx.report_progress(total_synced, total_synced + 100)
            
        page += 1
    
    stats.records_processed["payments"] = total_synced

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
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sync_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time TEXT,
            end_time TEXT,
            records_processed TEXT,
            errors TEXT
        )
    """)
    conn.commit()

def save_sync_stats(stats: SyncStats):
    """Save sync statistics to database"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO sync_stats 
        (start_time, end_time, records_processed, errors)
        VALUES (?, ?, ?, ?)
    """, (
        stats.start_time.isoformat(),
        stats.end_time.isoformat() if stats.end_time else None,
        str(stats.records_processed),
        str(stats.errors)
    ))
    conn.commit()

@mcp.resource("sync://status")
def get_sync_status() -> dict:
    """Get current sync status and statistics"""
    conn = get_db_connection()
    cur = conn.cursor()
    last_sync = cur.execute("""
        SELECT * FROM sync_stats 
        ORDER BY id DESC LIMIT 1
    """).fetchone()
    
    if not last_sync:
        return {
            "last_sync": None,
            "records_synced": {},
            "next_scheduled": None
        }
        
    return {
        "last_sync": last_sync["end_time"],
        "records_synced": eval(last_sync["records_processed"]),
        "errors": eval(last_sync["errors"]),
        "next_scheduled": (
            datetime.fromisoformat(last_sync["end_time"]) + 
            timedelta(hours=1)
        ).isoformat() if last_sync["end_time"] else None
    } 