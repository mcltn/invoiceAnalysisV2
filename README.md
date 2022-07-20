# IBM Cloud Classic Infrastructure Invoice Analysis Report
*invoiceAnalysis.py* collects IBM Cloud Classic Infrastructure NEW, RECURRING, and CREDIT invoices and PaaS Usage between months specified in the parameters consolidates the data into an Excel worksheet for billing and usage analysis. 
In addition to consolidation of the detailed data,  pivot tables are created in Excel tabs to assist with understanding account usage.

### Required Files
Script | Description
------ | -----------
invoiceAnalysis.py | Export usage detail by invoice month to an Excel file for all IBM Cloud Classic invoices and PaaS Consumption.
requirements.txt | Package requirements
logging.json | LOGGER config used by script
Dockerfile | Docker Build file used by code engine to build container.


### Identity & Access Management Requirements
| APIKEY | Description | Min Access Permissions
| ------ | ----------- | ----------------------
| IBM Cloud API Key | API Key used to pull classic and PaaS invoices and Usage Reports. | IAM Billing Viewer Role
| COS API Key | API Key used to write output to specified bucket (if specified) | COS Bucket Write access to Bucket at specified Object Storage CRN.


### Output Description
One Excel worksheet is created with multiple tabs from the collected data (Classic Invoices & PaaS Usage between start and end month specified).   _Tabs are only be created if there are related resources on the collected invoices._

*Excel Tab Explanation*
   - ***Detail*** is a table of every invoice item (Parent and children) for all the collected invoices represented as one row each.  All invoice types are included, including CREDIT invoices.  The detail tab can be sorted or filtered to find specific dates, billing item id's, or specific services.  
   - ***InvoiceSummary*** is a table of all charges by product group and category for each month by invoice type. This tab can be used to understand changes in month-to-month usage.
   - ***CategorySummary*** is a table  of all charges by product group, category, and description (for example specific VSI sizes or Bare metal server types) to dig deeper into month to month usage changes.
   - ***IaaS_Invoice_Detail*** is a table of all line items expected to appear on the monthly Infrastructure as a Service invoice as a line item.  (Items with the same INV_PRODID have been grouped together and will appear as one line item and need to be manually summed to match invoice. )
   - ***Classic_IaaS_combined*** is a table of all the Classic Infrastructure Charges combined into one line item on the monthly invoice, the total should match one of the two remaining line items. 
   - ***Classic_COS_Custom*** is a table of the custom charges for Classic Object Storage.  Detail is provided for awareness, but will not appear on invoice.
   - ***Platform_Invoice_Detail*** is a table of all the Platform as a Service charges appearing on the  "Platform as a Service" invoice.  (Items with the same INV_PRODID have been grouped together and will appear as one line item and need to be manually summed to match invoice. )

### Reconciliation Approach
1. First Look at the IaaS_Invoice_Detail.  These are the line items that should be broken out on the monthly Infrastructure as a Service Invoice.   Items with the same INV_PRODID will appear as one line item.  If correct you should be able to match all but two line items on invoice.
2. Next look at the Classic_IaaS_combined tab, this is a breakdown of all the Classic Infrastructure Charges combined into one line item on the monthly invoice, the total should match one of the two remaining line items.  Detail is provided for awareness, but will not appear on invoice.
3. Next look at the Classic_COS_Custom tab, this is a breakdown of the custom charges for Classic Object Storage.  On the monthly invoice  This total should match the remaining line item.  Detail is provided for awareness, but will not appear on invoice.
4. Last look at the Platform_Invoice_Detail tab,  this is a breakdown of all the Platform as a Service charges appearing on the second monthly invoice as "Platform as a Service"   The lines items should match this invoice.  Items with the same INV_PRODID will appear as one line item.


## Script Execution Instructions: _See alternate instructions for Code Engine._

1. Install required packages.  
````
pip install -r requirements.txt
````
2. Set environment variables which can be used.  IBM COS only required if file needs to be written to COS, otherwise file will be written locally.

|Parameter | Environment Variable | Default | Description
|--------- | -------------------- | ------- | -----------
|--IC_API_KEY, -k | IC_API_KEY | None | IBM Cloud API Key to be used to retrieve invoices and usage.
|--STARTDATE, -s | startdate | None | Start Month in YYYY-MM format
|--ENDDATE, -e | enddate | None | End Month in YYYY-MM format
|--months, -m | months | None | Number of months including last full month to include in report. (use instead of -s/-e)
|--COS_APIKEY | COS_APIKEY | None | COS API to be used to write output file to object storage, if not specified file written locally.
|--COS_BUCKET | COS_BUCKET | None | COS Bucket to be used to write output file to.
|--COS_ENDPOINT | COS_ENDPOINT| None | COS Endpoint to be used to write output file to.
|--OS_INSTANCE_CRN | COS_INSTANCE_CRN | None | COS Instance CRN to be used to write output file to.
|--sendGridApi | sendGridApi | None | SendGrid API key to use to send Email.
|--sendGridTo | sendGridTo | None | SendGrid comma delimited list of email addresses to send output report to.
|--sendGridFrom | sendGridFrom | None | SendGrid from email addresss to send output report from.
|--sendGridSubject | sendGridSubject | None | SendGrid email subject.
|--OUTPUT | OUTPUT | invoice-analysis.xlsx | Output file name used.
|--SL_PRIVATE,--no_SL_PRIVATE | | --no_SL_PRIVATE | Whether to use Public or Private Endpoint.

3. Run Python script (Python 3.9 required).</br>

```bazaar
export IC_API_KEY=<ibm cloud apikey>
python invoiceAnalysis.py -s 2021-01 -e 2021-06
```

```bazaar
usage: invoiceAnalysis.py [-h] [-k apikey] [-s YYYY-MM] [-e YYYY-MM] [-m MONTHS] [--COS_APIKEY COS_APIKEY] [--COS_ENDPOINT COS_ENDPOINT] [--COS_INSTANCE_CRN COS_INSTANCE_CRN] [--COS_BUCKET COS_BUCKET] [--sendGridApi SENDGRIDAPI]      ─╯
                          [--sendGridTo SENDGRIDTO] [--sendGridFrom SENDGRIDFROM] [--sendGridSubject SENDGRIDSUBJECT] [--output OUTPUT] [--SL_PRIVATE | --no-SL_PRIVATE]

Export usage detail by invoice month to an Excel file for all IBM Cloud Classic invoices and PaaS Consumption.

optional arguments:
  -h, --help            show this help message and exit
  -k apikey, --IC_API_KEY apikey
                        IBM Cloud API Key
  -s YYYY-MM, --startdate YYYY-MM
                        Start Year & Month in format YYYY-MM
  -e YYYY-MM, --enddate YYYY-MM
                        End Year & Month in format YYYY-MM
  -m MONTHS, --months MONTHS
                        Number of months including last full month to include in report.

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


```

## Running IBM Cloud Classic Infrastructure Invoice Analysis Report as a Code Engine Job

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
