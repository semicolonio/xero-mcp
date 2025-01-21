from xero_python.accounting import AccountingApi
from xero_python.identity import IdentityApi
from xero_python.api_client import ApiClient
from xero_python.api_client.configuration import Configuration
from xero_python.api_client.oauth2 import OAuth2Token
from authlib.integrations.requests_client import OAuth2Session
from xero_python.accounting.models.contacts import Contacts
from xero_python.accounting.models.accounts import Accounts
from xero_python.accounting.models.bank_transactions import BankTransactions
from db_operations import XeroDatabase

import webbrowser
import json
import os

# Your Xero app credentials
CLIENT_ID = "E3B81C746D304D14A6D50159E021CCF1"
CLIENT_SECRET = "9-ZdynhOVXz4k_Ij6D86TwL94YOWAflahtapuJxcCSkBq2ME"
SCOPE = "offline_access openid profile email accounting.transactions accounting.contacts.read"

# Xero OAuth2 URLs
AUTHORIZATION_URL = "https://login.xero.com/identity/connect/authorize"
TOKEN_URL = "https://identity.xero.com/connect/token"

if not os.path.exists("token.json"):
    print("Token does not exist")
    # Create OAuth2 session
    client = OAuth2Session(
        CLIENT_ID,
        CLIENT_SECRET,
        scope=SCOPE,
        redirect_uri="http://localhost:9000/callback"
    )

    # Get authorization URL
    auth_url, state = client.create_authorization_url(AUTHORIZATION_URL)

    # Open browser for authentication
    print(f"Please visit this URL to authorize the application: {auth_url}")
    webbrowser.open(auth_url)

    # Get the authorization response URL from user input
    authorization_response = input("Enter the full callback URL: ")

    # Fetch token
    token = client.fetch_token(
        TOKEN_URL,
        authorization_response=authorization_response,
        grant_type="authorization_code"
    )

    # Save token to file (optional)
    with open("token.json", "w") as f:
        json.dump(token, f)
else:
    print("Token already exists")
    # read token from file
    


# Create API client
api_client = ApiClient(
    Configuration(
        debug=False,
        oauth2_token=OAuth2Token(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET
        ),
    ),
    pool_threads=1,
)

@api_client.oauth2_token_getter
def obtain_xero_oauth2_token():
    with open("token.json", "r") as f:
        token = json.load(f)
    return token

@api_client.oauth2_token_saver
def store_xero_oauth2_token(token):
    pass


def get_tenant_id():
    identity_api = IdentityApi(api_client)
    for connection in identity_api.get_connections():
        if connection.tenant_type == "ORGANISATION":
            return connection.tenant_id

def get_contacts(tenant_id) -> Contacts:
    accounting_api = AccountingApi(api_client)
    contacts = accounting_api.get_contacts(tenant_id)
    return contacts

def get_accounts(tenant_id) -> Accounts:
    accounting_api = AccountingApi(api_client)
    accounts = accounting_api.get_accounts(tenant_id)
    return accounts

def get_transactions(tenant_id) -> BankTransactions:
    accounting_api = AccountingApi(api_client)
    transactions = accounting_api.get_bank_transactions(tenant_id)
    return transactions


# Make API calls and store in database
tenant_id = get_tenant_id()
accounts = get_accounts(tenant_id)
contacts = get_contacts(tenant_id)
transactions = get_transactions(tenant_id)

# Initialize database and store the data
db = XeroDatabase()
db.store_accounts(accounts)
db.store_contacts(contacts)
db.store_transactions(transactions)
