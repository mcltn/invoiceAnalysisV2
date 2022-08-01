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
from datetime import datetime, tzinfo, timezone
from dateutil import tz
from calendar import monthrange
from dateutil.relativedelta import relativedelta


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

def createEmployeeClient(end_point_employee, employee_user, passw, token):
    """Creates a softlayer-python client that can make API requests for a given employee_user"""
    client_noauth = SoftLayer.Client(endpoint_url=end_point_employee)
    client_noauth.auth = None
    employee = client_noauth['SoftLayer_User_Employee']
    result = employee.performExternalAuthentication(employee_user, passw, token)
    # Save result['hash'] somewhere to not have to login for every API request
    client_employee = SoftLayer.employee_client(username=employee_user, access_token=result['hash'], endpoint_url=end_point_employee)
    return client_employee

def estimateCost(usage):
    """
    Estimate cost based on contractual calculation
    """
    totalRecurringCharge = round(( usage * 0.75 * 0.00099) + (usage * 0.25 * 0.0051), 5)
    logging.info("Estimating Zenfolio Discounted usage for {} GB average COS usage at {}.".format(usage, totalRecurringCharge))
    return totalRecurringCharge

def getObjectStorageInstances():
    """
    GET LIST OF CLASSIC OBJECT STORAGE INSTANCES
    """

    logging.info("Getting Classic Object Storage Instances {}.".format(ims_account))
    try:
        objectStorageInstances = client['Account'].getHubNetworkStorage(id=ims_account, mask="accountId, id, createDate, notes, billingItem")

        #billingItem.associatedChildren")
    except SoftLayer.SoftLayerAPIError as e:
        logging.error("Account::getHubNetworkStorage: %s, %s" % (e.faultCode, e.faultString))
        quit()
    return objectStorageInstances

def getObjectStorageMetrics(objectStorageInstances, start, end):
    """
    # GET METRICS BETWEEN TWO TIMES FOR EACH OBJECT STORAGE INSTANCE
    """

    logging.info("Using {} to {} for metrics.".format(start,end))

    data = []
    for instance in objectStorageInstances:
        """
        Pull metrics
        """

        metrics = client["Network_Storage_Hub_Cleversafe_Account"].getCloudObjectStorageMetrics(start.timestamp() * 1000,
                    end.timestamp() * 1000, "us-south", "standard,cold,vault,flex", "average_byte_hours,bandwidth,retrieval,classa,classb,average_archive_byte_hours",
                    id=instance["id"])

        metrics = json.loads(metrics[1])
        for resource in metrics["resources"]:
            for metric in resource["metrics"]:
                if resource["storage_class"] == "cold":
                    if metric["name"] == "average_byte_hours":
                        gbused = float(metric["value"]) / 1073741824
                        cost = estimateCost(gbused)
                    elif metric["name"] == "bandwidth":
                        gbused = float(metric["value"]) / 1073741824
                        cost = float(gbused * 0.0425)
                    elif metric["name"] == "retrieval":
                        gbused = float(metric["value"]) / 1073741824
                        cost = float(gbused * 0.0425)
                    elif metric["name"] == "classa":
                        # .02125 per 1000 transactions
                        gbused = 0
                        cost  = (float(metric["value"]) / 1000) * 0.02125
                    elif metric["name"] == "classb":
                        # .02125 per 10,000 transactions
                        gbused =0
                        cost = (float(metric["value"]) / 10000) * 0.02125
                    elif metric["name"] == "average_archive_byte_hours":
                        gbused = float(metric["value"]) / 1073741824
                        cost = float(gbused * 0.0189)
                    else:
                        gbused = 0
                        cost =0
                elif resource["storage_class"] == "standard":
                    if metric["name"] == "average_byte_hours":
                        gbused = float(metric["value"]) / 1073741824
                        cost = gbused * 0.0189
                    elif metric["name"] == "bandwidth":
                        gbused = float(metric["value"]) / 1073741824
                        cost = float(gbused * .09)
                    elif metric["name"] == "retrieval":
                        gbused = float(metric["value"]) / 1073741824
                        cost = float(gbused * 0.0)
                    elif metric["name"] == "classa":
                        # .02125 per 1000 transactions
                        gbused = 0
                        cost  = float(metric["value"]) / 1000 * 0.005
                    elif metric["name"] == "classb":
                        # .02125 per 10,000 transactions
                        gbused =0
                        cost = float(metric["value"]) / 10000 * 0.004
                    else:
                        gbused = 0
                        cost =0

                row = {"start": datetime.strftime(start, "%Y-%m-%d %H:%M:%S"), "end": datetime.strftime(end, "%Y-%m-%d %H:%M:%S"), "billingItemId": instance["billingItem"]["id"], "resourceId": resource["resource_id"], "storageLocation": resource["storage_location"],
                       "storageClass": resource["storage_class"], "metric": metric["name"], "metricValue": float(metric["value"]), "GB": gbused, "estimate": cost}

                data.append(row.copy())

    df = pd.DataFrame(data, columns=['start',
                                     'end',
                                     'billingItemId',
                                     'resourceId',
                                     'storageLocation',
                                     'storageClass',
                                     'metric',
                                     'metricValue',
                                     'GB',
                                     'estimate'
                                     ])

    return df

def createDetailTab(classicUsage):
    """
    Write detail tab to excel
    """
    logging.info("Creating detail tab.")
    classicUsage.to_excel(writer, 'Detail')
    usdollar = workbook.add_format({'num_format': '$#,##0.00'})
    format2 = workbook.add_format({'align': 'left'})
    format3 = workbook.add_format({'num_format': '#,##0'})
    format4 = workbook.add_format({'num_format': '#,##0.00000'})
    worksheet = writer.sheets['Detail']
    worksheet.set_column('B:D', 20, format2)
    worksheet.set_column('E:E', 40, format2)
    worksheet.set_column('F:H', 20, format2)
    worksheet.set_column('I:I', 40, format3)
    worksheet.set_column('J:J', 20, format4)
    worksheet.set_column('K:K', 20, usdollar)


    totalrows,totalcols=classicUsage.shape
    worksheet.autofilter(0,0,totalrows,totalcols)
    return

def createPivot(usage):
    """
    Build a pivot table of Classic Object Storage that displays charges appearing on CFTS invoice
    """

    logging.info("Creating Pivot Tab.")

    cosPivot = pd.pivot_table(usage, index=["storageLocation", "storageClass", "metric"],
                                     values=["metricValue", "GB",  "estimate"],
                                     aggfunc=np.sum, margins=True, margins_name="Total")
    column_order = ["metricValue", "GB", "estimate"]
    cosPivot = cosPivot.reindex(column_order, axis=1)
    cosPivot.to_excel(writer, 'COS_PIVOT')
    worksheet = writer.sheets['COS_PIVOT']
    format1 = workbook.add_format({'num_format': '$#,##0.00'})
    format2 = workbook.add_format({'align': 'left'})
    format3 = workbook.add_format({'num_format': '#,##0'})
    format4 = workbook.add_format({'num_format': '#,##0.00000'})

    worksheet.set_column("A:C", 40, format2)
    worksheet.set_column("D:D", 40, format3)
    worksheet.set_column("E:E", 15, format4)
    worksheet.set_column("F:F", 15, format1)
    return

if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description="Forecast Classic Object Storage Stats.")
    parser.add_argument("-k", "--IC_API_KEY", default=os.environ.get('IC_API_KEY', None), metavar="apikey", help="IBM Cloud API Key")
    parser.add_argument("-u", "--username", default=os.environ.get('ims_username', None), metavar="username", help="IMS Userid")
    parser.add_argument("-p", "--password", default=os.environ.get('ims_password', None), metavar="password", help="IMS Password")
    parser.add_argument("-a", "--account", default=os.environ.get('ims_account', None), metavar="account",
                        help="IMS Account")
    parser.add_argument("-y", "--yubikey", default=os.environ.get('yubikey', None), metavar="yubikey", help="IMS Yubi Key")
    parser.add_argument("--output", default=os.environ.get('output','forecast-analysis.xlsx'), help="Filename Excel output file. (including extension of .xlsx)")
    parser.add_argument("--SL_PRIVATE", default=False, action=argparse.BooleanOptionalAction, help="Use IBM Cloud Classic Private API Endpoint")
    args = parser.parse_args()

    if args.IC_API_KEY == None:
        if args.username == None or args.password == None or args.account == None:
            logging.error("You must provide either IBM Cloud ApiKey or Internal Employee credentials & IMS account.")
            quit()
        else:
            logging.info("Using Internal endpoint and employee credentials.")
            ims_username = args.username
            ims_password = args.password
            ims_yubikey = input("Yubi Key:")
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

    objectStorageInstances = getObjectStorageInstances()
    dallas = tz.gettz('US/Central')
    end =datetime.now().astimezone(dallas)
    start = datetime(end.year, end.month, 1,0,0).astimezone(dallas)

    storage = getObjectStorageMetrics(objectStorageInstances, start, end)

    # Write dataframe to excel
    writer = pd.ExcelWriter("estimate.xlsx", engine='xlsxwriter')
    workbook = writer.book
    createDetailTab(storage)
    createPivot(storage)
    writer.save()

    logging.info("ICOS Forecast complete.")