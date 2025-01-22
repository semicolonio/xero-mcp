# Payments

[Try in API Explorer](https://api-explorer.xero.com/accounting/payments)

## Overview

|  |  |
| --- | --- |
| URL | [https://api.xero.com/api.xro/2.0/Payments](https://api.xero.com/api.xro/2.0/Payments) |
| Methods Supported | [GET](https://developer.xero.com/documentation/api/accounting/payments#get-payments), [PUT](https://developer.xero.com/documentation/api/accounting/payments#put-payments), [POST](https://developer.xero.com/documentation/api/accounting/payments#post-payments) |
| Description | Retrieve either one or many payments for invoices and credit notes <br>Apply payments to approved AR and AP invoices <br>Allow you to refund credit notes <br>Delete (reverse) a payment <br>Allows you to refund prepayments and overpayments <br>Allows you to retrieve history <br>Allows you to add notes |

To pay multiple AR or AP invoices in a single transaction use the [BatchPayments](https://developer.xero.com/documentation/api/accounting/batchpayments) endpoint.

## GET Payments

[anchor for get payments](https://developer.xero.com/documentation/api/accounting/payments#get-payments)

Use this method to retrieve either one or many payments for invoices and credit notes

|  |  |
| --- | --- |
| Date | Date the payment is being made (YYYY-MM-DD) e.g. 2009-09-06 |
| CurrencyRate | Exchange rate when payment is received. Only used for non base currency invoices and credit notes e.g. 0.7500 |
| Amount | The amount of the payment. Must be less than or equal to the outstanding amount owing on the invoice e.g. 200.00 |
| Reference | An optional description for the payment e.g. Direct Debit |
| IsReconciled | An optional parameter for the payment. Conversion related apps can utilise the IsReconciled flag in scenarios when a matching bank statement line is not available. [Learn more](http://help.xero.com/#Q_BankRecNoImport) |
| Status | The [status](https://developer.xero.com/documentation/api/accounting/types#payment-status-codes) of the payment. |
| PaymentType | See [Payment Types](https://developer.xero.com/documentation/api/accounting/types#PaymentTypes). |
| UpdatedDateUTC | UTC timestamp of last update to the payment |
| BatchPaymentID | Present if the payment was created as part of a batch. |
| BatchPayment | Details of the Batch the payment was part of. See [Batch Payments](https://developer.xero.com/documentation/api/accounting/batchpayments) for more details. |
| Account | The [Account](https://developer.xero.com/documentation/api/accounting/accounts) the payment was made from |
| Invoice | The [Invoice](https://developer.xero.com/documentation/api/accounting/invoices) the payment was made against |
| CreditNote | The [Credit Note](https://developer.xero.com/documentation/api/accounting/creditnotes) the payment was made against |
| Prepayments | The [Prepayment](https://developer.xero.com/documentation/api/accounting/prepayments) the payment was made against |
| Overpayment | The [Overpayment](https://developer.xero.com/documentation/api/accounting/overpayments) the payment was made against |

### Optional parameters for GET Payments

|  |  |
| --- | --- |
| Record filter | You can specify an individual record by appending the PaymentID to the endpoint, i.e. <br>**GET [https://.../Payments/297c2dc5-cc47-4afd-8ec8-74990b8761e9](https://.../Payments/297c2dc5-cc47-4afd-8ec8-74990b8761e9)** |
| Modified After | The ModifiedAfter filter is actually an HTTP header: 'If-Modified-Since'. note payments created or modified since this timestamp will be returned e.g. 2009-11-12T00:00:00 |
| Where | Filter by any element ( _see [Filters](https://developer.xero.com/documentation/api/accounting/requests-and-responses#retrieving-modified-resources)_ ). Only [certain elements](https://developer.xero.com/documentation/#optimised-parameters) are optimised to ensure performance across organisations of all sizes. |
| Order | Order by any element returned ( _see [Order By](https://developer.xero.com/documentation/api/accounting/requests-and-responses/#http-get)_ ). Only [certain elements](https://developer.xero.com/documentation/#optimised-ordering) are optimised to ensure performance across organisations of all sizes. |
| Page | Up to 100 payments will be returned per call when the page parameter is used e.g. page=1 |

### High volume threshold limit

In order to make our platform more stable, we've added a high volume threshold limit for the GET Payments Endpoint.

- Requests that have more than 100k payments being returned in the response will be denied and receive a 400 response code
- Requests using unoptimised fields for filtering or ordering that result in more than 100k payments will be denied with a 400 response code

Please continue reading to find out how you can use paging and optimise your filtering to ensure your requests are always successful. Be sure to check out the [Efficient Data Retrieval](https://developer.xero.com/documentation/api/efficient-data-retrieval) page for tips on query optimisation.

### Paging payments (recommended)

More information about [retrieving paged resources](https://developer.xero.com/documentation/api/accounting/requests-and-responses#retrieving-paged-resources).

### Optimised filtering using the where parameter

The most common filters have been optimised to ensure performance across organisations of all sizes. We recommend you restrict your filtering to the following optimised parameters.

#### Range Operators in Where clauses

Indicated fields also support the range operators: greater than, greater than or equals, less than, less than or equals (>, >=, <, <=).

Range operators can be combined with the AND operator to query a date range. eg where=Date>=DateTime(2020, 01, 01) AND Date<DateTime(2020, 02, 01)

_When using individually or combined with the AND operator:_

| Field | Operator | Query |
| --- | --- | --- |
| PaymentType | equals | where=PaymentType="ACCRECPAYMENT" |
| Status | equals | where=Status="AUTHORISED" |
| Date | equals, range | where=Date=DateTime(2020, 01, 01)<br>where=Date>DateTime(2020, 01, 01) |
| Invoice.InvoiceId | equals | where=Invoice.InvoiceID=guid("96988e67-ecf9-466d-bfbf-0afa1725a649") |
| Reference | equals | where=Reference="INV-0001" |

_When using with the OR operator:_

| Field | Operator | Query |
| --- | --- | --- |
| PaymentId | equals | where=PaymentID=guid("0a0ef7ee-7b91-46fa-8136-c4cc6287273a") OR PaymentID=guid("603b8347-d833-4e65-abf9-1f465652cb42") |
| Invoice.InvoiceId | equals | where=Invoice.InvoiceId=guid("0b0ef7ee-7b91-46fa-8136-c4cc6287273a") OR Invoice.InvoiceId=guid("693b8347-d833-4e65-abf9-1f465652cb42") |

**Example:** Retrieve all ACCRECPAYMENT payments with an AUTHORISED status

```json
?where=Type=="ACCRECPAYMENT" AND Status=="AUTHORISED"
```

copy code

This would translate to the following URL once encoded.

```json
https://api.xero.com/api.xro/2.0/Payments?where=Type%3D%3D%22ACCRECPAYMENT%22+AND+Status%3D%3D%22AUTHORISED%22%0D%0A
```

copy code

### Optimised ordering:

The following parameters are optimised for ordering:

- UpdatedDateUTC
- Date
- PaymentId

The default order is _UpdatedDateUTC ASC, PaymentId ASC_. Secondary ordering is applied by default using the PaymentId. This ensures consistency across pages.

The example below is fetching a payment on an AR invoice in the base currency of the organisation

```json
GET https://api.xero.com/api.xro/2.0/Payments/b26fd49a-cbae-470a-a8f8-bcbc119e0379
```

copy code

```json
{
  "Payments": [\
    {\
      "PaymentID": "b26fd49a-cbae-470a-a8f8-bcbc119e0379",\
      "BatchPaymentID": "b54aa50c-794c-461b-89d1-846e1b84d9c0",\
      "BatchPayment": {\
        "Account": {\
          "AccountID": "ac993f75-035b-433c-82e0-7b7a2d40802c"\
        },\
        "BatchPaymentID": "b54aa50c-794c-461b-89d1-846e1b84d9c0",\
        "Date": "\/Date(1455667200000+0000)\/",\
        "Type": "RECBATCH",\
        "Status": "AUTHORISED",\
        "TotalAmount": "600.00",\
        "UpdatedDateUTC": "\/Date(1289572582537+0000)\/",\
        "IsReconciled": "true"\
      },\
      "Date": "\/Date(1455667200000+0000)\/",\
      "BankAmount": 500.00,\
      "Amount": 500.00,\
      "Reference": "INV-0001",\
      "CurrencyRate": 1.000000,\
      "PaymentType": "ACCRECPAYMENT",\
      "Status": "AUTHORISED",\
      "UpdatedDateUTC": "\/Date(1289572582537+0000)\/",\
      "HasAccount": true,\
      "IsReconciled": true,\
      "Account": {\
        "AccountID": "ac993f75-035b-433c-82e0-7b7a2d40802c",\
        "Code": "090"\
      },\
      "Invoice": {\
        "Type": "ACCREC",\
        "InvoiceID": "b0875d8b-ff26-4ce8-8aea-6955492ead48",\
        "InvoiceNumber": "INV-0001",\
        "Contact": {\
          "ContactID": "fef6755f-549b-4617-b1e9-60bdffb517d8",\
          "Name": "Ridgeway University"\
        }\
      }\
    }\
  ]
}

```

copy code

## PUT Payments

[anchor for put payments](https://developer.xero.com/documentation/api/accounting/payments#put-payments)

Use this method to apply payments to approved AR and AP invoices or refund AR or AP credit notes.

Invoice or CreditNote or Prepayment or Overpayment

|  |  |  |
| --- | --- | --- |
| _either_ | **InvoiceID or CreditNoteID or PrepaymentID or OverpaymentID** | ID of the invoice, credit note, prepayment or overpayment you are applying payment to e.g. 297c2dc5-cc47-4afd-8ec8-74990b8761e9 |
| _or_ | **InvoiceNumber or CreditNoteNumber** | Number of invoice or credit note you are applying payment to e.g. INV-4003 |

Account

|  |  |  |
| --- | --- | --- |
| _either_ | AccountID | ID of account you are using to make the payment e.g. 294b1dc5-cc47-2afc-7ec8-64990b8761b8. This account needs to be either an account of type BANK or have enable payments to this accounts switched on (see [GET Accounts](https://developer.xero.com/documentation/api/accounting/accounts)) . See the edit account screen of your Chart of Accounts in Xero if you wish to enable payments for an account other than a bank account |
| _or_ | Code | Code of account you are using to make the payment e.g. 001 ( _note: not all accounts have a code value_) |

|  |  |  |
| --- | --- | --- |
| Date |  | Date the payment is being made (YYYY-MM-DD) e.g. 2009-09-06 |
| CurrencyRate |  | Exchange rate when payment is received. Only used for non base currency invoices and credit notes e.g. 0.7500 |
| Amount |  | The amount of the payment. Must be less than or equal to the outstanding amount owing on the invoice e.g. 200.00 |
| Reference |  | An optional description for the payment e.g. Direct Debit |
| IsReconciled |  | A boolean indicating whether the payment has been reconciled. |
| Status |  | The [status](https://developer.xero.com/documentation/api/accounting/types#payment-status-codes) of the payment. |

### Example – single payment

Below is an example of applying a $32.06 payment to invoice OIT00545 from Account Code 001 on 8 Sept 2009.

```json
{
  "Invoice": { "InvoiceID": "96df0dff-43ec-4899-a7d9-e9d63ef12b19" },
  "Account": { "Code": "001" },
  "Date": "2009-09-08",
  "Amount": 32.06
}

```

copy code

### Example – multiple payments

Below is an example of applying multiple payments to various Invoices (identified by InvoiceID) from various Accounts (identified by AccountID) across various dates.

```json
{
  "Payments": [\
    {\
      "Invoice": { "InvoiceID": "96df0dff-43ec-4899-a7d9-e9d63ef12b19" },\
      "Account": { "AccountID": "297c2dc5-cc47-4afd-8ec8-74990b8761e9" },\
      "Date": "2009-07-13",\
      "Amount": 3375.00\
    },\
    {\
      "Invoice": { "InvoiceID": "0a1d0d71-b001-4c71-a260-31e77c9d4a92" },\
      "Account": { "AccountID": "a65b0dac-b444-4b41-959b-c1580cd6268f" },\
      "Date": "2009-09-01",\
      "Amount": 393.75\
    },\
    {\
      "Invoice": { "InvoiceID": "93c9be81-1df4-4338-b5dc-e67a89cd2d7c" },\
      "Account": { "AccountID": "a65b0dac-b444-4b41-959b-c1580cd6268f" },\
      "Date": "2009-07-21",\
      "Amount": 398\
    }\
  ]
}

```

copy code

### Example – credit note refunds

Below is an example of refunding the full amount of $50.00 of credit note CN-007 to a bank account

```json
{
  "CreditNote": { "CreditNoteNumber": "CN-007" },
  "Account": { "Code": "090" },
  "Date": "2013-09-04",
  "Amount": 50.00,
  "Reference": "Full refund as we couldn't replace item"
}

```

copy code

Below is an example of refunding a part amount of $100 of a credit note to a bank account in a different currency to the credit note.

```json
{
  "CreditNote": { "CreditNoteNumber": "CN-007" },
  "Account": { "Code": "AUD" },
  "Date": "2013-09-04",
  "Amount": 50.00,
  "CurrencyRate": "0.8"
}

```

copy code

### Example – prepayment refunds

Below is an example of refunding the full amount of $100.00 of prepayment 262c3049-cbf2-4b4b-9fca-60d55b076e35 to a bank account

```json
{
  "Prepayment": { "PrepaymentID": "262c3049-cbf2-4b4b-9fca-60d55b076e35" },
  "Account": { "Code": "090" },
  "Date": "2015-03-25",
  "Amount": 100.00,
  "Reference": "Full refund as the customer cancelled their subscription"
}

```

copy code

### Example – overpayment refunds

Below is an example of refunding the full amount of $200.00 of overpayment 1ced4be7-ea6d-4f46-8279-4203e461de80 to a bank account

```json
{
  "Overpayment": { "OverpaymentID": "1ced4be7-ea6d-4f46-8279-4203e461de80" },
  "Account": { "Code": "090" },
  "Date": "2015-04-01",
  "Amount": 200.00,
  "Reference": "Refunded overpayment made by mistake"
}

```

copy code

### Example – Creating a reconciled payment

Below is an example for applying an automatically reconciled payment to an invoice (useful for conversion purposes)

```json
{
  "Invoice": { "InvoiceNumber": "OIT00619" },
  "Account": { "Code": "001" },
  "Date": "2009-09-08",
  "Amount": 20.00,
  "IsReconciled": true
}

```

copy code

## POST Payments

[anchor for post payments](https://developer.xero.com/documentation/api/accounting/payments#post-payments)

Use this method to delete (reverse) payments to invoices, credit notes, prepayments & overpayments. Note that payments created via batch payments and receipts are not supported. Payments cannot be modified, only created and deleted.

### Required parameters for POST Payments

|  |  |
| --- | --- |
| PaymentID | The Xero identifier for an Payment e.g. 297c2dc5-cc47-4afd-8ec8-74990b8761e9 |

### Example – delete a payment

Below is an example of deleting a payment. In order to delete a payment, you must POST to the resource ID for the payment. e.g POST /Payments/b05466c8-dc54-4ff8-8f17-9d7008a2e44b

```json
{
  "Status": "DELETED"
}

```

copy code

### Retrieving History

View a summary of the actions made by all users to the payment. See the [History and Notes](https://developer.xero.com/documentation/api/accounting/historyandnotes) page for more details.

Example of retrieving a payment's history

```json
GET https://api.xero.com/api.xro/2.0/Payments/{Guid}/History
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

### Add Notes to a Payment

Add a note which will appear in the history against a payment. See the [History and Notes](https://developer.xero.com/documentation/api/accounting/historyandnotes) page for more details.

Example of creating a note against a payment

```json
PUT https://api.xero.com/api.xro/2.0/Payments/{Guid}/History
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

- [Overview](https://developer.xero.com/documentation/api/accounting/payments/#overview)
- [GET Payments](https://developer.xero.com/documentation/api/accounting/payments/#get-payments)
- [PUT Payments](https://developer.xero.com/documentation/api/accounting/payments/#put-payments)
- [POST Payments](https://developer.xero.com/documentation/api/accounting/payments/#post-payments)

[iframe](https://www.google.com/recaptcha/api2/anchor?ar=1&k=6LfzQv8fAAAAAKRU2mXYpmmWwBZZzMH-jw9TKk3s&co=aHR0cHM6Ly9kZXZlbG9wZXIueGVyby5jb206NDQz&hl=en&v=1Bq_oiMBd4XPUhKDwr0YL1Js&size=invisible&cb=60oj0mlyue3u)
