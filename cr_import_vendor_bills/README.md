# CR Import Vendor Bills

This module import Vendor Bills from incoming mail server.

Setup
=====

Go to TECHNICIAN, in INCOMING MAIL SERVERS, create and configure the following:

SERVER AND CONNECTION

    SERVER NAME: service host

    USER NAME: email or username

    PORT: Connection port

    PASSWORD: password

    SSL / TSL: Check if required

ADVANCED TAB

    It is recommended to leave the default values

    KEEP ORIGINAL: Select to keep the mail in the inbox (it is recommended not to mark it)

    After configuring save and click on the Test and confirm button

    ** Now is a good time to go to the scheduled task and modify the execution time if necessary, by default it is every 5 minutes **

Activate in the company

Go to COMPANY and activate the function for the company (the module supports multi-companies)

In the Import of invoices tab, select the option to Import Supplier Invoices and fill in the required fields

    MAIL SERVER: Import Supplier Invoice (configured in the previous step)

    JOURNAL: Select the supplier invoices journal

    PRODUCT: Select the default product that will be assigned to each line (OPTIONAL not wanted)

    EXPENSES ACCOUNT: Select the accounting account to be assigned to each line (MANDATORY, this account can be changed if necessary in each line of the invoice)

    ANALYTICAL ACCOUNT: Select or create the analytical account that will be assigned to each line (OPTIONAL, this account can be changed if necessary in each line of the invoice)

Functioning
=====

The function is executed, reads the emails in the inbox and validates the information

When it finds an attached XML file, it validates the company's VAT number

    If the company's NIF matches, validate the supplier's NIF
        If the supplier's NIF exists
            Upload the information to a supplier invoice, leaving it in a draft state for later validation

        If the supplier's NIF does not exist
            Create the supplier with the XML information and upload the information in a supplier invoice, leaving it in a draft state for later validation

        All the messages referring to each supplier invoice are added in the messages section (Ex: The supplier does not exist, it has been created automatically - etc - etc)
        Attach the files (PDF, XML receipt and XML response)
        ** If you only find the response XML, attach this file to the corresponding invoice and delete the email from the inbox **
        Delete the email from the account if this option was selected in the incoming email settings (RECOMMENDED)

    If the company ID does not match
        Ignore mail and keep it in the inbox

    If it can't find valid files to process, ignore the email by leaving it in the inbox.
    When the supplier invoice is created with this process, the fields partner, supplier reference, voucher type, payment methods, currency, supplier xml and invoice date will be type fields (read only).
    If the numeric key already exists when validating the XML, the process is ignored and the email is removed from the inbox.
    When validating the XML invoice, if the numeric key already exists, the process is ignored and the mail is removed from the inbox.
    When validating the response XML if the "Has ACK" box is already checked, the process is ignored and the email is removed from the inbox.

Recommendations
===========
*** Important: Go to Technician - Pseudonyms and delete SUPPLIER INVOICES ***

You can create a single email to receive from several companies; each company validates the XML, takes the one that corresponds to it and executes the entire previous process.

Create an exclusive email for this service and schedule the resending from the email accounts that receive the FE
Mail must be maintained to eliminate junk mail


Bug Tracker
===========

Bugs are tracked on Issues section.
In case of trouble, please check there if your issue has already been reported.
If you spotted it first, help us smashing it by providing a detailed and welcomed
feedback.

Do not contact contributors directly about support or help with technical issues.


Contributors
============

* Carlos Monge
* Kendall Adanis
* Luis Felipe
* Rolando Quirós

You are welcome to contribute.
