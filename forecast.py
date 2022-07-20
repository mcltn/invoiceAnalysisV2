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

def createEmployeeClient(end_point_employee, employee_user, passw, token):
    """Creates a softlayer-python client that can make API requests for a given employee_user"""
    client_noauth = SoftLayer.Client(endpoint_url=end_point_employee)
    client_noauth.auth = None
    employee = client_noauth['SoftLayer_User_Employee']
    result = employee.performExternalAuthentication(employee_user, passw, token)
    # Save result['hash'] somewhere to not have to login for every API request
    client_employee = SoftLayer.employee_client(username=result['userId'], auth=result['hash'], endpoint_url=end_point_employee)
    return client_employee

def getObjectStorage():
    # GET LIST OF PORTAL INVOICES BETWEEN DATES USING CENTRAL (DALLAS) TIME

    logging.info("Getting current storage usage.")
    try:
        storage = client['SoftLayer_Network_Storage_Hub_Cleversafe_Account'].getAllObjects(id=37573109)

    except SoftLayer.SoftLayerAPIError as e:
        logging.error("Account::getInvoices: %s, %s" % (e.faultCode, e.faultString))
        quit()
    print(storage)

    return storage

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
    parser.add_argument("-u", "--username", default=os.environ.get('ims_username', None), metavar="username", help="IMS Userid")
    parser.add_argument("-p", "--password", default=os.environ.get('ims_password', None), metavar="password", help="IMS Password")
    parser.add_argument("-a", "--account", default=os.environ.get('ims_account', None), metavar="account",
                        help="IMS Account")
    parser.add_argument("-y", "--yubikey", default=os.environ.get('yubikey', None), metavar="yubikey", help="IMS Yubi Key")
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

    if args.IC_API_KEY != "force":
        if args.username == None or args.password == None or args.yubikey == None or args.account == None:
            logging.error("You must provide either IBM Cloud ApiKey or Internal Employee credentials & IMS account.")
            quit()
        else:
            logging.info("Using Internal endpoint and employee credentials.")
            ims_username = args.username
            ims_password = args.password
            ims_yubikey = args.yubikey
            ims_account = args.account
            SL_ENDPOINT = "http://internal.applb.dal10.softlayer.local/v3.1/internal/xmlrpc"
            client = createEmployeeClient(SL_ENDPOINT, ims_username, ims_password, ims_yubikey)
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