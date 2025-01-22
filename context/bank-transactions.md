# Bank Transactions

[Try in API Explorer](https://api-explorer.xero.com/accounting/banktransactions)

## Overview

This endpoint includes spend and receive money transactions, overpayments and prepayments. This endpoint does not allow access to any bank statements or direct bank feeds.

|  |  |
| --- | --- |
| URL | [https://api.xero.com/api.xro/2.0/BankTransactions](https://api.xero.com/api.xro/2.0/BankTransactions) |
| Methods Supported | [GET](https://developer.xero.com/documentation/api/accounting/banktransactions#get-banktransactions), [PUT](https://developer.xero.com/documentation/api/accounting/banktransactions#put-banktransactions), [POST](https://developer.xero.com/documentation/api/accounting/banktransactions#post-banktransactions) |
| Description | Allows you to retrieve any spend or receive money transactions <br>Allows you to create or update spend or receive money transactions <br>Allows you to create a receive or spend overpayment <br>Allows you to create a receive or spend prepayment <br>Allows you to attach files to spend or receive money transactions <br>Allows you to retrieve history <br>Allows you to add notes |

## GET BankTransactions

[anchor for get banktransactions](https://developer.xero.com/documentation/api/accounting/banktransactions#get-banktransactions)

Use this method to retrieve one or many bank transactions.

This endpoint does not return payments applied to invoices, expense claims or transfers between bank accounts.

The following elements are returned in the BankTransactions response

|  |  |
| --- | --- |
| Type | See [Bank Transaction Types](https://developer.xero.com/documentation/api/accounting/types#bank-transactions) |
| Contact | See [Contacts](https://developer.xero.com/documentation/api/accounting/contacts) |
| Lineitems | See LineItems below. The LineItems element can contain any number of individual LineItem sub-elements. |
| BankAccount | Bank account for transaction. See BankAccount below |
| BatchPayment | Present if the transaction is part of a batch. See [Batch Payments](https://developer.xero.com/documentation/api/accounting/batchpayments) for more details. |
| IsReconciled | Boolean to show if transaction is reconciled |
| Date | Date of transaction – YYYY-MM-DD |
| Reference | Reference for the transaction. Only supported for SPEND and RECEIVE transactions. |
| CurrencyCode | The currency that bank transaction has been raised in (see [Currencies](https://developer.xero.com/documentation/api/accounting/currencies)). Setting currency is only supported on overpayments. |
| CurrencyRate | Exchange rate to base currency when money is spent or received. e.g. 0.7500 Only used for bank transactions in non base currency. Setting currency is only supported on overpayments. |
| Url | URL link to a source document – shown as "Go to App Name" |
| Status | See [Bank Transaction Status Codes](https://developer.xero.com/documentation/api/accounting/types#bank-transactions) |
| LineAmountTypes | See [Line Amount Types](https://developer.xero.com/documentation/api/accounting/types#invoices) |
| SubTotal | Total of bank transaction excluding taxes |
| TotalTax | Total tax on bank transaction |
| Total | Total of bank transaction tax inclusive |
| BankTransactionID | Xero generated identifier for bank transaction (unique within organisations) |
| PrepaymentID | Xero generated identifier for a [Prepayment](https://developer.xero.com/documentation/api/accounting/prepayments) (unique within organisations). This will be returned on BankTransactions with a Type of SPEND-PREPAYMENT or RECEIVE-PREPAYMENT |
| OverpaymentID | Xero generated identifier for an [Overpayment](https://developer.xero.com/documentation/api/accounting/overpayments) (unique within organisations). This will be returned on BankTransactions with a Type of SPEND-OVERPAYMENT or RECEIVE-OVERPAYMENT |
| UpdatedDateUTC | Last modified date UTC format |
| HasAttachments | Boolean to indicate if a bank transaction has an attachment |

Elements for Line Items

|  |  |
| --- | --- |
| Description | The description of the line item |
| Quantity | LineItem Quantity |
| UnitAmount | Lineitem unit amount. By default, unit amount will be rounded to two decimal places. You can opt in to use four decimal places by adding the querystring parameter unitdp=4 to your query. See the [Rounding in Xero](https://developer.xero.com/documentation/guides/how-to-guides/rounding-in-xero#unit-prices) guide for more information. |
| AccountCode | See [Accounts](https://developer.xero.com/documentation/api/accounting/accounts) |
| ItemCode | ItemCode can only be present when the Bank Transaction Type is SPEND or RECEIVE. |
| LineItemID | The Xero generated identifier for a LineItem. |
| TaxType | Used as an override if the default Tax Code for the selected AccountCode is not correct – see [TaxTypes](https://developer.xero.com/documentation/api/accounting/types#tax-rates). |
| TaxAmount | The tax amount is automatically calculated as a percentage of the line amount (see below) based on the tax rate. This value must match the auto calculated value. |
| LineAmount | The total of the line including discount |
| Tracking | Optional Tracking Category – see [Tracking](https://developer.xero.com/documentation/api/accounting/trackingcategories). Any LineItem can have a maximum of 2 TrackingCategory elements. |

Elements for Bank Account

|  |  |
| --- | --- |
| Code | BankAccount code (this value may not always be present for a bank account) |
| AccountID | BankAccount identifier |

### Optional parameters

|  |  |
| --- | --- |
| **Record filter** | You can specify an individual record by appending the BankTransactionID to the endpoint, i.e. **GET [https://.../BankTransactions/297c2dc5-cc47-4afd-8ec8-74990b8761e9](https://.../BankTransactions/297c2dc5-cc47-4afd-8ec8-74990b8761e9)** |
| Modified After | The ModifiedAfter filter is actually an HTTP header: ' **If-Modified-Since**'. A UTC timestamp (yyyy-mm-ddThh:mm:ss) . Only bank transactions created or modified since this timestamp will be returned e.g. 2009-11-12T00:00:00 |
| Where | Filter by an any element ( _see [Filters](https://developer.xero.com/documentation/api/accounting/requests-and-responses#http-get)_ ). We recommend you limit filtering to the [optimised elements](https://developer.xero.com/documentation/api/accounting/banktransactions#optimised-use-of-the-where-filter) only. |
| order | Order by any element returned ( _see [Order By](https://developer.xero.com/documentation/api/accounting/requests-and-responses#http-get)_ ) |
| page | Up to 100 bank transactions will be returned per call, with line items shown for each transaction, when the page parameter is used e.g. page=1 |

### High volume threshold limit

In order to make our platform more stable, we've added a high volume threshold limit for the GET Bank Transactions Endpoint.

- Requests that have more than 100k bank transactions being returned in the response will be denied and receive a 400 response code
- Requests using unoptimised fields for filtering or ordering that result in more than 100k bank transactions will be denied with a 400 response code

Please continue reading to find out how you can use paging and optimise your filtering to ensure your requests are always successful. Be sure to check out the [Efficient Data Retrieval](https://developer.xero.com/documentation/api/efficient-data-retrieval) page for tips on query optimisation.

### Optimised use of the where filter

The most common filters have been optimised to ensure performance across organisations of all sizes. We recommend you restrict your filtering to the following optimised parameters.

#### Range Operators in Where clauses

Indicated fields also support the range operators: greater than, greater than or equals, less than, less than or equals (>, >=, <, <=).

Range operators can be combined with the AND operator to query a date range. eg where=Date>=DateTime(2020, 01, 01) AND Date<DateTime(2020, 02, 01)

_When using individually or combined with the AND operator:_

| Field | Operator | Query |
| --- | --- | --- |
| Type | equals | where=Type="RECEIVE" |
| Status | equals | where=Status="AUTHORISED" |
| Date | equals, range | where=Date=DateTime(2020, 01, 01)<br>where=Date>DateTime(2020, 01, 01) |
| Contact.ContactID | equals | where=Contact.ContactID=guid("96988e67-ecf9-466d-bfbf-0afa1725a649") |

**Example:** Retrieve all SPEND BankTransactions on the 1st of January, 2020

```json
?where=Type=="SPEND" AND Date=DateTime(2020, 01, 01)
```

copy code

This would translate to the following URL once encoded.

```json
https://api.xero.com/api.xro/2.0/banktransactions?where=Type%3d%3d%22SPEND%22+AND+Date%3DDateTime%282020%2C+01%2C+01%29%0D%0A
```

copy code

#### Paging BankTransactions (recommended)

By using paging all the line item details for each bank transaction are returned which may avoid the need to retrieve each individual bank transaction.

More information about [retrieving paged resources](https://developer.xero.com/documentation/api/accounting/requests-and-responses#retrieving-paged-resources).

#### Optimised ordering:

The following parameters are optimised for ordering:

- BankTransactionID
- UpdatedDateUTC
- Date

The default order is _UpdatedDateUTC ASC, BankTransactionID ASC_. Secondary ordering is applied by default using the BankTransactionID. This ensures consistency across pages.

Example response when retrieving a single BankTransaction

```json
GET https://api.xero.com/api.xro/2.0/BankTransactions/d20b6c54-7f5d-4ce6-ab83-55f609719126

```

copy code

```json
{
  "BankTransactions": [{\
    "Contact": {\
      "ContactID": "6d42f03b-181f-43e3-93fb-2025c012de92",\
      "Name": "Wilson Periodicals"\
    },\
    "DateString": "2014-05-26T00:00:00",\
    "Date": "\/Date(1401062400000+0000)\/",\
    "Status": "AUTHORISED",\
    "LineAmountTypes": "Inclusive",\
    "LineItems": [{\
      "Description": "Monthly account fee",\
      "UnitAmount": "49.90",\
      "TaxType": "NONE",\
      "TaxAmount": "0.00",\
      "LineAmount": "49.90",\
      "AccountCode": "404",\
      "Quantity": "1.0000",\
      "LineItemID": "52208ff9-528a-4985-a9ad-b2b1d4210e38"\
    }],\
    "SubTotal": "49.90",\
    "TotalTax": "0.00",\
    "Total": "49.90",\
    "UpdatedDateUTC": "\/Date(1439434356790+0000)\/",\
    "CurrencyCode": "NZD",\
    "BankTransactionID": "d20b6c54-7f5d-4ce6-ab83-55f609719126",\
    "BankAccount": {\
      "AccountID": "ac993f75-035b-433c-82e0-7b7a2d40802c",\
      "Code": "090",\
      "Name": "Business Bank Account"\
    },\
    "BatchPayment": {\
      "Account": {\
        "AccountID": "ac993f75-035b-433c-82e0-7b7a2d40802c"\
      },\
      "BatchPaymentID": "b54aa50c-794c-461b-89d1-846e1b84d9c0",\
      "Date": "\/Date(1401062400000+0000)\/",\
      "Type": "RECBATCH",\
      "Status": "AUTHORISED",\
      "TotalAmount": "100.00",\
      "UpdatedDateUTC": "\/Date(1439434356790+0000)\/",\
      "IsReconciled": "true"\
    },\
    "Type": "SPEND",\
    "Reference": "Sub 098801",\
    "IsReconciled": "true"\
  }]
}

```

copy code

Example response when retrieving a collection of BankTransactions

```json
GET https://api.xero.com/api.xro/2.0/BankTransactions

```

copy code

```json
{
  "BankTransactions": [{\
    "Contact": {\
      "ContactID": "c09661a2-a954-4e34-98df-f8b6d1dc9b19",\
      "Name": "BNZ"\
    },\
    "DateString": "2014-05-26T00:00:00",\
    "Date": "\/Date(1401062400000+0000)\/",\
    "LineAmountTypes": "Inclusive",\
    "SubTotal": "15.00",\
    "TotalTax": "0.00",\
    "Total": "15.00",\
    "UpdatedDateUTC": "\/Date(1519250319570+0000)\/",\
    "FullyPaidOnDate": "\/Date(1439434356790+0000)\/",\
    "BankTransactionID": "d20b6c54-7f5d-4ce6-ab83-55f609719126",\
    "BankAccount": {\
      "AccountID": "297c2dc5-cc47-4afd-8ec8-74990b8761e9",\
      "Code": "BANK"\
    },\
    "Type": "SPEND",\
    "IsReconciled": "true"\
  },{\
    ...\
  }]
}

```

copy code

## POST BankTransactions

[anchor for post banktransactions](https://developer.xero.com/documentation/api/accounting/banktransactions#post-banktransactions)

Use this method to create spend money, receive money, spend prepayment, receive prepayment, spend overpayment or receive overpayment transactions.

It can also be used to update spend money and receive money transactions. Updates on spend prepayment, receive prepayment, spend overpayment or receive overpayment transactions are NOT currently supported.

Note – you cannot create transfers using PUT/POST BankTransactions. To create a bank transfer you need to use the [BankTransfers](https://developer.xero.com/documentation/api/accounting/banktransfers) endpoint.

_The following are **mandatory** for a PUT / POST request_

|  |  |
| --- | --- |
| Type | See [Bank Transaction Types](https://developer.xero.com/documentation/api/accounting/types#bank-transactions) |
| Contact | See [Contacts](https://developer.xero.com/documentation/api/accounting/contacts) |
| Lineitems | See LineItems. The LineItems element can contain any number of individual LineItem sub-elements. At least _**one**_ is required to create a bank transaction. |
| BankAccount | Bank account for transaction. See BankAccount. Only accounts of [Type BANK](https://developer.xero.com/documentation/api/accounting/types#accounts) will be accepted. |

_The following are **optional** for a PUT / POST request_

|  |  |
| --- | --- |
| IsReconciled | Boolean to show if transaction is reconciled. Conversion related apps can set the IsReconciled flag in scenarios when a matching bank statement line is not available. [Learn more](http://help.xero.com/#Q_BankRecNoImport) |
| Date | Date of transaction – YYYY-MM-DD |
| Reference | Reference for the transaction. Only supported for SPEND and RECEIVE transactions. |
| CurrencyCode | The currency that bank transaction has been raised in (see [Currencies](https://developer.xero.com/documentation/api/accounting/currencies)). Setting currency is only supported on overpayments. |
| CurrencyRate | Exchange rate to base currency when money is spent or received. e.g. 0.7500 Only used for bank transactions in non base currency. If this isn't specified for non base currency accounts then either the user-defined rate (preference) or the [XE.com day rate](http://help.xero.com/#CurrencySettings$Rates) will be used. Setting currency is only supported on overpayments. |
| Url | URL link to a source document – shown as "Go to App Name" |
| Status | See [Bank Transaction Status Codes](https://developer.xero.com/documentation/api/accounting/types#bank-transactions) |
| LineAmountTypes | Line amounts are inclusive of tax by default if you don't specify this element. See [Line Amount Types](https://developer.xero.com/documentation/api/accounting/types#invoices) |

Elements for Line Items

|  |  |
| --- | --- |
| Description | Description needs to be at least 1 char long. |
| Quantity | Quantity must be > 0 |
| UnitAmount | Lineitem unit amount must not equal 0. Line item amounts may be negative, but the total value for the document must be positive. By default, unit amount will be rounded to two decimal places. You can opt in to use four decimal places by adding the querystring parameter unitdp=4 to your query. See the [Rounding in Xero](https://developer.xero.com/documentation/guides/how-to-guides/rounding-in-xero#unit-prices) guide for more information. |
| AccountCode | AccountCode must be active for the organisation. See [Accounts](https://developer.xero.com/documentation/api/accounting/accounts) |
| ItemCode | ItemCode can only be used when the Bank Transaction Type is SPEND or RECEIVE. If Description, UnitAmount or AccountCode are not specified, then the defaults from the [Item](https://developer.xero.com/documentation/api/accounting/items) will be applied. |
| LineItemID | The Xero generated identifier for a LineItem. If LineItemIDs are not included with line items in an update request then the line items are deleted and recreated. |
| TaxType | Used as an override if the default Tax Code for the selected AccountCode is not correct – see [TaxTypes](https://developer.xero.com/documentation/api/accounting/types#tax-rates). |
| TaxAmount | The tax amount is auto calculated as a percentage of the line amount (see below) based on the tax rate. This value must match the auto calculated value. |
| LineAmount | If you wish to omit either of the Quantity or UnitAmount you can provide a LineAmount and Xero will calculate the missing amount for you |
| Tracking | Optional Tracking Category – see [Tracking](https://developer.xero.com/documentation/api/accounting/trackingcategories). Any LineItem can have a maximum of 2 TrackingCategory elements. |

Elements for Bank Account. Either of the following are **mandatory** for a PUT / POST request

|  |  |
| --- | --- |
| Code | BankAccount code (this value may not always be present for a bank account) |
| AccountID | BankAccount identifier |

### Creating, updating and deleting line items when updating bank transactions

In an update (POST) request:

- Providing an existing LineItem with its LineItemID will update that line item.
- Providing a LineItem with no LineItemID will create a new line item.
- Not providing an existing LineItem with it's LineItemID will result in that line item being deleted.

### SummarizeErrors

If you are entering many bank transactions in a single API call then we recommend you utilise our response format that shows validation errors for each bank transaction. The new response messages for validating bulk API calls would mean a breaking change so to utilise this functionality you'll need to append `?SummarizeErrors=false` to the end of your API calls e.g. `POST /api.xro/2.0/BankTransactions?SummarizeErrors=false`

Example of minimum elements required to add a new spend money transaction.

```json
POST https://api.xero.com/api.xro/2.0/BankTransactions

```

copy code

```json
{
  "Type": "SPEND",
  "Contact": {
    "ContactID": "eaa28f49-6028-4b6e-bb12-d8f6278073fc"
  },
  "LineItems": [{\
    "Description": "Yearly Bank Account Fee",\
    "UnitAmount": "20.00",\
    "AccountCode": "404"\
  }],
  "BankAccount": {
    "Code": "BANK-ABC"
  }
}

```

copy code

Example of a receive money transaction **using an item code** of GB1-White.

```json
POST https://api.xero.com/api.xro/2.0/BankTransactions

```

copy code

```json
{
  "Type": "RECEIVE",
  "Contact": {
    "ContactID": "6d42f03b-181f-43e3-93fb-2025c012de92"
  },
  "Date": "2014-05-26T00:00:00",
  "LineAmountTypes": "Exclusive",
  "LineItems": [{\
    "Description": "Golf balls - white single",\
    "Quantity": "5",\
    "ItemCode": "GB1-White"\
  }],
  "BankAccount": {
    "Code": "090"
  }
}

```

copy code

Example of specifying a tracking category with a receive money transaction.

```json
POST https://api.xero.com/api.xro/2.0/BankTransactions

```

copy code

```json
{
  "Type": "RECEIVE",
  "Contact": {
    "ContactID": "6d42f03b-181f-43e3-93fb-2025c012de92"
  },
  "LineAmountTypes": "Inclusive",
  "LineItems": [{\
    "Description": "Monthly Retainer",\
    "UnitAmount": "575.00",\
    "AccountCode": "200",\
    "Tracking": [{\
        "Name": "Activity/Workstream",\
        "Option": "Website management"\
    }]\
  }],
  "BankAccount": {
    "Code": "091"
    },
  "Url": "http://www.accounting20.com"
}

```

copy code

Example of creating a receive prepayment

```json
POST https://api.xero.com/api.xro/2.0/BankTransactions

```

copy code

```json
{
  "Type": "RECEIVE-PREPAYMENT",
  "Contact": { "ContactID": "6d42f03b-181f-43e3-93fb-2025c012de92" },
  "BankAccount": { "Code": "090" },
  "LineAmountTypes": "Exclusive",
  "LineItems": [{\
    "Description": "Prepayment for Kitchen Designs",\
    "Quantity": "1",\
    "UnitAmount": "500.00",\
    "AccountCode": "200"\
  },{\
    "Description": "Prepayment for Kitchen materials",\
    "Quantity": "1",\
    "UnitAmount": "1000.00",\
    "AccountCode": "200"\
  }]
}

```

copy code

Example of creating a receive-overpayment

```json
POST https://api.xero.com/api.xro/2.0/BankTransactions

```

copy code

```json
{
  "Type": "RECEIVE-OVERPAYMENT",
  "Contact": { "ContactID": "6d42f03b-181f-43e3-93fb-2025c012de92" },
  "BankAccount": { "Code": "090" },
  "LineAmountTypes": "NoTax",
  "LineItems": [{\
    "Description": "Forgot to cancel annual sub payment",\
    "LineAmount": "100.00"\
  }]
}

```

copy code

Overpayments can only have a single line item. The line item will be automated coded to either the Accounts Receivable (receive) or Accounts Payable (spend) control account. You will see this account code contained in the response.

### Deleting spend and receive money transactions

You can delete a spend money or receive money transaction by updating the Status to DELETED. Deletes are not supported for spend prepayment, receive prepayment, spend overpayment or receive overpayment transactions.

Example of deleting a BankTransaction

```json
POST https://api.xero.com/api.xro/2.0/BankTransactions/4af93d54-0d13-459a-9d8a-d570982e2fb2

```

copy code

```json
{
  "BankTransactionID": "4af93d54-0d13-459a-9d8a-d570982e2fb2",
  "Status": "DELETED"
}

```

copy code

### Uploading an Attachment

You can upload up to 10 attachments (each up to 25mb in size) per bank transaction, once the bank transaction has been created in Xero. To do this you'll need to know the ID of the bank transaction which you'll use to construct the URL when POST/PUTing a byte stream containing the attachment file. See the [Attachments](https://developer.xero.com/documentation/api/accounting/attachments) page for more details.

```json
POST https://api.xero.com/api.xro/2.0/BankTransactions/f0ec0d8c-4330-bb3b-83062c6fd8/Attachments/Image002932.png
```

copy code

```json
Headers:
Authorization: Bearer...
Content Type: image/png
Content-Length: 10293

Body:
{RAW-IMAGE-CONTENT}

```

copy code

## PUT BankTransactions

[anchor for put banktransactions](https://developer.xero.com/documentation/api/accounting/banktransactions#put-banktransactions)

The PUT method is similar to the POST BankTransactions method, however you can only create new bank transactions with this method.

### Retrieving History

View a summary of the actions made by all users to the bank transaction. See the [History and Notes](https://developer.xero.com/documentation/api/accounting/historyandnotes) page for more details.

Example of retrieving a bank transaction's history

```json
GET https://api.xero.com/api.xro/2.0/BankTransactions/{Guid}/History
```

copy code

```json
{
  "HistoryRecords": [\
     {\
      "Changes": "Updated",\
      "DateUTCString": "2018-02-28T21:02:11",\
      "DateUTC": "\/Date(1519851731990+0000)\/",\
      "User": "System Generated",\
      "Details": "Received through the Xero API from ABC Org"\
    },\
    {\
      "Changes": "Created",\
      "DateUTCString": "2018-02-28T21:01:29",\
      "DateUTC": "\/Date(1519851689297+0000)\/",\
      "User": "Mac Haag",\
      "Details": "INV-0041 to ABC Furniture for 100.00."\
    }\
    ...\
  ]
}

```

copy code

### Add Notes to a Bank Transaction

Add a note which will appear in the history against a bank transaction. See the [History and Notes](https://developer.xero.com/documentation/api/accounting/historyandnotes) page for more details.

Example of creating a note against a bank transaction

```json
PUT https://api.xero.com/api.xro/2.0/BankTransactions/{Guid}/History
```

copy code

```json
{
  "HistoryRecords": [\
    {\
      "Details": "Note added by your favourite app!"\
    }\
    ...\
  ]
}

```

copy code

## On this page

- [Overview](https://developer.xero.com/documentation/api/accounting/banktransactions/#overview)
- [GET BankTransactions](https://developer.xero.com/documentation/api/accounting/banktransactions/#get-banktransactions)
- [POST BankTransactions](https://developer.xero.com/documentation/api/accounting/banktransactions/#post-banktransactions)
- [PUT BankTransactions](https://developer.xero.com/documentation/api/accounting/banktransactions/#put-banktransactions)

[iframe](https://www.google.com/recaptcha/api2/anchor?ar=1&k=6LfzQv8fAAAAAKRU2mXYpmmWwBZZzMH-jw9TKk3s&co=aHR0cHM6Ly9kZXZlbG9wZXIueGVyby5jb206NDQz&hl=en&v=1Bq_oiMBd4XPUhKDwr0YL1Js&size=invisible&cb=lolvnq6pikl)