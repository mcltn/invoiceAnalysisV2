#!/usr/bin/env python3
# Author: Jon Hall
# Copyright (c) 2022
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


__author__ = 'jonhall'
import SoftLayer, os, logging, logging.config, json, calendar, os.path, argparse, base64, re, urllib
import pandas as pd
import numpy as np
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Mail, Personalization, Email, Attachment, FileContent, FileName,
    FileType, Disposition, ContentId)
from datetime import datetime, tzinfo, timezone
from dateutil import tz
from calendar import monthrange
from dateutil.relativedelta import relativedelta
import ibm_boto3
from ibm_botocore.client import Config, ClientError
from dotenv import load_dotenv
def setup_logging(default_path='logging.json', default_level=logging.info, env_key='LOG_CFG'):
    # read logging.json for log parameters to be ued by script
    path = default_path
    value = os.getenv(env_key, None)
    if value:
        path = value
    if os.path.exists(path):
        with open(path, 'rt') as f:
            config = json.load(f)
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=default_level)

def getDescription(categoryCode, detail):
    # retrieve additional description detail for child records
    for item in detail:
        if 'categoryCode' in item:
            if item['categoryCode'] == categoryCode:
                return item['product']['description'].strip()
    return ""

def getStorageServiceUsage(categoryCode, detail):
    # retrieve storage details for description text
    for item in detail:
        if 'categoryCode' in item:
            if item['categoryCode'] == categoryCode:
                return item['description'].strip()
    return ""

def getCFTSInvoiceDate(invoiceDate):
    # Determine CFTS Invoice Month (20th of prev month - 19th of current month) are on current month CFTS invoice.
    if invoiceDate.day > 19:
        invoiceDate = invoiceDate + relativedelta(months=1)
    return invoiceDate.strftime('%Y-%m')

def getInvoiceDates(startdate,enddate):
    # Adjust start and dates to match CFTS Invoice cutoffs of 20th to end of day 19th 00:00 Dallas time on the 20th
    dallas = tz.gettz('US/Central')
    startdate = datetime(int(startdate[0:4]),int(startdate[5:7]),20,0,0,0,tzinfo=dallas) - relativedelta(months=1)
    enddate = datetime(int(enddate[0:4]),int(enddate[5:7]),20,0,0,0,tzinfo=dallas)
    return startdate, enddate

def createEmployeeClient(end_point_employee, employee_user, passw, token):
    """Creates a softlayer-python client that can make API requests for a given employee_user"""
    client_noauth = SoftLayer.Client(endpoint_url=end_point_employee)
    client_noauth.auth = None
    employee = client_noauth['SoftLayer_User_Employee']
    result = employee.performExternalAuthentication(employee_user, passw, token)
    # Save result['hash'] somewhere to not have to login for every API request
    client_employee = SoftLayer.employee_client(username=employee_user, access_token=result['hash'], endpoint_url=end_point_employee)
    return client_employee

def getInvoiceList(startdate, enddate):
    # GET LIST OF PORTAL INVOICES BETWEEN DATES USING CENTRAL (DALLAS) TIME
    dallas=tz.gettz('US/Central')
    logging.info("Looking up invoices from {} to {}.".format(startdate.strftime("%m/%d/%Y %H:%M:%S%z"), enddate.strftime("%m/%d/%Y %H:%M:%S%z")))
    # filter invoices based on local dallas time that correspond to CFTS UTC cutoff
    logging.debug("invoiceList startDate: {}".format(startdate.astimezone(dallas).strftime("%m/%d/%Y %H:%M:%S")))
    logging.debug("invoiceList endDate: {}".format(enddate.astimezone(dallas).strftime("%m/%d/%Y %H:%M:%S")))
    try:
        invoiceList = client['Account'].getInvoices(id=ims_account, mask='id,createDate,typeCode,invoiceTotalAmount,invoiceTotalRecurringAmount,invoiceTopLevelItemCount', filter={
                'invoices': {
                    'createDate': {
                        'operation': 'betweenDate',
                        'options': [
                             {'name': 'startDate', 'value': [startdate.astimezone(dallas).strftime("%m/%d/%Y %H:%M:%S")]},
                             {'name': 'endDate', 'value': [enddate.astimezone(dallas).strftime("%m/%d/%Y %H:%M:%S")]}
                        ]
                    }
                }
        })
    except SoftLayer.SoftLayerAPIError as e:
        logging.error("Account::getInvoices: %s, %s" % (e.faultCode, e.faultString))
        quit()
    logging.debug("getInvoiceList account {}: {}".format(ims_account,invoiceList))
    return invoiceList

def parseChildren(row, parentDescription, children):
    """
    Parse Children Record if requested
    """
    global data

    for child in children:
        logging.debug(child)
        if float(child["recurringFee"]) > 0:
            row['RecordType'] = "Child"
            row["childBillingItemId"] = child["billingItemId"]
            row['childParentProduct'] = parentDescription
            if "itemCategory" in child["product"]:
                row["Category"] = child["product"]["itemCategory"]["name"]
            else:
                row["Category"] = "Unknown"
            if "group" in child["category"]:
                row["Category_Group"] = child["category"]["group"]["name"]
            else:
                row["Category_group"] = child['category']['name']
            if row["Category_Group"] == "StorageLayer":
                desc = child["description"].find(":")
                if desc == -1:
                    row["Description"] = child["description"]
                    row["childUsage"] = ""
                else:
                    # Parse usage details from child description for StorageLayer
                    row["Description"] = child["description"][0:desc]
                    if child["description"].find("API Requests") != -1:
                        row['childUsage'] = float(re.search("\d+", child["description"][desc:]).group())
                    elif child["description"].find("Snapshot Space") != -1:
                            row['childUsage'] = float(re.search("\d+", child["description"][desc:]).group())
                    elif child["description"].find("Replication for tier") != -1:
                            row['childUsage'] = 0
                    else:
                            row['childUsage'] = float(re.search("\d+([\.,]\d+)", child["description"][desc:]).group())
            else:
                desc = child["description"].find("- $")
                if desc == -1:
                    row["Description"] = child["description"]
                    row["childUsage"] = ""
                else:
                    # Parse usage details from child description
                    row["Description"] = child["description"][0:desc]
                    row['childUsage'] = re.search("([\d.]+)\s+(\S+)", child["description"][desc:]).group()
                    row['childUsage'] = float(row['childUsage'][0:row['childUsage'].find("Usage") - 3])
            row["totalRecurringCharge"] = 0
            row["childTotalRecurringCharge"] = round(float(child["recurringFee"]), 3)

            # Get product attributes for PaaS Product Code and DIV
            row["INV_PRODID"] = ""
            row["INV_DIV"] = ""
            if "attributes" in child["product"]:
                for attr in child["product"]["attributes"]:
                    if attr["attributeType"]["keyName"] == "BLUEMIX_PART_NUMBER":
                        row["INV_PRODID"] = attr["value"]
                    if attr["attributeType"]["keyName"] == "BLUEMIX_SERVICE_PLAN_DIVISION":
                        row["INV_DIV"] = attr["value"]

            # write child record
            data.append(row.copy())
            logging.info("child {} {} {} RecurringFee: {}".format(row["childBillingItemId"], row["INV_PRODID"], row["Description"],
                                                               row["childTotalRecurringCharge"]))
            logging.debug(row)
    return

def getAccountNetworkStorage():
    """
    Build Dataframe with accounts current network storage
    """
    logging.info("Getting details on existing Network Storage in account.")
    try:
        networkStorage = client['Account'].getNetworkStorage(id=ims_account, mask="id, createDate, capacityGb, nasType, notes, username, provisionedIops, billingItem.id")
    except Exception as e:
        logging.error("Account::getNetworkStorage {}, {}".format(e.faultCode, e.faultString))
        quit()

    storage_df = pd.DataFrame(columns=[
                               'id',
                               'billingItemId',
                               'createDate',
                               'capacityGb',
                               'nasType',
                               'notes',
                               'username',
                               'provisionedIops',
                               'iopsTier',
                               ])
    for item in networkStorage:
        if 'billingItem' in item:
            if 'id' in item['billingItem']:
                billingItemId = item['billingItem']['id']
            else:
                billingItemId = ""
        else:
            billingItemId = ""

        if 'createDate' in item:
            createDate = item['createDate']
        else:
            createDate = ""

        if 'capacityGb' in item:
            capacityGb = item['capacityGb']
        else:
            capacityGb = ""

        if 'nasType' in item:
            nasType = item['nasType']
        else:
            nasType = ""

        if 'notes' in item:
            notes = urllib.parse.unquote(item['notes'])
        else:
            notes = ""

        if 'username' in item:
            username = item['username']
        else:
            username = ""

        if 'provisionedIops' in item:
            provisionedIops = item['provisionedIops']
            if float(capacityGb) > 0:
                iopsTier = round(float(provisionedIops)/float(capacityGb),0)
            else:
                iopsTier = ""
        else:
            provisionedIops = ""
            iopsTier = ""

        row = pd.DataFrame({
                            'id': [item['id']],
                            'billingItemId': [billingItemId],
                            'createDate': [createDate],
                            'capacityGb': [capacityGb],
                            'nasType': [nasType],
                            'notes': [notes],
                            'username': [username],
                            'provisionedIops': [provisionedIops],
                            'iopsTier': [iopsTier]
                            })

        storage_df = pd.concat([storage_df, row], ignore_index=True)

    return storage_df

def getInvoiceDetail(startdate, enddate):
    """
    Read invoice top level detail from range of invoices
    """
    global client, data, networkStorageDF
    # Create dataframe to work with for classic infrastructure invoices
    data = []

    dallas = tz.gettz('US/Central')

    # get list of invoices between start month and endmonth
    invoiceList = getInvoiceList(startdate, enddate)

    if invoiceList == None:
        return invoiceList

    for invoice in invoiceList:
        if (float(invoice['invoiceTotalAmount']) == 0) and (float(invoice['invoiceTotalRecurringAmount']) == 0):
            continue

        invoiceID = invoice['id']
        # To align to CFTS billing cutoffs display time in Dallas timezone.
        invoiceDate = datetime.strptime(invoice['createDate'], "%Y-%m-%dT%H:%M:%S%z").astimezone(dallas)
        invoiceTotalAmount = float(invoice['invoiceTotalAmount'])
        CFTSInvoiceDate = getCFTSInvoiceDate(invoiceDate)

        invoiceTotalRecurringAmount = float(invoice['invoiceTotalRecurringAmount'])
        invoiceType = invoice['typeCode']
        recurringDesc = ""
        if invoiceType == "NEW":
            serviceDateStart = invoiceDate
            # get last day of month
            serviceDateEnd= serviceDateStart.replace(day=calendar.monthrange(serviceDateStart.year,serviceDateStart.month)[1])

        if invoiceType == "CREDIT" or invoiceType == "ONE-TIME-CHARGE":
            serviceDateStart = invoiceDate
            serviceDateEnd = invoiceDate

        totalItems = invoice['invoiceTopLevelItemCount']

        # PRINT INVOICE SUMMARY LINE
        logging.info('Invoice: {} Date: {} Type:{} Items: {} Amount: ${:,.2f}'.format(invoiceID, datetime.strftime(invoiceDate, "%Y-%m-%d"), invoiceType, totalItems, invoiceTotalRecurringAmount))

        limit = 75 ## set limit of record returned
        for offset in range(0, totalItems, limit):
            if ( totalItems - offset - limit ) < 0:
                remaining = totalItems - offset
            logging.info("Retrieving %s invoice line items for Invoice %s at Offset %s of %s" % (limit, invoiceID, offset, totalItems))

            try:
                """
                       if --storage specified on command line provide
                       additional mapping of current storage comments to billing
                       records billingItem.resourceTableId is link to storage.
                       note: user must have classic Infrastructure access for storage components
                """
                if storageFlag:
                    Billing_Invoice = client['Billing_Invoice'].getInvoiceTopLevelItems(id=invoiceID, limit=limit, offset=offset,
                                        mask="id, billingItemId,categoryCode,category,category.group, hourlyFlag,hostName,domainName,location,notes,product.description,product.taxCategory,billingItem.resourceTableId," \
                                             "createDate,totalRecurringAmount,totalOneTimeAmount,usageChargeFlag,hourlyRecurringFee,children.billingItemId,children.description,children.category.group," \
                                             "children.categoryCode,children.product,children.product.taxCategory,children.product.attributes,children.product.attributes.attributeType,children.recurringFee")
                else:
                    Billing_Invoice = client['Billing_Invoice'].getInvoiceTopLevelItems(id=invoiceID, limit=limit, offset=offset,
                                        mask="id, billingItemId,categoryCode,category,category.group, hourlyFlag,hostName,domainName,location,notes,product.description,product.taxCategory," \
                                             "createDate,totalRecurringAmount,totalOneTimeAmount,usageChargeFlag,hourlyRecurringFee,children.billingItemId,children.description,children.category.group," \
                                             "children.categoryCode,children.product,children.product.taxCategory,children.product.attributes,children.product.attributes.attributeType,children.recurringFee")
            except SoftLayer.SoftLayerAPIError as e:
                logging.error("Billing_Invoice::getInvoiceTopLevelItems: %s, %s" % (e.faultCode, e.faultString))
                quit()
            count = 0
            # ITERATE THROUGH DETAIL
            for item in Billing_Invoice:
                logging.debug(item)
                totalOneTimeAmount = float(item['totalOneTimeAmount'])
                billingItemId = item['billingItemId']
                if "group" in item["category"]:
                    categoryGroup = item["category"]["group"]["name"]
                else:
                    categoryGroup = "Other"
                category = item["categoryCode"]
                categoryName = item["category"]["name"]
                taxCategory = item['product']['taxCategory']['name']
                description = item['product']['description']
                memory = getDescription("ram", item["children"])
                os = getDescription("os", item["children"])

                if 'notes' in item:
                    billing_notes = item["notes"]
                else:
                    billing_notes = ""

                if 'location' in item:
                    location = item["location"]["longName"]
                else:
                    location = ""

                if 'hostName' in item:
                    if 'domainName' in item:
                        hostName = item['hostName']+"."+item['domainName']
                    else:
                        hostName = item['hostName']
                else:
                    hostName = ""

                recurringFee = float(item['totalRecurringAmount'])
                NewEstimatedMonthly = 0

                # If Hourly calculate hourly rate and total hours
                if item["hourlyFlag"]:
                    # if hourly charges are previous month usage
                    serviceDateStart = invoiceDate - relativedelta(months=1)
                    serviceDateEnd = serviceDateStart.replace(day=calendar.monthrange(serviceDateStart.year, serviceDateStart.month)[1])
                    recurringDesc = "IaaS Usage"
                    hourlyRecurringFee = 0
                    hours = 0
                    if "hourlyRecurringFee" in item:
                        if float(item["hourlyRecurringFee"]) > 0:
                            hourlyRecurringFee = float(item['hourlyRecurringFee'])
                            for child in item["children"]:
                                if "hourlyRecurringFee" in child:
                                    hourlyRecurringFee = hourlyRecurringFee + float(child['hourlyRecurringFee'])
                            hours = round(float(recurringFee) / hourlyRecurringFee)            # Not an hourly billing item
                else:
                    if taxCategory == "PaaS":
                        # Non Hourly PaaS Usage from actual usage two months prior
                        serviceDateStart = invoiceDate - relativedelta(months=2)
                        serviceDateEnd = serviceDateStart.replace(day=calendar.monthrange(serviceDateStart.year, serviceDateStart.month)[1])
                        recurringDesc = "Platform Service Usage"
                    elif taxCategory == "IaaS":
                        if invoiceType == "RECURRING":
                            serviceDateStart = invoiceDate
                            serviceDateEnd = serviceDateStart.replace(day=calendar.monthrange(serviceDateStart.year, serviceDateStart.month)[1])
                            recurringDesc = "IaaS Monthly"
                    elif taxCategory == "HELP DESK":
                        serviceDateStart = invoiceDate
                        serviceDateEnd = serviceDateStart.replace(
                            day=calendar.monthrange(serviceDateStart.year, serviceDateStart.month)[1])
                        recurringDesc = "Support Charges"
                    hourlyRecurringFee = 0
                    hours = 0

                # if storage flag specified, lookup existing note from object stored in dataframe
                if storageFlag and (category == "storage_service_enterprise" or category == "performance_storage_iops" or category == "storage_as_a_service"):
                    if "resourceTableId" in item["billingItem"]:
                        resourceTableId = item["billingItem"]["resourceTableId"]
                        result = networkStorageDF.query('id == @resourceTableId')
                        if len(result) > 0:
                            storage_notes = result['notes'].values[0]
                        else:
                            storage_notes = "Volume Deleted."
                else:
                    storage_notes = ""

                if category == "storage_service_enterprise":
                    iops = getDescription("storage_tier_level", item["children"])
                    storage = getDescription("performance_storage_space", item["children"])
                    snapshot = getDescription("storage_snapshot_space", item["children"])
                    if snapshot == "":
                        description = storage + " " + iops + " "
                    else:
                        description = storage+" " + iops + " with " + snapshot
                elif category == "performance_storage_iops":
                    iops = getDescription("performance_storage_iops", item["children"])
                    storage = getDescription("performance_storage_space", item["children"])
                    description = storage + " " + iops
                elif category == "storage_as_a_service":
                    if item["hourlyFlag"]:
                        model = "Hourly"
                        for child in item["children"]:
                            if "hourlyRecurringFee" in child:
                                hourlyRecurringFee = hourlyRecurringFee + float(child['hourlyRecurringFee'])
                        if hourlyRecurringFee > 0:
                            hours = round(float(recurringFee) / hourlyRecurringFee)
                        else:
                            hours = 0
                    else:
                        model = "Monthly"
                    space = getStorageServiceUsage('performance_storage_space', item["children"])
                    tier = getDescription("storage_tier_level", item["children"])
                    snapshot = getDescription("storage_snapshot_space", item["children"])
                    if space == "" or tier == "":
                        description = model + " File Storage"
                    else:
                        if snapshot == "":
                            description = model + " File Storage " + space + " at " + tier
                        else:
                            snapshotspace = getStorageServiceUsage('storage_snapshot_space', item["children"])
                            description = model + " File Storage " + space + " at " + tier + " with " + snapshotspace
                elif category == "guest_storage":
                        imagestorage = getStorageServiceUsage("guest_storage_usage", item["children"])
                        if imagestorage == "":
                            description = description.replace('\n', " ")
                        else:
                            description = imagestorage
                else:
                    description = description.replace('\n', " ")


                if invoiceType == "NEW":
                    # calculate non pro-rated amount for use in forecast
                    daysInMonth = monthrange(invoiceDate.year, invoiceDate.month)[1]
                    daysLeft = daysInMonth - invoiceDate.day + 1
                    dailyAmount = recurringFee / daysLeft
                    NewEstimatedMonthly = dailyAmount * daysInMonth

                recordType = "Parent"

                # Append record to dataframe
                row = {'Portal_Invoice_Date': invoiceDate.strftime("%Y-%m-%d"),
                       'Portal_Invoice_Time': invoiceDate.strftime("%H:%M:%S%z"),
                       'Service_Date_Start': serviceDateStart.strftime("%Y-%m-%d"),
                       'Service_Date_End': serviceDateEnd.strftime("%Y-%m-%d"),
                       'IBM_Invoice_Month': CFTSInvoiceDate,
                       'Portal_Invoice_Number': invoiceID,
                       'RecordType': recordType,
                       'BillingItemId': billingItemId,
                       'hostName': hostName,
                       'location': location,
                       'billing_notes': billing_notes,
                       'Category_Group': categoryGroup,
                       'Category': categoryName,
                       'TaxCategory': taxCategory,
                       'Description': description,
                       'Memory': memory,
                       'OS': os,
                       'Hourly': item["hourlyFlag"],
                       'Usage': item["usageChargeFlag"],
                       'Hours': hours,
                       'HourlyRate': round(hourlyRecurringFee,5),
                       'totalRecurringCharge': round(recurringFee,3),
                       'totalOneTimeAmount': float(totalOneTimeAmount),
                       'NewEstimatedMonthly': float(NewEstimatedMonthly),
                       'InvoiceTotal': float(invoiceTotalAmount),
                       'InvoiceRecurring': float(invoiceTotalRecurringAmount),
                       'Type': invoiceType,
                       'Recurring_Description': recurringDesc,
                       'childTotalRecurringCharge': 0
                        }
                if storageFlag:
                    row["storage_notes"] = storage_notes


                # write parent record
                data.append(row.copy())
                logging.info("parent {} {} RecurringFee: {}".format(row["BillingItemId"], row["Description"],row["totalRecurringCharge"]))
                logging.debug(row)

                if len(item["children"]) > 0:
                    parseChildren(row, description, item["children"])

    columns = ['Portal_Invoice_Date',
               'Portal_Invoice_Time',
               'Service_Date_Start',
               'Service_Date_End',
               'IBM_Invoice_Month',
               'Portal_Invoice_Number',
               'Type',
               'RecordType',
               'BillingItemId',
               'hostName',
               'location',
               'Category_Group',
               'Category',
               'TaxCategory',
               'Description',
               'Memory',
               'OS',
               'billing_notes',
               'Hourly',
               'Usage',
               'Hours',
               'HourlyRate',
               'totalRecurringCharge',
               'NewEstimatedMonthly',
               'totalOneTimeAmount',
               'InvoiceTotal',
               'InvoiceRecurring',
               'Recurring_Description',
               'childBillingItemId',
               'childParentProduct',
               'childUsage',
               'childTotalRecurringCharge',
               'INV_PRODID',
               'INV_DIV']
    if storageFlag:
        columns.append("storage_notes")

    df = pd.DataFrame(data, columns=columns)

    return df

def createType1Report(filename, classicUsage):
    """
    Type 1 Output meets the majority of SLIC account setup.
    Break out of invoice data is based on a traditional IaaS vs PaaS view.
    IaaS Top Sheet Detail is split by all classic Infrastructure broken out by IMS Invoice, with splits for VMware Licensing, Classic Object Storage, and all other IaaS
    PaaS Top Sheet Detail is atches the definition of IMS as any usage billed through IMS from DSW.  Additional detail is provided to assist in reconcilation

    Command-line Flags can be set to control which tabs are created
    """

    def createDetailTab(classicUsage):
        """
        Write detail tab to excel
        """
        logging.info("Creating detail tab.")
        classicUsage.to_excel(writer, 'Detail')
        usdollar = workbook.add_format({'num_format': '$#,##0.00'})
        format2 = workbook.add_format({'align': 'left'})
        worksheet = writer.sheets['Detail']
        worksheet.set_column('Q:AA', 18, usdollar)
        worksheet.set_column('AB:AB', 18, format2)
        worksheet.set_column('AC:AC', 18, usdollar)
        worksheet.set_column('W:W', 18, format2)
        totalrows, totalcols = classicUsage.shape
        worksheet.autofilter(0, 0, totalrows, totalcols)
        return

    def createIaasTopSheet(classicUsage):
        """
        Break out for CFTS type 1 detail for IaaS.  This covers accounts with single billing work number
        where the IaaS detail (NEW & RECURRING) broken out by cloud services vs VMware License
        Charges (both OS & VCS)
        """
        months = classicUsage.IBM_Invoice_Month.unique()
        for i in months:
            logging.info("Creating IaaS CFTS Invoice Top Sheet tab for {}.".format(i))

            """
            Start by Parsing NEW & ONE TIME & RECURRING IaaS Charges and split by COS, VMware, and all other IaaS Charges
            """
            allcharges = classicUsage.query(
                'IBM_Invoice_Month == @i and (Type == "NEW" or Type == "ONE-TIME-CHARGE" or Type == "RECURRING") and (TaxCategory == "IaaS" or TaxCategory == "HELP DESK")').copy()

            # Build Dataframe of VMWARE Licenses
            vmwareSoftware = allcharges.query(
                'RecordType == "Parent" and Category_Group == "Software" and Category == "Software License"').copy()
            vmwareSoftware["Invoice_Line_Item_Description"] = "VMware Licensing"

            # Build Dataframe of metered OS VMware Licenses (from children records)
            vmwareOS = allcharges.query('RecordType == "Child" and Category == "Operating System"').loc[
                allcharges["OS"].str.contains("VMware")]
            vmwareOS["Invoice_Line_Item_Description"] = "VMware Licensing"

            # Build Dataframe of all Classic Objet Storage line items
            objectStorage = allcharges.query(
                'RecordType == "Parent" and Category_Group == "StorageLayer" and Category == "Object Storage"').copy()
            objectStorage["Invoice_Line_Item_Description"] = "Classic Cloud Object Storage Usage"

            # combine dataframes into one new dataframe
            iaas = pd.concat([vmwareSoftware, vmwareOS, objectStorage])
            iaas["invoiceAmount"] = (
                        iaas["totalRecurringCharge"] + iaas["childTotalRecurringCharge"] + iaas["totalOneTimeAmount"])

            # exclude Object Storage and VMware Offering LIcense Fees
            iaasRemaining = allcharges.query(
                'RecordType == "Parent" and Category != "Object Storage" and Category != "Software License"').copy()

            # Remove VMware OS licenses from server total recurring cost, as it's included in the above line item.
            for index, row in iaasRemaining.iterrows():
                if row["RecordType"] == "Parent" and row["Category"] == "Server":
                    # get corresponding child record and subtract OS license
                    billingItemId = row["BillingItemId"]
                    invoiceId = row["Portal_Invoice_Number"]
                    os = vmwareOS.query('BillingItemId == @billingItemId and Portal_Invoice_Number == @invoiceId')
                    logging.debug("os: {}".format(os))
                    if len(os) > 0:
                        serverCost = row["totalRecurringCharge"]
                        osCost = os["childTotalRecurringCharge"]
                        logging.debug("row:{}".format(row))
                        iaasRemaining.at[index, 'totalRecurringCharge'] = float(serverCost) - float(osCost)

            iaasRemaining["invoiceAmount"] = (iaasRemaining["totalRecurringCharge"] + iaasRemaining["totalOneTimeAmount"])
            iaasRemaining["Invoice_Line_Item_Description"] = "Infrastructure-as-a-Service Other"

            """
            Build new dataframe for VMware + COS
            """
            table1 = iaas.groupby(["Type",
                                   "Portal_Invoice_Number",
                                   "Portal_Invoice_Date",
                                   "Service_Date_Start",
                                   "Service_Date_End",
                                   'IBM_Invoice_Month',
                                   "Invoice_Line_Item_Description", "Category", "Description"
                                   ])["invoiceAmount"].sum().reset_index()

            # build table for other
            table2 = iaasRemaining.groupby(["Type",
                                            "Portal_Invoice_Number",
                                            "Portal_Invoice_Date",
                                            "Service_Date_Start",
                                            "Service_Date_End",
                                            "IBM_Invoice_Month",
                                            "Invoice_Line_Item_Description", "Category", "Description"
                                            ])["invoiceAmount"].sum().reset_index()

            lineitems = pd.concat([table1, table2])

            """
            Build pivot tab for the line items on the IaaS Invoice.
            Summary Tab has line items to match CFTS invoice
            Detail Tab has additional level of detail to help reconcile
            """

            iaasInvoice = pd.pivot_table(lineitems, index=["Portal_Invoice_Number", "Type", "Portal_Invoice_Date",
                                                           "Invoice_Line_Item_Description"],
                                         values=["invoiceAmount"],
                                         aggfunc=np.sum, margins=True, margins_name="Total",
                                         fill_value=0)

            iaasInvoice.to_excel(writer, 'IaaS_{}'.format(i))
            worksheet = writer.sheets['IaaS_{}'.format(i)]
            format1 = workbook.add_format({'num_format': '$#,##0.00'})
            format2 = workbook.add_format({'align': 'left'})
            worksheet.set_column("A:A", 20, format2)
            worksheet.set_column("B:C", 25, format2)
            worksheet.set_column("D:D", 50, format2)
            worksheet.set_column("E:ZZ", 18, format1)

            iaasInvoiceDetail = pd.pivot_table(lineitems, index=["Type", "Portal_Invoice_Number", "Portal_Invoice_Date", "Service_Date_Start",
                                                                  "Service_Date_End","Invoice_Line_Item_Description", "Category"],
                                               values=["invoiceAmount"],
                                               aggfunc=np.sum, margins=True, margins_name="Total",
                                               fill_value=0)

            iaasInvoiceDetail.to_excel(writer, 'IaaS_Detail_{}'.format(i))
            worksheet = writer.sheets['IaaS_Detail_{}'.format(i)]
            format1 = workbook.add_format({'num_format': '$#,##0.00'})
            format2 = workbook.add_format({'align': 'left'})
            worksheet.set_column("A:E", 20, format2)
            worksheet.set_column("F:F", 40, format2)
            worksheet.set_column("G:G", 40, format2)
            worksheet.set_column("H:ZZ", 18, format1)
        return

    def createPaasTopSheet(classicUsage):
        """
        Build a pivot table of items that typically show on CFTS invoice at child level
        """
        paasCodes = ["D01J5ZX", "D01J6ZX", "D01J7ZX", "D01J8ZX", "D01J9ZX", "D01JAZX", "D01JBZX", "D01NGZX", "D01NHZX",
                     "D01NIZX", "D01NJZX", "D022FZX", "D1VCRLL", "D1VCSLL",
                     "D1VCTLL", "D1VCULL", "D1VCVLL", "D1VCWLL", "D1VCXLL", "D1VCYLL", "D1VCZLL", "D1VD0LL", "D1VD1LL",
                     "D1VD2LL", "D1VD3LL", "D1VD4LL", "D1VD5LL", "D1VD6LL",
                     "D1VD7LL", "D1VD8LL", "D1VD9LL", "D1VDALL", "D1YJMLL", "D20Y7LL"]

        months = classicUsage.IBM_Invoice_Month.unique()
        for i in months:
            logging.info("Creating PaaS Invoice Top Sheet Tab for {}.".format(i))
            childRecords = classicUsage.query(
                'IBM_Invoice_Month == @i and RecordType == ["Child"] and INV_PRODID != [""] ')

            if len(childRecords) > 0:
                childSummary = pd.pivot_table(childRecords,
                                              index=["Portal_Invoice_Number", "Portal_Invoice_Date",  "Service_Date_Start",
                                                    "Service_Date_End", "INV_PRODID", "childParentProduct"],
                                              values=["childTotalRecurringCharge"],
                                              aggfunc={'childTotalRecurringCharge': np.sum}, margins=True,
                                              margins_name="Total", fill_value=0)

                childSummary.to_excel(writer, 'PaaS_{}'.format(i))
                worksheet = writer.sheets['PaaS_{}'.format(i)]
                format1 = workbook.add_format({'num_format': '$#,##0.00'})
                format2 = workbook.add_format({'align': 'left'})
                worksheet.set_column("A:E", 20, format2)
                worksheet.set_column("F:F", 50, format2)
                worksheet.set_column("G:ZZ", 18, format1)
        return
    
    def createCreditTopSheet(classicUsage):
        """
        Build a pivot table Credit Invoices
        """
        months = classicUsage.IBM_Invoice_Month.unique()
        for i in months:
            creditItems = classicUsage.query('IBM_Invoice_Month == @i and Type == "CREDIT"')

            if len(creditItems) > 0:
                logging.info("Creating Credit Invoice Tab for {}.".format(i))
                pivot = pd.pivot_table(creditItems, index=["Portal_Invoice_Number", "Type", "Portal_Invoice_Date"],
                                             values=["totalAmount"],
                                             aggfunc=np.sum, margins=True, margins_name="Total",
                                             fill_value=0)
                pivot.to_excel(writer, 'Credit_{}'.format(i))
                worksheet = writer.sheets['Credit_{}'.format(i)]
                format1 = workbook.add_format({'num_format': '$#,##0.00'})
                format2 = workbook.add_format({'align': 'left'})
                worksheet.set_column("A:C", 20, format2)
                worksheet.set_column("D:ZZ", 18, format1)
        return

    def createCategoryGroup(classicUsage):
        """
        Create General SUmmary Tab by Category_Group of NEW, RECURRING, and ONE_TIME CHARGES appearing
        on monthly Invoice
        """
        logging.info("Creating Category Group Summary Tab.")
        parentRecords = classicUsage.query('RecordType == ["Parent"]')
        invoiceSummary = pd.pivot_table(parentRecords, index=["Type", "Category_Group", "Category"],
                                        values=["totalAmount"],
                                        columns=['IBM_Invoice_Month'],
                                        aggfunc={'totalAmount': np.sum, }, margins=True, margins_name="Total",
                                        fill_value=0). \
            rename(columns={'totalRecurringCharge': 'TotalRecurring'})
        invoiceSummary.to_excel(writer, 'CategoryGroupSummary')
        worksheet = writer.sheets['CategoryGroupSummary']
        format1 = workbook.add_format({'num_format': '$#,##0.00'})
        format2 = workbook.add_format({'align': 'left'})
        worksheet.set_column("A:A", 20, format2)
        worksheet.set_column("B:B", 40, format2)
        worksheet.set_column("C:ZZ", 18, format1)
        return

    def createCategoryDetail(classicUsage):
        """
        Build a pivot table by Category with totalRecurringCharges
        tab name CategorySummary
        """

        logging.info("Creating Category Detail Tab.")
        parentRecords = classicUsage.query('RecordType == ["Parent"]')
        categorySummary = pd.pivot_table(parentRecords, index=["Type", "Category_Group", "Category", "Description"],
                                         values=["totalAmount"],
                                         columns=['IBM_Invoice_Month'],
                                         aggfunc={'totalAmount': np.sum}, margins=True, margins_name="Total",
                                         fill_value=0)
        categorySummary.to_excel(writer, 'CategoryDetail')
        worksheet = writer.sheets['CategoryDetail']
        format1 = workbook.add_format({'num_format': '$#,##0.00'})
        format2 = workbook.add_format({'align': 'left'})
        worksheet.set_column("A:A", 20, format2)
        worksheet.set_column("B:D", 40, format2)
        worksheet.set_column("E:ZZ", 18, format1)
        return

    def createClassicCOS(classicUsage):
        """
        Build a pivot table of Classic Object Storage
        """
        logging.info("Creating Classic Object Storage Detail Tab.")
        iaasscosRecords = classicUsage.query(
            'RecordType == ["Child"] and childParentProduct == ["Cloud Object Storage - S3 API"]')
        if len(iaasscosRecords) > 0:
            logging.info("Creating Classic_COS_Detail Tab.")
            iaascosSummary = pd.pivot_table(iaasscosRecords,
                                            index=["Type", "Category_Group", "childParentProduct", "Category",
                                                   "Description"],
                                            values=["childTotalRecurringCharge"],
                                            columns=['IBM_Invoice_Month'],
                                            aggfunc={'childTotalRecurringCharge': np.sum}, fill_value=0,
                                            margins=True, margins_name="Total")
            iaascosSummary.to_excel(writer, 'Classic_COS_Detail')
            worksheet = writer.sheets['Classic_COS_Detail']
            format1 = workbook.add_format({'num_format': '$#,##0.00'})
            format2 = workbook.add_format({'align': 'left'})
            worksheet.set_column("A:A", 20, format2)
            worksheet.set_column("B:E", 40, format2)
            worksheet.set_column("F:ZZ", 18, format1)
        return

    def createPaaSInvoiceDetail(classicUsage):
        """
        Build a pivot table of PaaS object storage
        """

        logging.info("Creating PaaS_COS_Detail Tab.")
        paasCodes = ["D01J5ZX", "D01J6ZX", "D01J7ZX", "D01J8ZX", "D01J9ZX", "D01JAZX", "D01JBZX", "D01NGZX", "D01NHZX",
                     "D01NIZX", "D01NJZX", "D022FZX", "D1VCRLL", "D1VCSLL",
                     "D1VCTLL", "D1VCULL", "D1VCVLL", "D1VCWLL", "D1VCXLL", "D1VCYLL", "D1VCZLL", "D1VD0LL", "D1VD1LL",
                     "D1VD2LL", "D1VD3LL", "D1VD4LL", "D1VD5LL", "D1VD6LL",
                     "D1VD7LL", "D1VD8LL", "D1VD9LL", "D1VDALL", "D1YJMLL", "D20Y7LL"]

        paascosRecords = classicUsage.query('RecordType == ["Child"] and INV_PRODID in @paasCodes')
        if len(paascosRecords) > 0:
            paascosSummary = pd.pivot_table(paascosRecords, index=["INV_PRODID", "childParentProduct", "Description"],
                                            values=["childTotalRecurringCharge"],
                                            aggfunc={'childTotalRecurringCharge': np.sum}, fill_value=0, margins=True,
                                            margins_name="Total")
            paascosSummary.to_excel(writer, 'PaaS_Invoice_Detail')
            worksheet = writer.sheets['PaaS_Invoice_Detail']
            format1 = workbook.add_format({'num_format': '$#,##0.00'})
            format2 = workbook.add_format({'align': 'left'})
            worksheet.set_column("A:A", 20, format2)
            worksheet.set_column("B:B", 40, format2)
            worksheet.set_column("C:C", 60, format2)
            worksheet.set_column("D:ZZ", 18, format1)
        return

    def createHourlyVirtualServers(classicUsage):
        """
        Build a pivot table for Hourly VSI's with totalRecurringCharges
        """
        virtualServers = classicUsage.query('Category == ["Computing Instance"] and Hourly == [True]')
        if len(virtualServers) > 0:
            logging.info("Creating Hourly VSI Tab.")
            virtualServerPivot = pd.pivot_table(virtualServers, index=["Description", "OS"],
                                                values=["Hours", "totalRecurringCharge"],
                                                columns=['IBM_Invoice_Month'],
                                                aggfunc={'Description': len, 'Hours': np.sum,
                                                         'totalRecurringCharge': np.sum}, fill_value=0). \
                rename(columns={"Description": 'qty', 'Hours': 'Total Hours', 'totalRecurringCharge': 'TotalRecurring'})

            virtualServerPivot.to_excel(writer, 'HrlyVirtualServers')
            format_leftjustify = workbook.add_format()
            format_leftjustify.set_align('left')
            worksheet = writer.sheets['HrlyVirtualServers']
            worksheet.set_column('A:B', 40, format_leftjustify)

        return

    def createMonthlyVirtualServers(classicUsage):
        """
        Build a pivot table for Monthly VSI's with totalRecurringCharges
        """
        monthlyVirtualServers = classicUsage.query('Category == ["Computing Instance"] and Hourly == [False]')
        if len(monthlyVirtualServers) > 0:
            logging.info("Creating Monthly VSI Tab.")
            virtualServerPivot = pd.pivot_table(monthlyVirtualServers, index=["Description", "OS"],
                                                values=["totalRecurringCharge"],
                                                columns=['IBM_Invoice_Month'],
                                                aggfunc={'Description': len, 'totalRecurringCharge': np.sum},
                                                fill_value=0). \
                rename(columns={"Description": 'qty', 'totalRecurringCharge': 'TotalRecurring'})
            virtualServerPivot.to_excel(writer, 'MnthlyVirtualServers')
            format_leftjustify = workbook.add_format()
            format_leftjustify.set_align('left')
            worksheet = writer.sheets['MnthlyVirtualServers']
            worksheet.set_column('A:B', 40, format_leftjustify)
        return

    def createHourlyBareMetalServers(classicUsage):
        """
        Build a pivot table for Hourly Bare Metal with totalRecurringCharges
        """
        bareMetalServers = classicUsage.query('Category == ["Server"]and Hourly == [True]')
        if len(bareMetalServers) > 0:
            logging.info("Creating Hourly Bare Metal Tab.")
            pivot = pd.pivot_table(bareMetalServers, index=["Description", "OS"],
                                   values=["Hours", "totalRecurringCharge"],
                                   columns=['IBM_Invoice_Month'],
                                   aggfunc={'Description': len, 'totalRecurringCharge': np.sum}, fill_value=0). \
                rename(columns={"Description": 'qty', 'Hours': np.sum, 'totalRecurringCharge': 'TotalRecurring'})
            pivot.to_excel(writer, 'HrlyBaremetalServers')
            format_leftjustify = workbook.add_format()
            format_leftjustify.set_align('left')
            worksheet = writer.sheets['HrlyBaremetalServers']
            worksheet.set_column('A:B', 40, format_leftjustify)
        return

    def createMonthlyBareMetalServers(classicUsage):
        """
        Build a pivot table for Monthly Bare Metal with totalRecurringCharges
        """
        monthlyBareMetalServers = classicUsage.query('Category == ["Server"] and Hourly == [False]')
        if len(monthlyBareMetalServers) > 0:
            logging.info("Creating Monthly Bare Metal Tab.")
            pivot = pd.pivot_table(monthlyBareMetalServers, index=["Description", "OS"],
                                   values=["totalRecurringCharge"],
                                   columns=['IBM_Invoice_Month'],
                                   aggfunc={'Description': len, 'totalRecurringCharge': np.sum}, fill_value=0). \
                rename(columns={"Description": 'qty', 'totalRecurringCharge': 'TotalRecurring'})
            pivot.to_excel(writer, 'MthlyBaremetalServers')
            format_leftjustify = workbook.add_format()
            format_leftjustify.set_align('left')
            worksheet = writer.sheets['MthlyBaremetalServers']
            worksheet.set_column('A:B', 40, format_leftjustify)
        return

    def createStorageTab(classicUsage):
        """
        Build a pivot table for Storage as a Service by Volume Name
        """

        storage = classicUsage.query(
            'Category == ["Storage As A Service"] or Category == ["Endurance"] and Type == ["RECURRING"]')

        if len(storage) > 0:
            logging.info("Creating Storage Detail Tab.")
            format_usdollar = workbook.add_format({'num_format': '$#,##0.00'})
            format_leftjustify = workbook.add_format()
            format_leftjustify.set_align('left')
            st = pd.pivot_table(storage,
                                index=["location", "Category", "billing_notes", "storage_notes", "Description"],
                                values=["totalRecurringCharge"],
                                columns=['IBM_Invoice_Month'],
                                aggfunc={'totalRecurringCharge': np.sum}, fill_value=0).rename(
                columns={'totalRecurringCharge': 'TotalRecurring'})

            """
            Create Storage-as-a-Service Tab
            """
            if st is not None:
                st.to_excel(writer, 'StoragePivot')
                worksheet = writer.sheets['StoragePivot']
                worksheet.set_column("A:C", 30, format_leftjustify)
                worksheet.set_column("D:D", 50, format_leftjustify)
                worksheet.set_column("E:ZZ", 18, format_usdollar)

        return

    """
    Create Pivots and write to Excel using xlswriter.
    """
    writer = pd.ExcelWriter(filename, engine='xlsxwriter')
    workbook = writer.book
    logging.info("Creating {}.".format(filename))

    # combine one time amounts and total recurring charge in datafrane
    classicUsage["totalAmount"] = classicUsage["totalOneTimeAmount"] + classicUsage["totalRecurringCharge"] + classicUsage["childTotalRecurringCharge"]

    """
    Create each tab in Excel Worksheet
    """
    if len(classicUsage) > 0:
        if detailFlag:
            createDetailTab(classicUsage)
        """
        Create IaaS, PaaS, and Credit Top Sheets to match
        each month's CFTS invoices generated
        """
        if reconciliationFlag:
            createIaasTopSheet(classicUsage)
            createPaasTopSheet(classicUsage)
            createCreditTopSheet(classicUsage)

        """
        Create additional Summary Usage and Category Detail
        """
        if summaryFlag:
            createCategoryGroup(classicUsage)
            createCategoryDetail(classicUsage)

        if cosdetailFlag:
            createClassicCOS(classicUsage)

        if serverDetailFlag:
            createHourlyVirtualServers(classicUsage)
            createMonthlyVirtualServers(classicUsage)
            createHourlyBareMetalServers(classicUsage)
            createMonthlyBareMetalServers(classicUsage)

        """
        if --storage specified on command line provide
        additional mapping of current storage comments to billing
        records
        """
        if storageFlag:
            createStorageTab(classicUsage)
    writer.close()
    return

def createType2Report(filename, classicUsage):

    """
    Type 2 Output meets the setup of SLIC accounts who have manual billing and/or multiple worknumbers.
    Break out of invoice data is based on "D Code" offering detail.
    The IaaS_Invoice_Detail.  Items with the same INV_PRODID will appear as a single item on the CFTS invoice.
    The Classic_IaaS_combined tab will breakout all the Classic Infrastructure Charges which do not have a "D Code", these will be combined into one line item on the CFTS invoice.
    Both of these tabs will appear on the CFTS Infrastructure as a Service Invoice (including those which are normally though of as PaaS)
    Platform_Invoice_Detail tab will show the PaaS CFTS charges,  currently this is only PaaS Cloud Object Storage (Not classic Cloud Object Storage)
    """

    def createDetailTab(classicUsage):
        """
        Write detail tab to excel
        """
        logging.info("Creating detail tab.")
        classicUsage.to_excel(writer, 'Detail')
        usdollar = workbook.add_format({'num_format': '$#,##0.00'})
        format2 = workbook.add_format({'align': 'left'})
        worksheet = writer.sheets['Detail']
        worksheet.set_column('Q:AA', 18, usdollar)
        worksheet.set_column('AB:AB', 18, format2)
        worksheet.set_column('AC:AC', 18, usdollar)
        worksheet.set_column('W:W', 18, format2 )
        totalrows,totalcols=classicUsage.shape
        worksheet.autofilter(0,0,totalrows,totalcols)
        return
    
    def createInvoiceSummary(classicUsage):
        """
        Map Portal Invoices to SLIC Invoices / Create Top Sheet per SLIC month
        """
    
        if len(classicUsage)>0:
            logging.info("Creating InvoiceSummary Tab.")
            parentRecords= classicUsage.query('RecordType == ["Parent"]')
            invoiceSummary = pd.pivot_table(parentRecords, index=["Type", "Category_Group", "Category"],
                                            values=["totalAmount"],
                                            columns=['IBM_Invoice_Month'],
                                            aggfunc={'totalAmount': np.sum,}, margins=True, margins_name="Total", fill_value=0).\
                                            rename(columns={'totalRecurringCharge': 'TotalRecurring'})
            invoiceSummary.to_excel(writer, 'InvoiceSummary')
            worksheet = writer.sheets['InvoiceSummary']
            format1 = workbook.add_format({'num_format': '$#,##0.00'})
            format2 = workbook.add_format({'align': 'left'})
            worksheet.set_column("A:A", 20, format2)
            worksheet.set_column("B:B", 40, format2)
            worksheet.set_column("C:ZZ", 18, format1)
        return
    
    def createCategoorySummary(classicUsage):
        """
        Build a pivot table by Category with totalRecurringCharges
        tab name CategorySummary
        """
    
        if len(classicUsage) > 0:
            logging.info("Creating CategorySummary Tab.")
            parentRecords = classicUsage.query('RecordType == ["Parent"]')
            categorySummary = pd.pivot_table(parentRecords, index=["Type", "Category_Group", "Category", "Description"],
                                             values=["totalAmount"],
                                             columns=['IBM_Invoice_Month'],
                                             aggfunc={'totalAmount': np.sum}, margins=True, margins_name="Total", fill_value=0)
            categorySummary.to_excel(writer, 'CategorySummary')
            worksheet = writer.sheets['CategorySummary']
            format1 = workbook.add_format({'num_format': '$#,##0.00'})
            format2 = workbook.add_format({'align': 'left'})
            worksheet.set_column("A:A", 20, format2)
            worksheet.set_column("B:D", 40, format2)
            worksheet.set_column("E:ZZ", 18, format1)
        return
    
    def createClassicCombined(classicUsage):
        """
        Build a pivot table for items that show on CFTS IaaS charges not included in the PaaS children detail
        """
    
        if len(classicUsage) > 0:
            logging.info("Creating IaaS_Line_item_Detail Tab.")
            # VPC Storage now seperate line item as of July 2022
            iaasRecords = classicUsage.query('(RecordType == ["Child"] and TaxCategory == ["PaaS"] and INV_PRODID == [""]) or (RecordType == ["Parent"] and (TaxCategory == ["IaaS"] or TaxCategory == ["HELP DESK"]))')
    
            iaasSummary = pd.pivot_table(iaasRecords, index=["Type", "Category_Group", "Category", "Description"],
                                             values=["totalAmount"],
                                             columns=['IBM_Invoice_Month'],
                                             aggfunc={'totalAmount': np.sum}, margins=True, margins_name="Total", fill_value=0)
            iaasSummary.to_excel(writer, 'Classic_IaaS_Combined')
            worksheet = writer.sheets['Classic_IaaS_Combined']
            format1 = workbook.add_format({'num_format': '$#,##0.00'})
            format2 = workbook.add_format({'align': 'left'})
            worksheet.set_column("A:A", 20, format2)
            worksheet.set_column("B:D", 40, format2)
            worksheet.set_column("E:ZZ", 18, format1)
        return
    
    def createClassicCOS(classicUsage):
        """
        Build a pivot table of Classic Object Storage that displays charges appearing on CFTS invoice
        """
        if len(classicUsage) > 0:
            iaascosRecords = classicUsage.query('RecordType == ["Child"] and childParentProduct == ["Cloud Object Storage - S3 API"]')
            if len(iaascosRecords) > 0:
                logging.info("Creating Classic_COS_Detail Tab.")
                iaascosSummary = pd.pivot_table(iaascosRecords, index=["Type", "Category_Group", "childParentProduct", "Category", "Description"],
                                                 values=["childTotalRecurringCharge"],
                                                 columns=['IBM_Invoice_Month'],
                                                 aggfunc={'childTotalRecurringCharge': np.sum}, fill_value=0, margins=True, margins_name="Total")
                iaascosSummary.to_excel(writer, 'Classic_COS_Detail')
                worksheet = writer.sheets['Classic_COS_Detail']
                format1 = workbook.add_format({'num_format': '$#,##0.00'})
                format2 = workbook.add_format({'align': 'left'})
                worksheet.set_column("A:A", 20, format2)
                worksheet.set_column("B:E", 40, format2)
                worksheet.set_column("F:ZZ", 18, format1)
        return
    
    def createPaaSInvoiceDetail(classicUsage):
        """
        Build a pivot table of PaaS object storage
        """
    
        logging.info("Creating PaaS_COS_Detail Tab.")
        paasCodes = ["D01J5ZX","D01J6ZX","D01J7ZX","D01J8ZX","D01J9ZX","D01JAZX","D01JBZX","D01NGZX","D01NHZX","D01NIZX","D01NJZX","D022FZX","D1VCRLL","D1VCSLL",
                     "D1VCTLL","D1VCULL","D1VCVLL","D1VCWLL","D1VCXLL","D1VCYLL","D1VCZLL","D1VD0LL","D1VD1LL","D1VD2LL","D1VD3LL","D1VD4LL","D1VD5LL","D1VD6LL",
                     "D1VD7LL","D1VD8LL","D1VD9LL","D1VDALL","D1YJMLL","D20Y7LL"]
    
        paascosRecords = classicUsage.query('RecordType == ["Child"] and INV_PRODID in @paasCodes')
        if len(paascosRecords) > 0:
            paascosSummary = pd.pivot_table(paascosRecords, index=["INV_PRODID", "childParentProduct", "Description"],
                                             values=["childTotalRecurringCharge"],
                                             columns=['IBM_Invoice_Month'],
                                             aggfunc={'childTotalRecurringCharge': np.sum}, fill_value=0, margins=True, margins_name="Total")
            paascosSummary.to_excel(writer, 'PaaS_Invoice_Detail')
            worksheet = writer.sheets['PaaS_Invoice_Detail']
            format1 = workbook.add_format({'num_format': '$#,##0.00'})
            format2 = workbook.add_format({'align': 'left'})
            worksheet.set_column("A:A", 20, format2)
            worksheet.set_column("B:B", 40, format2)
            worksheet.set_column("C:C", 60, format2)
            worksheet.set_column("D:ZZ", 18, format1)
        return
    
    def createIaaSInvoiceDetail(classicUsage):
        """
        Build a pivot table of items that typically show on CFTS invoice at child level
        """
        paasCodes = ["D01J5ZX", "D01J6ZX", "D01J7ZX", "D01J8ZX", "D01J9ZX", "D01JAZX", "D01JBZX", "D01NGZX", "D01NHZX",
                     "D01NIZX", "D01NJZX", "D022FZX", "D1VCRLL", "D1VCSLL",
                     "D1VCTLL", "D1VCULL", "D1VCVLL", "D1VCWLL", "D1VCXLL", "D1VCYLL", "D1VCZLL", "D1VD0LL", "D1VD1LL",
                     "D1VD2LL", "D1VD3LL", "D1VD4LL", "D1VD5LL", "D1VD6LL",
                     "D1VD7LL", "D1VD8LL", "D1VD9LL", "D1VDALL", "D1YJMLL", "D20Y7LL"]
    
        # D1VG4LL = VPC Block which is no it's own line item starting July 2022
    
        logging.info("Creating Platform Detail Tab.")
        childRecords = classicUsage.query('RecordType == ["Child"] and INV_PRODID != [""] and INV_PRODID not in @paasCodes')
        if len(childRecords) > 0:
            childSummary = pd.pivot_table(childRecords, index=["INV_PRODID", "childParentProduct", "Description"],
                                             values=["childTotalRecurringCharge"],
                                             columns=['IBM_Invoice_Month'],
                                             aggfunc={'childTotalRecurringCharge': np.sum}, margins=True,  margins_name="Total", fill_value=0)
    
            childSummary.to_excel(writer, 'IaaS_Invoice_Detail')
            worksheet = writer.sheets['IaaS_Invoice_Detail']
            format1 = workbook.add_format({'num_format': '$#,##0.00'})
            format2 = workbook.add_format({'align': 'left'})
            worksheet.set_column("A:A", 20, format2)
            worksheet.set_column("B:B", 50, format2)
            worksheet.set_column("C:C", 70, format2)
            worksheet.set_column("D:ZZ", 18, format1)
        return

    def createStorageTab(classicUsage):
        """
        Build a pivot table for Storage as a Service by Volume Name
        """

        storage = classicUsage.query(
            'Category == ["Storage As A Service"] or Category == ["Endurance"] and Type == ["RECURRING"]')

        if len(storage) > 0:
            logging.info("Creating Storage Detail Tab.")
            format_usdollar = workbook.add_format({'num_format': '$#,##0.00'})
            format_leftjustify = workbook.add_format()
            format_leftjustify.set_align('left')
            st = pd.pivot_table(storage,
                                index=["location", "Category", "billing_notes", "storage_notes", "Description"],
                                values=["totalRecurringCharge"],
                                columns=['IBM_Invoice_Month'],
                                aggfunc={'totalRecurringCharge': np.sum}, fill_value=0).rename(
                columns={'totalRecurringCharge': 'TotalRecurring'})

            """
            Create Storage-as-a-Service Tab
            """
            if st is not None:
                st.to_excel(writer, 'StoragePivot')
                worksheet = writer.sheets['StoragePivot']
                worksheet.set_column("A:C", 30, format_leftjustify)
                worksheet.set_column("D:D", 50, format_leftjustify)
                worksheet.set_column("E:ZZ", 18, format_usdollar)

        return

    global writer, workbook

    # Write dataframe to excel
    writer = pd.ExcelWriter(filename, engine='xlsxwriter')
    workbook = writer.book
    logging.info("Creating {}.".format(filename))

    # combine one time amounts and total recurring charge in datafrane
    classicUsage["totalAmount"] = classicUsage["totalOneTimeAmount"] + classicUsage["totalRecurringCharge"] + classicUsage["childTotalRecurringCharge"]

    # create pivots for various tabs for Type2 SLIC based on flags
    if detailFlag:
        createDetailTab(classicUsage)

    if summaryFlag:
        createInvoiceSummary(classicUsage)
        createCategoorySummary(classicUsage)

    if reconciliationFlag:
        createIaaSInvoiceDetail(classicUsage)
        createClassicCombined(classicUsage)
    if cosdetailFlag:
        createClassicCOS(classicUsage)
    if reconciliationFlag:
        createPaaSInvoiceDetail(classicUsage)
    if storageFlag:
        createStorageTab(classicUsage)
    writer.save()
    
def multi_part_upload(bucket_name, item_name, file_path):
    try:
        logging.info("Starting file transfer for {0} to bucket: {1}".format(item_name, bucket_name))
        # set 5 MB chunks
        part_size = 1024 * 1024 * 5

        # set threadhold to 15 MB
        file_threshold = 1024 * 1024 * 15

        # set the transfer threshold and chunk size
        transfer_config = ibm_boto3.s3.transfer.TransferConfig(
            multipart_threshold=file_threshold,
            multipart_chunksize=part_size
        )

        # the upload_fileobj method will automatically execute a multi-part upload
        # in 5 MB chunks for all files over 15 MB
        with open(file_path, "rb") as file_data:
            cos.Object(bucket_name, item_name).upload_fileobj(
                Fileobj=file_data,
                Config=transfer_config
            )
        logging.info("Transfer for {0} complete".format(item_name))
    except ClientError as be:
        logging.error("CLIENT ERROR: {0}".format(be))
    except Exception as e:
        logging.error("Unable to complete multi-part upload: {0}".format(e))
    return

def sendEmail(startdate, enddate, sendGridTo, sendGridFrom, sendGridSubject, sendGridApi, outputname):
    # Send output to email distributionlist via SendGrid

    html = ("<p><b>invoiceAnalysis Output Attached for {} to {} </b></br></p>".format(datetime.strftime(startdate, "%m/%d/%Y"), datetime.strftime(enddate, "%m/%d/%Y")))

    to_list = Personalization()
    for email in sendGridTo.split(","):
        to_list.add_to(Email(email))

    message = Mail(
        from_email=sendGridFrom,
        subject=sendGridSubject,
        html_content=html
    )

    message.add_personalization(to_list)

    # create attachment from file
    file_path = os.path.join("./", outputname)
    with open(file_path, 'rb') as f:
        data = f.read()
        f.close()
    encoded = base64.b64encode(data).decode()
    attachment = Attachment()
    attachment.file_content = FileContent(encoded)
    attachment.file_type = FileType('application/xlsx')
    attachment.file_name = FileName(outputname)
    attachment.disposition = Disposition('attachment')
    attachment.content_id = ContentId('invoiceAnalysis')
    message.attachment = attachment
    try:
        sg = SendGridAPIClient(sendGridApi)
        response = sg.send(message)
        logging.info("Email Send succesfull to {}, status code = {}.".format(sendGridTo,response.status_code))
    except Exception as e:
        logging.error("Email Send Error, status code = %s." % e.to_dict)
    return

if __name__ == "__main__":
    setup_logging()
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Export usage detail by invoice month to an Excel file for all IBM Cloud Classic invoices and corresponding PaaS Consumption.")
    parser.add_argument("-k", default=os.environ.get('IC_API_KEY', None), dest="IC_API_KEY", help="IBM Cloud API Key")
    parser.add_argument("-u", "--username", default=os.environ.get('ims_username', None), metavar="username", help="IBM IMS Userid")
    parser.add_argument("-p", "--password", default=os.environ.get('ims_password', None), metavar="password", help="IBM IMS Password")
    parser.add_argument("-a", "--account", default=os.environ.get('ims_account', None), metavar="account", help="IMS Account")
    parser.add_argument("-s", "--startdate", default=os.environ.get('startdate', None), help="Start Year & Month in format YYYY-MM")
    parser.add_argument("-e", "--enddate", default=os.environ.get('enddate', None), help="End Year & Month in format YYYY-MM")
    parser.add_argument("--months", default=os.environ.get('months', 1), help="Number of months including last full month to include in report.")
    parser.add_argument("--COS_APIKEY", default=os.environ.get('COS_APIKEY', None), help="COS apikey to use for Object Storage.")
    parser.add_argument("--COS_ENDPOINT", default=os.environ.get('COS_ENDPOINT', None), help="COS endpoint to use for Object Storage.")
    parser.add_argument("--COS_INSTANCE_CRN", default=os.environ.get('COS_INSTANCE_CRN', None), help="COS Instance CRN to use for file upload.")
    parser.add_argument("--COS_BUCKET", default=os.environ.get('COS_BUCKET', None), help="COS Bucket name to use for file upload.")
    parser.add_argument("--sendGridApi", default=os.environ.get('sendGridApi', None), help="SendGrid ApiKey used to email output.")
    parser.add_argument("--sendGridTo", default=os.environ.get('sendGridTo', None), help="SendGrid comma deliminated list of emails to send output to.")
    parser.add_argument("--sendGridFrom", default=os.environ.get('sendGridFrom', None), help="Sendgrid from email to send output from.")
    parser.add_argument("--sendGridSubject", default=os.environ.get('sendGridSubject', None), help="SendGrid email subject for output email")
    parser.add_argument("--output", default=os.environ.get('output', 'invoice-analysis.xlsx'), help="Filename Excel output file. (including extension of .xlsx)")
    parser.add_argument("--SL_PRIVATE", default=False, action=argparse.BooleanOptionalAction, help="Use IBM Cloud Classic Private API Endpoint")
    parser.add_argument('--type2', default=False, action=argparse.BooleanOptionalAction, help="Break out detail by 'D codes' consistent with CFTS Sprint process used for multiple work numbers.")
    parser.add_argument('--storage', default=False, action=argparse.BooleanOptionalAction, help="Include File, BLock and Classic Cloud Object Storage detail analysis.")
    parser.add_argument('--detail', default=True, action=argparse.BooleanOptionalAction, help="Whether to Write detail tabs to worksheet.")
    parser.add_argument('--summary', default=True, action=argparse.BooleanOptionalAction, help="Whether to Write summarytabs to worksheet.")
    parser.add_argument('--reconciliation', default=True, action=argparse.BooleanOptionalAction, help="Whether to write invoice reconciliation tabs to worksheet.")
    parser.add_argument('--serverdetail', default=True, action=argparse.BooleanOptionalAction, help="Whether to write server detail tabs to worksheet.")
    parser.add_argument('--cosdetail', default=False, action=argparse.BooleanOptionalAction, help="Whether to write Classic OBject Storage tab to worksheet.")

    args = parser.parse_args()

    """Set Flags to determine which Tabs are created in output"""
    storageFlag = args.storage
    type2Flag = args.type2
    detailFlag = args.detail
    summaryFlag = args.summary
    reconciliationFlag = args.reconciliation
    serverDetailFlag = args.serverdetail
    cosdetailFlag =args.cosdetail

    """
    If no APIKEY set, then check for internal IBM credentials
    NOTE: internal authentication requires internal SDK version & Global Protect VPN.
    """
    if args.IC_API_KEY == None:
        if args.username == None or args.password == None or args.account == None:
            logging.error("You must provide either IBM Cloud ApiKey or Internal Employee credentials & IMS account.")
            quit()
        else:
            if args.username != None or args.password != None or args.account != None:
                logging.info("Using Internal endpoint and employee credentials.")
                ims_username = args.username
                ims_password = args.password
                ims_yubikey = input("Yubi Key:")
                ims_account = args.account
                SL_ENDPOINT = "http://internal.applb.dal10.softlayer.local/v3.1/internal/xmlrpc"
                client = createEmployeeClient(SL_ENDPOINT, ims_username, ims_password, ims_yubikey)
            else:
                logging.error("Error!  Can't find internal credentials or ims account.")
                quit()
    else:
        logging.info("Using IBM Cloud Account API Key.")
        IC_API_KEY = args.IC_API_KEY
        ims_account = None

        # Change endpoint to private Endpoint if command line open chosen
        if args.SL_PRIVATE:
            SL_ENDPOINT = "https://api.service.softlayer.com/xmlrpc/v3.1"
        else:
            SL_ENDPOINT = "https://api.softlayer.com/xmlrpc/v3.1"

        # Create Classic infra API client
        client = SoftLayer.Client(username="apikey", api_key=IC_API_KEY, endpoint_url=SL_ENDPOINT)

    if args.months != None:
        months = int(args.months)
        dallas=tz.gettz('US/Central')
        today=datetime.today().astimezone(dallas)
        if today.day > 19:
            enddate=today.strftime('%Y-%m')
            startdate = today - relativedelta(months=months-1)
            startdate = startdate.strftime("%Y-%m")
        else:
            enddate = today - relativedelta(months=1)
            enddate=enddate.strftime('%Y-%m')
            startdate = today - relativedelta(months=(months))
            startdate = startdate.strftime("%Y-%m")
    else:
        if args.startdate == None or args.enddate == None:
            logging.error("You must provide either a number of months (--months) or a start (-s) and end month (-e) in the format of YYYY-MM.")
            quit()
        else:
            startdate = args.startdate
            enddate = args.enddate


    """
    Retrieve Existing Account Network Storage if requested by flag
    """
    if storageFlag:
        networkStorageDF = getAccountNetworkStorage()

    # Calculate invoice dates based on SLIC invoice cutoffs.
    startdate, enddate = getInvoiceDates(startdate, enddate)

    #  Retrieve Invoices from classic
    classicUsage = getInvoiceDetail(startdate, enddate)

    """"
    Build Exel Report Report with Charges
    """
    if type2Flag:
        createType2Report(args.output, classicUsage)
    else:
        createType1Report(args.output, classicUsage)

    if args.sendGridApi != None:
        sendEmail(startdate, enddate, args.sendGridTo, args.sendGridFrom, args.sendGridSubject, args.sendGridApi, args.output)

    # upload created file to COS if COS credentials provided
    if args.COS_APIKEY != None:
        cos = ibm_boto3.resource("s3",
                                 ibm_api_key_id=args.COS_APIKEY,
                                 ibm_service_instance_id=args.COS_INSTANCE_CRN,
                                 config=Config(signature_version="oauth"),
                                 endpoint_url=args.COS_ENDPOINT
                                 )
        multi_part_upload(args.COS_BUCKET, args.output, "./" + args.output)

    if args.sendGridApi != None or args.COS_APIKEY != None:
        logging.info("Deleting {} local file.".format(args.output))
        os.remove("./"+args.output)
    logging.info("invoiceAnalysis complete.")