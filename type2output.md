# Type 2 Format (--type2)

new experimental output format which is less common. but breaks out SLIC invoice line item detail by each product code.  To generate this output specify --type2 on command line.

### Detail Tabs
| Tab Name      | Default | flag to change default| Description of Tab 
|---------------|---------|----------------------|-------------------
| Detail | True | --no-detail | Detailed list of every invoice line item (including chidlren line items) from all invoices types between date range specified.

### Monthly Invoice Tabs
One tab is created for each month in range specified and used for reconciliation against invoices.   Only required tabs are created.  (ie if no credit in a month, then no credit tab will be created)

| Tab Name      | Default | flag to change default| Description of Tab 
|---------------|---------|----------------------|-------------------
| IaaS_YYYY-MM  | True | --no-reconcilliation | Table matching each portal invoice's IaaS and PaaS Charges. Grouped by Product or INV_PRODID.  These amounts should match the SLIC/CFTS invoice amounts and aid in reconciliation. 
| PaaS_YYYY-MM  | True | --no-reconcilliation | Table matching portal PaaS COS charges on RECURRING invoice PaaS for that month, which are included in that months SLIC/CFTS invoice.  PaaS Charges are typically consolidated into one amount for type1, though the detail is provided at a service level on this tab to faciliate reconcillation.  PaaS charges are for usage 2 months in arrears. 
| Credit-YYYY-MM |  True | --no-reconcilliation | Table of Credit Invoics to their corresponding IBM SLIC/CFTS invoice(s). 

### Summary Tabs
Tabs are created to summarize usage data based on SLIC invoice month.   If a range of months is specified, months are displayed as columns in each tab and can be used to compare month to month changes

| Tab Name                | Default | flag to change default | Description of Tab 
|-------------------------|---------|------------------------|-------------------
| CategoryGroupSummary    | True    | --no-summary          | A pivot table of all charges shown by Invoice Type and Category Groups by month. 
| CategoryDetail          | True    | --no-summary          | A pivot table of all charges by Invoice Type, Category Group, Category and specific service Detail by month.
| Classic_COS_Detail      | False   | --cosdetail            | is a table of detailed usage from Classic Cloud Object Storage.  Detail is provided for awareness, but will not appear on invoice.
| StoragePivot            | False   | --storage              | A Table of all Block and File Storage allocations by location with custom notes (if used)

Methodology for reconciliation
1. First Look at the IaaS_YYYY-MM.  These are the line items that should be broken out on the monthly Infrastructure as a Service Invoice.   Items with the same INV_PRODID or a Classic Infrastructure will appear as one line item.  If correct you should be able to match all but two line items on invoice.
2. Next look at the PaaS_YYYY=MM.   These are the PaaS COS line items.    The lines items should match this invoice.  Items with the same INV_PRODID will appear as one line item on the invoice.
3. Any credits will appear on the Credit-YYYY-MM tab.

***Caveats***
   - Items with the same INV_PRODID will appear as one line item on the invoice.   For most services this correlates to one usage metric, but several services combine metrics under on INV_PRODID and these will need to be summed on the ***IaaS_Invoice_Detail*** tab manually to match the line item on the invoice.
   - If on the ***IaaS_Invoice_Detail*** tab you can't find a corresponding line item on the invoice (other than the items mentioned in step 1) it's likley that it was included with the ***Classic_IaaS_combined*** or vice-versa.

   ***example:*** to provide the 3 latest months of detail
   ```bazaar
   $ export IC_API_KEY=<ibm cloud apikey>
   $ python invoiceAnalysis.py -m 3 --type2
   ```