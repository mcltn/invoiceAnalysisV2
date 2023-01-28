# IBM Cloud Classic Infrastructure Invoice Analysis Report V2
*invoiceAnalysis.py* collects IBM Cloud Classic Infrastructure NEW, RECURRING, ONE-TIME-CHARGES and CREDIT invoices between invoice months
specified, then consolidates the data into an Excel worksheet for billing analysis.  All charges are aligned to the IBM SLIC/CFTS invoice cycle of the 20th to 19th of a month.
In addition to consolidation of the detailed data and formatting consistent with SLIC/CFTS invoices, pivot tables are created to aid in reconiliation of  invoices charges.

### Required Files
Script | Description
------ | -----------
invoiceAnalysis.py | Export usage detail by SLIC invoice month to an Excel file for all IBM Cloud Classic invoices.
estimateCloudUsage.py | Estimate current monbth usage for Platform as a Service from start of month to current date & time
classicConfigAnalysis.py | Analyze the Classic Bare Metal Servers within an account; outputing an Excel worksheet with various inventory details including network VLANs.
classicConfigReport.py | Creates a detailed report of Classic Bare Metal Servers within an account outputing a plain text inventory report.
requirements.txt | Package requirements
logging.json | LOGGER config used by script


### Identity & Access Management Requirements
| APIKEY                                     | Description                                                               | Min Access Permissions
|--------------------------------------------|---------------------------------------------------------------------------|----------------------
| IBM Cloud API Key                          | API Key used to pull classic and PaaS invoices and Usage Reports.         | IAM Billing Viewer Role
| COS API Key                                | API Key used to write output to specified bucket (if specified)           | COS Bucket Write access to Bucket at specified Object Storage CRN.
| ims_username, ims_password<br/>ims_account | Credentials for internal IMS access.  | IMS Access to Account|


### Output Description (invoiceAnalysis.py)
An Excel worksheet is created with multiple tabs from the collected data from the IBM Cloud Classic Invoices, which will include PaaS usage for the purpose of reconciliation of charges.
In general SLIC/CFTS Invoice Month contains all RECURRING, NEW, ONE-TIME-CHARGE, and CREDIT invoices between the 20th of the previous month and the 19th of the current month.  If a range of
months is specifiied, tabs will either be created for each month, or a single table will display monthly usage side by side.   Note PaaS Usage appears on the RECURRING invoice in arrears 
for two months prior.   (i.e April PaaS Usage, will appear on the June 1st, RECURRING invoice and be on the SLIC/CFTS received at the end of June.

Up to 3 SLIC/CFTS Invoices are generated each month.  One for IaaS charges, one for PaaS Charges, and one for Credit Charges.  Depending on how the SLIC account is configured and whether
there are manual billing processes required this can change the format of invoices.  These are described below as Type 1 or Type 2 below.

### Type 1 (most common) Reconciliation Approach (Default Output)

**Detail**

| Tab Name      | Default | flag to change default| Description of Tab 
|---------------|---------|----------------------|-------------------
| Detail | True | --no-detail | Detailed list of every invoice line item (including chidlren line items) from all invoices types between date range specified.

**Tabs created for each month in range specified and used for reconciliation against invoicese.**

| Tab Name      | Default | flag to change default| Description of Tab 
|---------------|---------|----------------------|-------------------
| IaaS_YYYY-MM  | True | --no-reconcilliation | Table matching each portal invoice's IaaS Charges to the IBM SLIC/CFTS invoice.  IaaS Charges are split into three categories VMware License Charges, Classic COS Charges, and All other Classic IaaS Charges for each portal invoice, these amounts should match the SLIC/CFTS invoice amounts and aid in reconciliation. 
| IaaS_Detail_YYYY-MM | True | --no-reconcilliation | Table provides a more detailed breakdown of the IaaS charges, and particular helps understand Other Classic IaaS Charges from the IaaS-YYYY-MM tab.   This is for information only, and detail will not match the IBM SLIC/CFTS invoice detail. 
| PaaS_YYYY-MM  | True | --no-reconcilliation | Table matching portal PaaS charges on RECURRING invoice PaaS for that month, which are included in that months SLIC/CFTS invoice.  PaaS Charges are typically consolidated into one amount for type1, though the detail is provided at a service level on this tab to faciliate reconcillation.  PaaS charges are for usage 2 months in arrears. 
| Credit-YYYY-MM |  True | --no-reconcilliation | Table of Credit Invoics to their corresponding IBM SLIC/CFTS invoice(s). 

**Tabs which are created with range of months displayed as columns in each tab and used for understanding month to month change**

| Tab Name      | Default | flag to change default | Description of Tab 
|---------------|---------|------------------------|-------------------
| CategoryGroupSummary | True | --no-summary           | A pivot table of all charges shown by Invoice Type and Category Groups by month. 
| CategoryDetail | True  | --no-summary           | A pivot table of all charges by Invoice Type, Category Group, Category and specific service Detail by month. 
| Classic_COS_Detail | False | --cos-detail           | A table of all Classic Cloud Object Storage Usage (if used)
| HrlyVirtualServerPivot | True | --no-serverdetail      | A table of Hourly Classic VSI's if they exist 
| MnthlyVirtualServerPivot | True | --no-serverdetail      | A table of monthly Classic VSI's if they exist 
| HrlyBareMetalServerPivot | True | --no-serverdetail      | A table of Hourly Bare Metal Servers if they exist 
| MnthlyBareMetalServerPivot | True | --no-serverdetail      | A table of monthly Bare Metal Server if they exist 
| StoragePivot | False | --storage              | A Table of all Block and File Storage allocations by location with custom notes (if used)


Methodology for reconciliation
1. First Look at the IaaS-YYYY-MM tab for month being reconciled.  For each portal invoice (NEW, ONE-TIME-CHARGE, and RECURRING), the charges can be split into three categories VMware License Charges, Classic COS Charges, and All other Classic IaaS Charges.  These should match a line item on the SLIC/CFTS invoice.
2. Next look at the PaaS-YYYY-MM tab for month being reconciled.  PaaS charges only appear on the RECURRING invoice.  The total should match the SLIC/CFTS invoice total.
3. Next look at the Credit-YYYY-MM tab for month being reconciled.   For each CREDIT invoice the total should match the SLIC/CFTS invoice.

If you don't understand the line item charges on any of the three invoices, for IaaS you can use the IaaS-Detail-YYYY-MM tab for an additional level of detail.  Additionally using the Category
detail tab and Virtual and Baremetal pivot tabs to compare month to month changes to identify what changed.  

   ***example:*** to provide the 3 latest months of detail
   ```bazaar
   $ export IC_API_KEY=<ibm cloud apikey>
   $ python invoiceAnalysis.py -m 3
   ```

### Type 2 (less common) Reconciliation Approach (specify --type2 on command line to generate this output)
**Details**

| Tab Name      | Default | flag to change default| Description of Tab 
|---------------|---------|----------------------|-------------------
| Detail | True | --no-detail | Detailed list of every invoice line item (including chidlren line items) from all invoices types between date range specified.

**Tabs which are created with range of months displayed as columns in each tab**

| Tab Name                | Default | flag to change default | Description of Tab 
|-------------------------|---------|------------------------|-------------------
| InvoiceSummary          | True    | --no-summary           | is a table of all charges by product group and category for each month by invoice type. This tab can be used to understand changes in month-to-month usage.
| CategorySummary         | True    | --no-summary           | is a table  of all charges by product group, category, and description (for example specific VSI sizes or Bare metal server types) to dig deeper into month to month usage changes.
| IaaS_Invoice_Detail     | True    | --no-reconciliation    | is a table of all line items expected to appear on the monthly Infrastructure as a Service invoice as a line item.  (Items with the same INV_PRODID have been grouped together and will appear as one line item and need to be manually summed to match invoice. )
| Classic_IaaS_combined   | True    | --no-reconciliation    |is a table of all the Classic Infrastructure Charges combined into one line item on the monthly invoice, the total should match one of the two remaining line items. 
| Classic_COS_Detail      | False   | --cosdetail            | is a table of detailed usage from Classic Cloud Object Storage.  Detail is provided for awareness, but will not appear on invoice.
| Platform_Invoice_Detail | True    | --no-reconciliation    | is a table of all the Platform as a Service charges appearing on the  "Platform as a Service" invoice.  (Items with the same INV_PRODID have been grouped together and will appear as one line item and need to be manually summed to match invoice. )
| StoragePivot            | False   | --storage              | A Table of all Block and File Storage allocations by location with custom notes (if used)

Methodology for reconciliation
1. First Look at the IaaS_Invoice_Detail.  These are the line items that should be broken out on the monthly Infrastructure as a Service Invoice.   Items with the same INV_PRODID will appear as one line item.  If correct you should be able to match all but two line items on invoice.
2. Next look at the Classic_IaaS_combined tab, this is a breakdown of all the Classic Infrastructure Charges combined into one line item on the monthly invoice, the total should match one of the two remaining line items.  Detail is provided for awareness, but will not appear on invoice.
3. Next look at the Classic_COS_Custom tab, this is a breakdown of the custom charges for Classic Object Storage.  On the monthly invoice  This total should match the remaining line item.  Detail is provided for awareness, but will not appear on invoice.
4. Last look at the Platform_Invoice_Detail tab,  this is a breakdown of all the Platform as a Service charges appearing on the second monthly invoice as "Platform as a Service"   The lines items should match this invoice.  Items with the same INV_PRODID will appear as one line item.

***Caveats***
   - Items with the same INV_PRODID will appear as one line item on the invoice.   For most services this correlates to one usage metric, but several services combine metrics under on INV_PRODID and these will need to be summed on the ***IaaS_Invoice_Detail*** tab manually to match the line item on the invoice.
   - If on the ***IaaS_Invoice_Detail*** tab you can't find a corresponding line item on the invoice (other than the items mentioned in step 1) it's likley that it was included with the ***Classic_IaaS_combined*** or vice-versa.

   ***example:*** to provide the 3 latest months of detail
   ```bazaar
   $ export IC_API_KEY=<ibm cloud apikey>
   $ python invoiceAnalysis.py -m 3 --type2
   ```

## Script Execution Instructions

1. Install required packages. 
````
$ pip install -r requirements.txt
````
2. For Internal IBM IMS users who wish to use internal credentials (with Yubikey 2FA) you must manually uninstall the Public SoftLayer SDK and manually 
build the internal SDK for this script to function properly.  Additionally, while executing script you must be connected securely via Global Protect VPN 
to IMS while running reports and will be prompted for your 2FA yubikey at execution time.   [Internal SDK & Instructions](https://github.ibm.com/SoftLayer/internal-softlayer-cli)
```azure
$ pip uninstall SoftLayer
$ git clone https://github.ibm.com/SoftLayer/internal-softlayer-cli
$ cd internal-softlayer-cli
$ python setup.py install
$ ./islcli login

```
3. Set environment variables which can be used.  IBM COS only required if file needs to be written to COS, otherwise file will be written locally.

| Parameter           | Environment Variable | Default               | Description                   
|---------------------|----------------------|-----------------------|-------------------------------
| --IC_API_KEY, -k    | IC_API_KEY           | None                  | IBM Cloud API Key to be used to retrieve invoices and usage. 
| --username          | ims_username         | None                  | Required only if using internal authorization (used instead of IC_API_KEY) 
| --password          | ims_password         | None                  | Required only if using internal authorization (used instead of IC_API_KEY) 
| --account           | ims_account          | None                  | Required only if using internal authorization to specify IMS account to pull. 
| --STARTDATE, -s     | startdate            | None                  | Start Month in YYYY-MM format 
| --ENDDATE, -e       | enddate              | None                  | End Month in YYYY-MM format   
| --months, -m        | months               | None                  | Number of months including last full month to include in report. (use instead of -s/-e) 
| --COS_APIKEY        | COS_APIKEY           | None                  | COS API to be used to write output file to object storage, if not specified file written locally. 
| --COS_BUCKET        | COS_BUCKET           | None                  | COS Bucket to be used to write output file to. 
| --COS_ENDPOINT      | COS_ENDPOINT         | None                  | COS Endpoint to be used to write output file to. 
| --OS_INSTANCE_CRN   | COS_INSTANCE_CRN     | None                  | COS Instance CRN to be used to write output file to. 
| --sendGridApi       | sendGridApi          | None                  | SendGrid API key to use to send Email. 
| --sendGridTo        | sendGridTo           | None                  | SendGrid comma delimited list of email addresses to send output report to. 
| --sendGridFrom      | sendGridFrom         | None                  | SendGrid from email addresss to send output report from. 
| --sendGridSubject   | sendGridSubject      | None                  | SendGrid email subject.       
| --OUTPUT            | OUTPUT               | invoice-analysis.xlsx | Output file name used.        
| --SL_PRIVATE        |                      | --no_SL_PRIVATE       | Whether to use Public or Private Endpoint. 
| --type2             |                      | --no_type2            | Specify Type 2 output, if not specified defaults to Type 1 
| --storage           |                      | --no_storage          | Whether to write additional level of classic Block & File storage analysis to worksheet (default: False) 
| --no-summary        |                      | --summary             | Whether to write summary detail tabs to worksheet. (default: True)
| --no-detail         |                      | --detail              | Whether to Write detail tabs to worksheet. (default: True)
| --no-reconciliation |                      | --reconciliation      | Whether to write invoice reconciliation tabs to worksheet. (default: True)
| --no-serverdetail   |                      | --serverdetail        | Whether to write server detail tabs to worksheet (default: True)
| --cosdetail         |                      | --no-cosdetail        | Whether to write Classic OBject Storage tab to worksheet (default: False)

3. Run Python script (Python 3.9+ required).</br>
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

### Estimating IBM Cloud Usage Month To Date

```bazaar
export IC_API_KEY=<ibm cloud apikey>
python estimateCloudUsage.py

usage: estimateCloudUsage.py [-h] [-k apikey][--output OUTPUT]

Estimate Platform as a Service Usage.

optional arguments:
  -h, --help            show this help message and exit
  -k apikey, --IC_API_KEY apikey
                        IBM Cloud API Key

  --output OUTPUT       Filename Excel output file. (including extension of .xlsx)
```
### Output Description for estimateCloudUsage.py
Note this shows current month usage only.  For SLIC/CFTS invoices, this actual usage from IBM Cloud will be consolidated onto the classic RECURRING invoice
one month later, and be invoiced on the SLIC/CFTS invoice at the end of that month.  (i.e. April Usage, appears on the June 1st RECURRING invoice, and will
appear on the end of June SLIC/CFTS invoice)  Additionally in most cases for SLIC accounts, discounts are applied at the time the data is fed to the RECURRING
invoice.  Other words the USAGE charges are generally list price, but eppear on the Portal RECURRING invoice at their discounted rate.
*Excel Tab Explanation*
   - ***Detail*** is a table of all month to date usage for billable metrics for each platform service.   Each row contains a unique service, resource, and metric with the rated usage and cost, and the resulting cost for discounted items.
   - ***PaaS_Summary*** is a pibot table showing the month to date estimated cost for each PaaS service.
   - ***PaaS_Metric_Summary*** is a pivot table showing the month to date usage and cost for each metric for each service instance and plan.


## Running IBM Cloud Classic Infrastructure Invoice Analysis Report as a Code Engine Job (CloudAPIKey required)

### Setting up IBM Code Engine and building container to run report
1. Create project, build job and job.  
   1.1. Open the Code Engine console.  
   1.2. Select Start creating from Start from source code.  
   1.3. Select Job  
   1.4. Enter a name for the job such as invoiceanalysis. Use a name for your job that is unique within the project.  
   1.5. Select a project from the list of available projects of if this is the first one, create a new one. Note that you must have a selected project to deploy an app.  
   1.6. Enter the URL for this GitHub repository and click specify build details. Make adjustments if needed to URL and Branch name. Click Next.  
   1.7. Select Dockerfile for Strategy, Dockerfile for Dockerfile, 10m for Timeout, and Medium for Build resources. Click Next.  
   1.8. Select a container registry location, such as IBM Registry, Dallas.  
   1.9. Select Automatic for Registry access.  
   1.10. Select an existing namespace or enter a name for a new one, for example, newnamespace. 
   1.11. Enter a name for your image and optionally a tag.  
   1.12. Click Done.  
   1.13. Click Create.  
2. Create configmaps and secrets.  
   2.1. From project list, choose newly created project.  
   2.2. Select secrets and configmaps  
   2.3. click create, choose config map, and give it a name. Add the following key value pairs    
        ***COS_BUCKET*** = Bucket within COS instance to write report file to.  
        ***COS_ENDPOINT*** = Public COS Endpoint for bucket to write report file to  
        ***COS_INSTANCE_CRN*** = COS Service Instance CRN in which bucket is located.  
   2.4. Select secrets and configmaps (again)
   2.5.  click create, choose secrets, and give it a name. Add the following key value pairs  
         ***IC_API_KEY*** = an IBM Cloud API Key with Billing access to IBM Cloud Account  
         ***COS_APIKEY*** = your COS Api Key Id with writter access to appropriate bucket  
3. Choose the job previously created.  
   3.1. Click on the Environment variables tab.   
   3.2. Click add, choose reference to full configmap, and choose configmap created in previous step and click add.  
   3.3. Click add, choose reference to full secret, and choose secrets created in previous step and click add.  
   3.4 .Click add, choose literal value (click add after each, and repeat)  
         ***startdate*** = start year & month of invoice analysis in YYYY-MM format  
         ***enddate*** = end year & month invoice analysis in YYYY-MM format  
         ***output*** = report filename (including extension of XLSX to be written to COS bucket)  
4. to Run report click ***Submit job***  
5. Logging for job can be found from job screen, by clicking Actions, Logging