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
    totalRecurringCharge = round(( usage * 0.75 * 0.00099) + (usage * 0.25 * 0.0051), 2)
    logging.info("Estimating Zenfolio Discounted usage for {} GB average COS usage at {}.".format(usage, totalRecurringCharge))
    return totalRecurringCharge

def getObjectStorage():
    # GET LIST OF PORTAL INVOICES BETWEEN DATES USING CENTRAL (DALLAS) TIME

    logging.info("Getting current storage usage {}.".format(ims_account))
    try:
        objectstorage = client['Account'].getHubNetworkStorage(id=ims_account, mask="metricTrackingObject")
    except SoftLayer.SoftLayerAPIError as e:
        logging.error("Account::getInvoices: %s, %s" % (e.faultCode, e.faultString))
        quit()
    end = datetime(2022,7,26,23,59,59)
    start = datetime(end.year, end.month, 1,0,0)
    logging.info("Using {} to {} for metrics.".format(start,end))

    print ()
    print ("Buckets,Location,ObjectCount,BytesUsed")
    for instance in objectstorage:
        buckets = client["Network_Storage_Hub_Cleversafe_Account"].getBuckets(id=instance["id"])
        for bucket in buckets:
            print("{},{},{},{}".format(bucket["name"], bucket["storageLocation"], bucket["objectCount"], int(bucket["bytesUsed"])))

        #metrics = client["Network_Storage_Hub_Cleversafe_Account"].getCapacityUsage(id=instance["id"])
        #print("Total Account Usage: {}".format(metrics))

    print ()

    print ("Location,Class,Metric,Qty")
    for instance in objectstorage:
        """
        Pull metrics
        """

        metrics = client["Network_Storage_Hub_Cleversafe_Account"].getCloudObjectStorageMetrics(start.timestamp() * 1000,
                    end.timestamp() * 1000, "us-south", "standard,cold", "copy_count,bandwidth,retrieval,classa,classb",
                    id=instance["id"])

        metrics = json.loads(metrics[1])
        print (json.dumps(metrics["warnings"],indent=2))
        for resource in metrics["resources"]:
            for metric in resource["metrics"]:
                print ("{},{},{},{}".format(resource["storage_location"],resource["storage_class"],metric["name"], metric["value"]))


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
    parser.add_argument("--output", default=os.environ.get('output','forecast-analysis.xlsx'), help="Filename Excel output file. (including extension of .xlsx)")
    parser.add_argument("--SL_PRIVATE", default=False, action=argparse.BooleanOptionalAction, help="Use IBM Cloud Classic Private API Endpoint")
    args = parser.parse_args()

    if args.IC_API_KEY == None:
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

    logging.info("invoiceAnalysis complete.")