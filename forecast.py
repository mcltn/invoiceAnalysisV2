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
"""
usage: invoiceAnalysis.py [-h] [-k apikey] [-s YYYY-MM] [-e YYYY-MM] [-m MONTHS] [--COS_APIKEY COS_APIKEY] [--COS_ENDPOINT COS_ENDPOINT] [--COS_INSTANCE_CRN COS_INSTANCE_CRN] [--COS_BUCKET COS_BUCKET] [--sendGridApi SENDGRIDAPI]      ─╯
                          [--sendGridTo SENDGRIDTO] [--sendGridFrom SENDGRIDFROM] [--sendGridSubject SENDGRIDSUBJECT] [--output OUTPUT] [--SL_PRIVATE | --no-SL_PRIVATE]

Export usage detail by invoice month to an Excel file for all IBM Cloud Classic invoices and corresponding lsPaaS Consumption.

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

"""
__author__ = 'jonhall'
import SoftLayer, os, logging, logging.config, json, calendar, os.path, argparse, pytz, base64, re
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
from ibm_platform_services import IamIdentityV1, UsageReportsV4
from ibm_cloud_sdk_core import ApiException
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator

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
                return item['description'].strip()
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


def getObjectStorage():
    # GET LIST OF PORTAL INVOICES BETWEEN DATES USING CENTRAL (DALLAS) TIME

    global client, data
    # Create dataframe to work with for classic infrastructure invoices
    data = []

    dallas = tz.gettz('US/Central')

    # Create Classic infra API client
    client = SoftLayer.Client(username="apikey", api_key=IC_API_KEY, endpoint_url=SL_ENDPOINT)

    dallas=tz.gettz('US/Central')
    logging.info("Getting current storage usage.")
    try:
        storage = client['Network_Storage_Hub_Swift_Metrics'].getMetricData(id=37573109)

    except SoftLayer.SoftLayerAPIError as e:
        logging.error("Account::getInvoices: %s, %s" % (e.faultCode, e.faultString))
        quit()
    print(storage)

    return storage


def parseChildren(row, parentDescription, children):
    """
    Parse Children Record if requested
    """
    global data

    for child in children:
        if float(child["recurringFee"]) > 0:
            row['RecordType'] = "Child"
            row["childBillingItemId"] = child["billingItemId"]
            row['childParentProduct'] = parentDescription
            row["Category"] = child["product"]["itemCategory"]["name"]
            if "group" in child["category"]:
                row["Category_Group"] = child["category"]["group"]["name"]
            else:
                row["Category_group"] = child['categoryGroup']
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

            # if cold average usage calculate discounted charge
            if row["Category_Group"] == "StorageLayer" and child["description"].find("cold Average Usage") != -1:
                row["childTotalRecurringCharge"] = round(
                    (row["childUsage"] * 0.75 * 0.00099) + (row["childUsage"] * 0.25 * 0.0051), 2)
                logging.info("Recalculating Zenfolio Discounted usage for {} GB average COS usage at {}.".format(row["childUsage"],row[
                                                                                                         "childTotalRecurringCharge"]))
            # write child record
            data.append(row.copy())
            logging.info("child {} {} RecurringFee: {}".format(row["childBillingItemId"], row["Description"],
                                                               row["childTotalRecurringCharge"]))
            logging.debug(row)
    return

def getInvoiceDetail(IC_API_KEY, SL_ENDPOINT):
    """
    Read invoice top level detail from range of invoices
    """
    global client, data
    # Create dataframe to work with for classic infrastructure invoices
    data = []

    dallas = tz.gettz('US/Central')

    # Create Classic infra API client
    client = SoftLayer.Client(username="apikey", api_key=IC_API_KEY, endpoint_url=SL_ENDPOINT)

    logging.info("Retrieving next invoice top level line items.")

    try:
        billingItems = client['Account'].getNextInvoiceTopLevelBillingItems(
                            mask="id, createDate, cycleStartDate, modifyDate, nextBillDate, cancellationDate, categoryCode, category, category.group, notes,"\
                                 "hourlyFlag, hostName, domainName, description, currentHourlyCharge, hoursUsed, recurringFee, hourlyRecurringFee,"\
                                 "children.description, children.category.group, children.categoryCode, children.recurringFee")
    except SoftLayer.SoftLayerAPIError as e:
        logging.error("Account::getNextInvoiceTopLevelBillingItems: %s, %s" % (e.faultCode, e.faultString))
        quit()

    logging.info("Retrieved {} next invoice top level line items.".format(len(billingItems)))
    # ITERATE THROUGH DETAIL
    for item in billingItems:
        logging.debug(item)
        createDate = datetime.strptime(item["createDate"], "%Y-%m-%dT%H:%M:%S%z").astimezone(dallas).strftime("%Y-%m-%d")
        cycleStartDate = datetime.strptime(item["cycleStartDate"], "%Y-%m-%dT%H:%M:%S%z").astimezone(dallas).strftime("%Y-%m-%d")

        if item["cancellationDate"] == "":
            cancellationDate = ""
        else:
            cancellationDate = datetime.strptime(item["cancellationDate"], "%Y-%m-%dT%H:%M:%S%z").astimezone(dallas).strftime("%Y-%m-%d")

        modifyDate=""
        if "modifyDate" in item:
            if item["modifyDate"] != "":
                modifyDate = datetime.strptime(item["modifyDate"], "%Y-%m-%dT%H:%M:%S%z").astimezone(dallas).strftime("%Y-%m-%d")

        nextBillDate = datetime.strptime(item["nextBillDate"], "%Y-%m-%dT%H:%M:%S%z").astimezone(dallas).strftime("%Y-%m-%d")
        if "group" in item["category"]:
            categoryGroup = item["category"]["group"]["name"]
        else:
            categoryGroup = "Other"

        category = item["categoryCode"]
        categoryName = item["category"]["name"]
        description = item['description']

        memory = getDescription("ram", item["children"])
        os = getDescription("os", item["children"])

        if 'hostName' in item:
            if 'domainName' in item:
                hostName = item['hostName']+"."+item['domainName']
            else:
                hostName = item['hostName']
        else:
            hostName = ""

        if "recurringFee" in item:
            recurringFee = float(item["recurringFee"])
        else:
            recurringFee = 0

        if "hoursUsed" in item:
            hoursUsed = item["hoursUsed"]
        else:
            hoursUsed = 0

        if "currentHourlyCharge" in item:
            currentHourlyCharge = item["currentHourlyCharge"]
        else:
            currentHourlyCharge = 0

        if "hourlyRecurringFee" in item:
            hourlyRecurringFee = item["hourlyRecurringFee"]
        else:
            hourlyRecurringFee = 0

        """
        # If Hourly calculate hourly rate and total hours
        if item["hourlyFlag"]:
            hourlyRecurringFee = 0
            hoursUsed = 0
            if "hourlyRecurringFee" in item:
                if float(item["hourlyRecurringFee"]) > 0:
                    hourlyRecurringFee = float(item['hourlyRecurringFee'])
                    for child in item["children"]:
                        if "hourlyRecurringFee" in child:
                            hourlyRecurringFee = hourlyRecurringFee + float(child['hourlyRecurringFee'])
        """

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
                if hourlyRecurringFee>0:
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
                    description = model + " File Storage "+ space + " at " + tier
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

        #datetime.strptime(invoice['createDate'], "%Y-%m-%dT%H:%M:%S%z").astimezone(dallas)
        recordType = "Parent"
        # Append record to dataframe
        row = {'createDate': createDate,
               'cycleStartDate': cycleStartDate,
               'cancellationDate': cancellationDate,
               'modifyDate': modifyDate,
               'nextBillDate': nextBillDate,
               'id': item["id"],
               'RecordType': recordType,
               'hostName': hostName,
               'Category_Group': categoryGroup,
               'Category': categoryName,
               'Description': description,
               'Memory': memory,
               'OS': os,
               'hourlyFlag': item["hourlyFlag"],
               'hoursUsed': hoursUsed,
               'hourlyRecurringFee': round(hourlyRecurringFee,5),
               'recurringFee': round(recurringFee,3),
               'currentHourlyCharge': round(currentHourlyCharge,3)
                }
        # write parent record
        data.append(row.copy())
        logging.info("parent {} {} RecurringFee: {}".format(row["id"], row["Description"],row["recurringFee"]))
        logging.debug(row)

        #if len(item["children"]) > 0:
        #    parseChildren(row, description, item["children"])

    df = pd.DataFrame(data)

    return df

def fixParentRecordsObjectStorage(df):
    """
    Re-calculate parent recurrigncharge to match sum of adjusted children records for each month in report.
    """

    months = df.IBM_Invoice_Month.unique()
    for i in months:
        parents = df.query('Category_Group == "StorageLayer" and IBM_Invoice_Month == @i and RecordType == "Parent"')
        for row in parents.itertuples():
            index = row[0]
            billingItemId = row[9]
            # calculate adjusted parent recurring charge from sum of children already adjusted
            sum = df.query('BillingItemId == @billingItemId and RecordType == ["Child"] and IBM_Invoice_Month == @i')["childTotalRecurringCharge"].sum()
            df.at[index, 'totalRecurringCharge'] = sum
    # return adjusted dataframe
    return df


def createReport(filename, classicUsage):
    """
    Create multiple tabs and write to excel file
    """
    global writer, workbook

    # Write dataframe to excel
    writer = pd.ExcelWriter(filename, engine='xlsxwriter')
    workbook = writer.book
    logging.info("Creating {}.".format(filename))

    # re-calculate Zenfolio top level parent items from children for classic object storage
    #classicUsage = fixParentRecordsObjectStorage(classicUsage)

    # create pivots for various tabs
    print(classicUsage)
    createDetailTab(classicUsage)
    #createInvoiceSummary(classicUsage)
    #createCategoorySummary(classicUsage)
    #createPlatformDetail(classicUsage)
    #createIaaSLineItemDetail(classicUsage)
    #createClassicCOS(classicUsage)
    #createPaaSCOS(classicUsage)

    writer.save()

    return

def createDetailTab(classicUsage):
    """
    Write detail tab to excel
    """
    logging.info("Creating detail tab.")
    classicUsage.to_excel(writer, 'Detail')
    usdollar = workbook.add_format({'num_format': '$#,##0.00'})
    format2 = workbook.add_format({'align': 'left'})
    worksheet = writer.sheets['Detail']
    #worksheet.set_column('Q:AA', 18, usdollar)
    #worksheet.set_column('AB:AB', 18, format2)
    #worksheet.set_column('AC:AC', 18, usdollar)
    #worksheet.set_column('W:W', 18, format2 )
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

    if len(classicUsage)>0:
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

def createIaaSLineItemDetail(classicUsage):
    """
    Build a pivot table for items that show on CFTS IaaS charges not included in the PaaS children detail
    """

    if len(classicUsage) > 0:
        logging.info("Creating IaaS_Line_item_Detail Tab.")
        iaasRecords = classicUsage.query('RecordType == ["Parent"] and Category != ["Object Storage"] and (TaxCategory == ["IaaS"] or TaxCategory == ["HELP DESK"] '\
                                         'or Description == ["Block Storage for VPC 10 IOPS/GB Gen2"] or Description == ["Block Storage for VPC 5 IOPS/GB Gen2"]'\
                                         'or Description == ["Block Storage for VPC General Purpose Tier Gen2"])')
        iaasSummary = pd.pivot_table(iaasRecords, index=["Type", "Category_Group", "Category", "Description"],
                                         values=["totalAmount"],
                                         columns=['IBM_Invoice_Month'],
                                         aggfunc={'totalAmount': np.sum}, margins=True, margins_name="Total", fill_value=0)
        iaasSummary.to_excel(writer, 'IaaS_Line_item_Detail')
        worksheet = writer.sheets['IaaS_Line_item_Detail']
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
        logging.info("Creating Classic_COS_Detail Tab.")
        iaasscosRecords = classicUsage.query('RecordType == ["Child"] and childParentProduct == ["Cloud Object Storage - S3 API"]')
        iaascosSummary = pd.pivot_table(iaasscosRecords, index=["Type", "Category_Group", "childParentProduct", "Category", "Description"],
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

def createPaaSCOS(classicUsage):
    """
    Build a pivot table of PaaS object storage
    """

    if len(classicUsage) > 0:
        logging.info("Creating PaaS_COS_Detail Tab.")
        paascosRecords = classicUsage.query('RecordType == ["Child"] and childParentProduct == ["Cloud Object Storage Premium"]')
        paascosSummary = pd.pivot_table(paascosRecords, index=["Type", "Category_Group", "childParentProduct", "Category", "Description"],
                                         values=["childTotalRecurringCharge"],
                                         columns=['IBM_Invoice_Month'],
                                         aggfunc={'childTotalRecurringCharge': np.sum}, fill_value=0, margins=True, margins_name="Total")
        paascosSummary.to_excel(writer, 'PaaS_COS_Detail')
        worksheet = writer.sheets['PaaS_COS_Detail']
        format1 = workbook.add_format({'num_format': '$#,##0.00'})
        format2 = workbook.add_format({'align': 'left'})
        worksheet.set_column("A:A", 20, format2)
        worksheet.set_column("B:D", 40, format2)
        worksheet.set_column("E:E", 55, format2)
        worksheet.set_column("F:ZZ", 18, format1)
    return

def createPlatformDetail(classicUsage):
    """
    Build a pivot table of items that typically show on CFTS invoice at child level
    """

    if len(classicUsage) > 0:
        logging.info("Creating Platform Detail Tab.")
        childRecords = classicUsage.query('RecordType == ["Child"] and TaxCategory == ["PaaS"] and ' \
                '(childParentProduct != ["Block Storage for VPC 10 IOPS/GB Gen2"] and childParentProduct != ["Block Storage for VPC 5 IOPS/GB Gen2"] ' \
                'and childParentProduct != ["Block Storage for VPC General Purpose Tier Gen2"])' \
                ' and childParentProduct != ["Cloud Object Storage Premium"]')
        childSummary = pd.pivot_table(childRecords, index=["Type", "Category_Group", "childParentProduct", "Category", "Description"],
                                         values=["childTotalRecurringCharge"],
                                         columns=['IBM_Invoice_Month'],
                                         aggfunc={'childTotalRecurringCharge': np.sum}, fill_value=0)
        childSummary.to_excel(writer, 'Platform_Detail')
        worksheet = writer.sheets['Platform_Detail']
        format1 = workbook.add_format({'num_format': '$#,##0.00'})
        format2 = workbook.add_format({'align': 'left'})
        worksheet.set_column("A:A", 20, format2)
        worksheet.set_column("B:D", 40, format2)
        worksheet.set_column("E:E", 60, format2)
        worksheet.set_column("F:ZZ", 18, format1)
    return

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
    parser = argparse.ArgumentParser(
        description="Export next invoice (forecast) to an Excel file for all IBM Cloud Classic invoices and corresponding lsPaaS Consumption.")
    parser.add_argument("-k", "--IC_API_KEY", default=os.environ.get('IC_API_KEY', None), metavar="apikey", help="IBM Cloud API Key")
    parser.add_argument("--COS_APIKEY", default=os.environ.get('COS_APIKEY', None), help="COS apikey to use for Object Storage.")
    parser.add_argument("--COS_ENDPOINT", default=os.environ.get('COS_ENDPOINT', None), help="COS endpoint to use for Object Storage.")
    parser.add_argument("--COS_INSTANCE_CRN", default=os.environ.get('COS_INSTANCE_CRN', None), help="COS Instance CRN to use for file upload.")
    parser.add_argument("--COS_BUCKET", default=os.environ.get('COS_BUCKET', None), help="COS Bucket name to use for file upload.")
    parser.add_argument("--sendGridApi", default=os.environ.get('sendGridApi', None), help="SendGrid ApiKey used to email output.")
    parser.add_argument("--sendGridTo", default=os.environ.get('sendGridTo', None), help="SendGrid comma deliminated list of emails to send output to.")
    parser.add_argument("--sendGridFrom", default=os.environ.get('sendGridFrom', None), help="Sendgrid from email to send output from.")
    parser.add_argument("--sendGridSubject", default=os.environ.get('sendGridSubject', None), help="SendGrid email subject for output email")
    parser.add_argument("--output", default=os.environ.get('output','forecast-analysis.xlsx'), help="Filename Excel output file. (including extension of .xlsx)")
    parser.add_argument("--SL_PRIVATE", default=False, action=argparse.BooleanOptionalAction, help="Use IBM Cloud Classic Private API Endpoint")

    args = parser.parse_args()

    if args.IC_API_KEY == None:
        logging.error("You must provide an IBM Cloud ApiKey with billing View authority to run script.")
        quit()

    IC_API_KEY = args.IC_API_KEY

    # Change endpoint to private Endpoint if command line open chosen
    if args.SL_PRIVATE:
        SL_ENDPOINT = "https://api.service.softlayer.com/xmlrpc/v3.1"
    else:
        SL_ENDPOINT = "https://api.softlayer.com/xmlrpc/v3.1"

    #  Retrieve Invoices from classic
    #classicUsage = getInvoiceDetail(IC_API_KEY, SL_ENDPOINT)
    storage = getObjectStorage()
    quit()

    """"
    Build Exel Report Report with Charges
    """
    createReport(args.output, classicUsage)

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
        #cleanup file if written to COS or sendvia email
        logging.info("Deleting {} local file.".format(args.output))
        os.remove("./"+args.output)
    logging.info("invoiceAnalysis complete.")