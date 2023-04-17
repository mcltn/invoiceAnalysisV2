# IBM Cloud Classic Infrastructure Invoice Analysis Report
*invoiceAnalysis.py* collects IBM Cloud Classic Infrastructure NEW, RECURRING, ONE-TIME-CHARGES and CREDIT invoices between invoice months
specified, then consolidates the data into an Excel worksheet for billing analysis.  All charges are aligned to the IBM SLIC/CFTS invoice cycle of the 20th to 19th of a month.
In addition to consolidation of the detailed data and formatting consistent with SLIC/CFTS invoices, pivot tables are created to aid in reconilliation of invoices charges and month to month comparisons.

## Table of Contents
1. [Identity and Access Management Requirements](#identity-&-access-management-requirements)
2. [Output Description](#output-description)
3. [Script Installation](#script-installation-instructions)
3. [Script Execution](#script-execution-instructions)
4. [Other included Scripts](other-scripts.md)
5. [Code Engine: Configuring Invoice Analysis Report to automatically produce output each month](#running-invoice-analysis-report-as-a-code-engine-job)

## Identity & Access Management Requirements
| APIKEY                                        | Description                                                                | Min Access Permissions                                                        
|-----------------------------------------------|----------------------------------------------------------------------------|-------------------------------------------------------------------------------
| IBM Cloud API Key                             | API Key used access classic invoices.                                      | IAM Billing Viewer Role; if --storage specified, required classic infrastructure viewer permission for net storage.                                                     
| COS API Key                                   | (optional) API Key used to write output to specified bucket (if specified) | (optional) COS Bucket Write access to Bucket at specified Object Storage CRN. 
| Internal employee ims_username & ims_password | (optional) Credentials for internal IBM IMS access.                        | IMS Access to Account                                                 |


## Output Description
invoiceAnalysis produces an Excel worksheet with multiple tabs (based on the parameters specified) from the consolidated IBM Cloud invoice data for SLIC accounts.  This data includes all classic Infrastructure usage (hourly & monthly) as well as
IBM Cloud/PaaS usage billed through SLIC for the purpose of reconciliation of invoice charges. In general the SLIC Invoice Month contains all RECURRING, NEW, ONE-TIME-CHARGE, and CREDIT invoices between the 20th of the previous month and the 19th of
the current month.   IBM Cloud PaaS Usage appears on the monthly RECURRING invoice 2 months in arrears.   (i.e April PaaS Usage, will appear on the June 1st, RECURRING invoice a which will be on the SLIC/CFTS invoice received at the end of June.  All
invoice and line item data is normalized to match the SLIC invoice billing dates.

### Detail Tabs
| Tab Name      | Included by Default | flag to change default| Description of Tab 
|---------------|---------------------|----------------------|-------------------
| Detail | True                | --no-detail | Detailed list of every invoice line item (including chidlren line items) from all invoices types between date ranges specified.

### Monthly Invoice Tabs
One tab is created for each month in range specified and used for reconciliation against invoices.   Only required tabs are created.  (ie if no credit in a month, then no credit tab will be created)

| Tab Name      | Included by Default | flag to change default| Description of Tab 
|---------------|---------------------|----------------------|-------------------
| IaaS_YYYY-MM  | True                | --no-reconcilliation | Table matching each portal invoice's IaaS Charges to the IBM SLIC/CFTS invoice.  IaaS Charges are split into three categories VMware License Charges, Classic COS Charges, and All other Classic IaaS Charges for each portal invoice, these amounts should match the SLIC/CFTS invoice amounts and aid in reconciliation. 
| IaaS_Detail_YYYY-MM | True                | --no-reconcilliation | Table provides a more detailed breakdown of the IaaS charges, and particular helps understand Other Classic IaaS Charges from the IaaS-YYYY-MM tab.   This is for information only, and detail will not match the IBM SLIC/CFTS invoice detail. 
| PaaS_YYYY-MM  | True                | --no-reconcilliation | Table matching portal PaaS charges on RECURRING invoice PaaS for that month, which are included in that months SLIC/CFTS invoice.  PaaS Charges are typically consolidated into one amount for type1, though the detail is provided at a service level on this tab to faciliate reconcillation.  PaaS charges are for usage 2 months in arrears. 
| Credit-YYYY-MM | True                | --no-reconcilliation | Table of Credit Invoics to their corresponding IBM SLIC/CFTS invoice(s). 

### Summary Tabs
Tabs are created to summarize usage data based on SLIC invoice month.   If a range of months is specified, months are displayed as columns in each tab and can be used to compare month to month changes

| Tab Name      | Incuded by Default | flag to change default | Description of Tab 
|---------------|--------------------|-----------------------|-------------------
| CategoryGroupSummary | True               | --no-summary          | A pivot table of all charges shown by Invoice Type and Category Groups by month. 
| CategoryDetail | True               | --no-summary          | A pivot table of all charges by Invoice Type, Category Group, Category and specific service Detail by month. 
| Classic_COS_Detail | False              | --cosdetail           | A table of all Classic Cloud Object Storage Usage (if used)
| HrlyVirtualServerPivot | True               | --no-serverdetail     | A table of Hourly Classic VSI's if they exist 
| MnthlyVirtualServerPivot | True               | --no-serverdetail     | A table of monthly Classic VSI's if they exist 
| HrlyBareMetalServerPivot | True               | --no-serverdetail     | A table of Hourly Bare Metal Servers if they exist 
| MnthlyBareMetalServerPivot | True               | --no-serverdetail     | A table of monthly Bare Metal Server if they exist 
| StoragePivot | False              | --storage             | A Table of all Block and File Storage allocations by location with custom notes (if used)

#### Methodology for reconciliation
1. First Look at the IaaS-YYYY-MM tab for month being reconciled.  For each portal invoice (NEW, ONE-TIME-CHARGE, and RECURRING), the charges can be split into three categories VMware License Charges, Classic COS Charges, and All other Classic IaaS Charges.  These should match a line item on the SLIC/CFTS invoice.
2. Next look at the PaaS-YYYY-MM tab for month being reconciled.  PaaS charges only appear on the RECURRING invoice.  The total should match the SLIC/CFTS invoice total.
3. Next look at the Credit-YYYY-MM tab for month being reconciled.   For each CREDIT invoice the total should match the SLIC/CFTS invoice.


## Script Installation Instructions

1. Install Python 3.9+
2. Install required Python packages. 
````
$ pip install -r requirements.txt
````
3. For *Internal IBM IMS users* (employees) who wish to use internal credentials (with Yubikey 2FA) you must first manually uninstall the Public SoftLayer SDK and manually 
build the internal SDK for this script to function properly with internal credentials.  While running script you must be connected securely to IBM network via Global Protect VPN.
You will be prompted for your 2FA yubikey at each script execution.  Note you must invclude IMS account number in environment variable or command line.   [Internal SDK & Instructions](https://github.ibm.com/SoftLayer/internal-softlayer-cli)
```azure
$ pip uninstall SoftLayer
$ git clone https://github.ibm.com/SoftLayer/internal-softlayer-cli
$ cd internal-softlayer-cli
$ python setup.py install
$ ./islcli login

```
4. Set environment variables which can be used.  IBM COS only required if file needs to be written to COS, otherwise file will be written locally.  It is recommended that environment variables be specified in local .env file.

## Script Execution Instructions

| Parameter                 | Environment Variable | Default               | Description                   
|---------------------------|----------------------|-----------------------|-------------------------------
| --IC_API_KEY, -k          | IC_API_KEY           | None                  | IBM Cloud API Key to be used to retrieve invoices and usage. 
| --username                | ims_username         | None                  | Required only if using internal authorization (used instead of IC_API_KEY) 
| --password                | ims_password         | None                  | Required only if using internal authorization (used instead of IC_API_KEY) 
| --account                 | ims_account          | None                  | Required only if using internal authorization to specify IMS account to pull. 
| --STARTDATE, -s           | startdate            | None                  | Start Month in YYYY-MM format 
| --ENDDATE, -e             | enddate              | None                  | End Month in YYYY-MM format   
| --months                  | months               | 1                     | Number of months including last full month to include in report. (use instead of -s/-e) 
| --COS_APIKEY              | COS_APIKEY           | None                  | COS API to be used to write output file to object storage, if not specified file written locally. 
| --COS_BUCKET              | COS_BUCKET           | None                  | COS Bucket to be used to write output file to. 
| --COS_ENDPOINT            | COS_ENDPOINT         | None                  | COS Endpoint (with https://) to be used to write output file to. 
| --COS_INSTANCE_CRN        | COS_INSTANCE_CRN     | None                  | COS Instance CRN to be used to write output file to. 
| --sendGridApi             | sendGridApi          | None                  | SendGrid API key to use to send Email. 
| --sendGridTo              | sendGridTo           | None                  | SendGrid comma delimited list of email addresses to send output report to. 
| --sendGridFrom            | sendGridFrom         | None                  | SendGrid from email addresss to send output report from. 
| --sendGridSubject         | sendGridSubject      | None                  | SendGrid email subject.       
| --output                  | output               | invoice-analysis.xlsx | Output file name used.        
| --SL_PRIVATE              |                      | --no_SL_PRIVATE       | Whether to use Public or Private Endpoint. 
| [--type2](type2output.md) |                      | --no_type2            | Specify Type 2 output (future format, not currently widely used)
| --storage                 |                      | --no_storage          | Whether to write additional level of classic Block & File storage analysis to worksheet (default: False) 
| --no-summary              |                      | --summary             | Whether to write summary detail tabs to worksheet. (default: True)
| --no-detail               |                      | --detail              | Whether to Write detail tabs to worksheet. (default: True)
| --no-reconciliation       |                      | --reconciliation      | Whether to write invoice reconciliation tabs to worksheet. (default: True)
| --no-serverdetail         |                      | --serverdetail        | Whether to write server detail tabs to worksheet (default: True)
| --cosdetail               |                      | --no-cosdetail        | Whether to write Classic OBject Storage tab to worksheet (default: False)

1. Run Python script (Python 3.9+ required).</br>
To analyze invoices between two months.
```bazaar
$ export IC_API_KEY=<ibm cloud apikey>
$ python invoiceAnalysis.py -s 2021-01 -e 2021-06
```
To analyze last 3 invoices.
```bazaar
$ export IC_API_KEY=<ibm cloud apikey>
$ python inboiceAnalysis.py -m 3
```
```bazaar
usage: invoiceAnalysis.py [-h] [-k IC_API_KEY] [-u username] [-p password] [-a account] [-s STARTDATE] [-e ENDDATE] [--months MONTHS] [--COS_APIKEY COS_APIKEY] [--COS_ENDPOINT COS_ENDPOINT] [--COS_INSTANCE_CRN COS_INSTANCE_CRN] [--COS_BUCKET COS_BUCKET] [--sendGridApi SENDGRIDAPI]
                          [--sendGridTo SENDGRIDTO] [--sendGridFrom SENDGRIDFROM] [--sendGridSubject SENDGRIDSUBJECT] [--output OUTPUT] [--SL_PRIVATE | --no-SL_PRIVATE] [--type2 | --no-type2] [--storage | --no-storage] [--detail | --no-detail] [--summary | --no-summary]
                          [--reconciliation | --no-reconciliation] [--serverdetail | --no-serverdetail] [--cosdetail | --no-cosdetail]

Export usage detail by invoice month to an Excel file for all IBM Cloud Classic invoices and corresponding lsPaaS Consumption.

optional arguments:
  -h, --help            show this help message and exit
  -k IC_API_KEY         IBM Cloud API Key
  -u username, --username username
                        IBM IMS Userid
  -p password, --password password
                        IBM IMS Password
  -a account, --account account
                        IMS Account
  -s STARTDATE, --startdate STARTDATE
                        Start Year & Month in format YYYY-MM
  -e ENDDATE, --enddate ENDDATE
                        End Year & Month in format YYYY-MM
  --months MONTHS       Number of months including last full month to include in report.
  --COS_APIKEY COS_APIKEY
                        COS apikey to use for Object Storage.
  --COS_ENDPOINT COS_ENDPOINT
                        COS endpoint to use for Object Storage.
  --COS_INSTANCE_CRN COS_INSTANCE_CRN
                        COS Instance CRN to use for file upload.
  --COS_BUCKET COS_BUCKET
                        COS Bucket name to use for file upload.
  --sendGridApi SENDGRIDAPI
                        SendGrid ApiKey used to email output.
  --sendGridTo SENDGRIDTO
                        SendGrid comma deliminated list of emails to send output to.
  --sendGridFrom SENDGRIDFROM
                        Sendgrid from email to send output from.
  --sendGridSubject SENDGRIDSUBJECT
                        SendGrid email subject for output email
  --output OUTPUT       Filename Excel output file. (including extension of .xlsx)
  --SL_PRIVATE, --no-SL_PRIVATE
                        Use IBM Cloud Classic Private API Endpoint (default: False)
  --type2, --no-type2   Break out detail by 'D codes' consistent with CFTS Sprint process used for multiple work numbers. (default: False)
  --storage, --no-storage
                        Include File, BLock and Classic Cloud Object Storage detail analysis. (default: False)
  --detail, --no-detail
                        Whether to Write detail tabs to worksheet. (default: True)
  --summary, --no-summary
                        Whether to Write summarytabs to worksheet. (default: True)
  --reconciliation, --no-reconciliation
                        Whether to write invoice reconciliation tabs to worksheet. (default: True)
  --serverdetail, --no-serverdetail
                        Whether to write server detail tabs to worksheet. (default: True)
  --cosdetail, --no-cosdetail
                        Whether to write Classic OBject Storage tab to worksheet. (default: False)


```

## Running Invoice Analysis Report as a Code Engine Job
Requirements
* Creation of an Object Storage Bucket to store the script output in at execution time. 
* Creation of an IBM Cloud Object Storage Service API Key with read/write access to bucket above
* Creation of an IBM Cloud API Key with Billing Service (View access))

### Setting up IBM Code Engine to run report from IBM Cloud Portal
1. Open IBM Cloud Code Engine Console from IBM Cloud Portal (left Navigation)
2. Create project, build job and job.
   - Select Start creating from Start from source code.  
   - Select Job  
   - Enter a name for the job such as invoiceanalysis. Use a name for your job that is unique within the project.  
   - Select a project from the list of available projects of if this is the first one, create a new one. Note that you must have a selected project to deploy an app.  
   - Enter the URL for this GitHub repository and click specify build details. Make adjustments if needed to URL and Branch name. Click Next.  
   - Select Dockerfile for Strategy, Dockerfile for Dockerfile, 10m for Timeout, and Medium for Build resources. Click Next.  
   - Select a container registry location, such as IBM Registry, Dallas.  
   - Select Automatic for Registry access.  
   - Select an existing namespace or enter a name for a new one, for example, newnamespace. 
   - Enter a name for your image and optionally a tag.  
   - Click Done.  
   - Click Create.  
2. Create ***configmaps*** and ***secrets***.  
    - From project list, choose newly created project.  
    - Select secrets and configmaps  
    - Click create, choose config map, and give it a name. Add the following key value pairs    
      - ***COS_BUCKET*** = Bucket within COS instance to write report file to.  
      - ***COS_ENDPOINT*** = Public COS Endpoint (including https://) for bucket to write report file to  
      - ***COS_INSTANCE_CRN*** = COS Service Instance CRN in which bucket is located.<br>
	- Select secrets and configmaps (again)
    - Click create, choose secrets, and give it a name. Add the following key value pairs
      - ***IC_API_KEY*** = an IBM Cloud API Key with Billing access to IBM Cloud Account  
      - ***COS_APIKEY*** = your COS Api Key with writter access to appropriate bucket  
3. Choose the job previously created.  
   - Click on the Environment variables tab.   
   - Click add, choose reference to full configmap, and choose configmap created in previous step and click add.  
   - Click add, choose reference to full secret, and choose secrets created in previous step and click add.  
   - Click add, choose literal value (click add after each, and repeat to set required environment variables.)
     - ***months*** = number of months to include if more than 1.<br>
     - ***output*** = report filename (including extension of XLSX to be written to COS bucket)<br>  
4. Specify Any command line parameters using Command Overrides.<br>
   - Click Command Overrides (see tables above) <br>
   - Under Arguments section specify command line arguments with one per line.
    ```azure
    --no-detail
    --no-reconcilliation
    ```
5. To configure the report to run at a specified date and time configure an Event Subscription.
   - From Project, Choose Event Subscription
   - Click Create
   - Choose Event type of Periodic timer
   - Name subscription; click Next
   - Select cron pattern or type your own.  
   - Recommend monthly on the 20th, as this is the SLIC/CFTS cutoff.  The following pattern will run the job at 07 UTC (2am CDT) on the 20th of every month. 
    ```
    00 07  20 * *
    ```
   - Click Next
   - Leave Custom event data blank, click Next.
   - Choose Event Consumer.  Choose Component Type of Job, Choose The Job Name for the job you created in Step 1.   Click Next.
   - Review configuration Summary; click create.
6. To Run report "On Demand" click ***Submit job***
7. Logging for job can be found from job screen, by clicking Actions, Logging