# Other IBM Cloud Included Scripts

## Table of Contents
1. Identity and Access Management Requirements
2. estimatedCloudUsage.py 
3. ibmCloudUsage.py
4. classicConfigAnalysis.py
5. classicConfigReport.py

### Identity & Access Management Requirements
| APIKEY                                     | Description                                                     | Min Access Permissions
|--------------------------------------------|-----------------------------------------------------------------|----------------------
| IBM Cloud API Key                          | API Key used access classic invoices & IBM Cloud Usage          | IAM Billing Viewer Role


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
