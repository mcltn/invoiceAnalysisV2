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
import os, logging, logging.config, json, os.path, argparse
import pandas as pd
import numpy as np
from datetime import datetime
from dateutil import tz
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

def getAccountId(IC_API_KEY):
    ##########################################################
    ## Get Account from the passed API Key
    ##########################################################

    logging.info("Retrieving IBM Cloud Account ID for this ApiKey.")
    try:
        authenticator = IAMAuthenticator(IC_API_KEY)
    except ApiException as e:
        logging.error("API exception {}.".format(str(e)))
        quit()
    try:
        iam_identity_service = IamIdentityV1(authenticator=authenticator)
    except ApiException as e:
        logging.error("API exception {}.".format(str(e)))
        quit()

    try:
        api_key = iam_identity_service.get_api_keys_details(
          iam_api_key=IC_API_KEY
        ).get_result()
    except ApiException as e:
        logging.error("API exception {}.".format(str(e)))
        quit()

    return api_key["account_id"]

def accountUsage(IC_API_KEY, IC_ACCOUNT_ID):
    """
    Get paas Usage from account for current month to date
    Note: This usage will bill two months later.  For example April Usage, will invoice on the end of June invoice.
    """
    now = datetime.now()
    usageMonth = now.strftime("%Y-%m")
    usageTime = now.strftime("%Y-%m %H:%M")

    try:
        authenticator = IAMAuthenticator(IC_API_KEY)
    except ApiException as e:
        logging.error("API exception {}.".format(str(e)))
        error = ("API exception {}.".format(str(e)))
        return accountUsage, error
    try:
        usage_reports_service = UsageReportsV4(authenticator=authenticator)
    except ApiException as e:
        logging.error("API exception {}.".format(str(e)))
        error = ("API exception {}.".format(str(e)))
        return accountUsage, error

    logging.info("Retrieving PaaS Usage from {}.".format(usageMonth))
    try:
        usage = usage_reports_service.get_account_usage(
            account_id=IC_ACCOUNT_ID,
            billingmonth=usageMonth,
            names=True
        ).get_result()
    except ApiException as e:
        logging.error("API exception {}.".format(str(e)))
        quit()

    data = []
    for resource in usage['resources']:
        for plan in resource['plans']:
            for metric in plan['usage']:
                row = {
                    'usageMonth': usageMonth,
                    'usageTime': usageTime,
                    'currency_code': usage['currency_code'],
                    'billing_country': usage['billing_country'],
                    'resource_id': resource['resource_id'],
                    'resource_name': resource['resource_name'],
                    'billable_charges': resource["billable_cost"],
                    'billable_rated_charges': resource["billable_rated_cost"],
                    'plan_id': plan['plan_id'],
                    'plan_name': plan['plan_name'],
                    'metric': metric['metric'],
                    'unit_name': metric['unit_name'],
                    'quantity': metric['quantity'],
                    'rateable_quantity': metric['rateable_quantity'],
                    'cost': metric['cost'],
                    'rated_cost': metric['rated_cost'],
                    }

                if len(metric['discounts']) > 0:
                    row['discount'] = metric['discounts'][0]['discount']
                else:
                    row['discount'] = 0
                data.append(row.copy())

    accountUsage = pd.DataFrame(data, columns=['usageMonth',
                    'usageTime',
                    'currency_code',
                    'billing_country',
                    'resource_id',
                    'resource_name',
                    'billable_charges',
                    'billable_rated_charges',
                    'plan_id',
                    'plan_name',
                    'metric',
                    'unit_name',
                    'quantity',
                    'rateable_quantity',
                    'cost',
                    'rated_cost',
                    'discount'])

    return accountUsage

def createDetailTab(paasUsage):
    """
    Write detail tab to excel
    """
    logging.info("Creating detail tab.")

    paasUsage.to_excel(writer, "Detail")
    worksheet = writer.sheets['Detail']
    format1 = workbook.add_format({'num_format': '$#,##0.00'})
    format2 = workbook.add_format({'align': 'left'})
    worksheet.set_column("A:C", 12, format2)
    worksheet.set_column("D:E", 25, format2)
    worksheet.set_column("F:G", 18, format1)
    worksheet.set_column("H:I", 25, format2)
    worksheet.set_column("J:J", 18, format1)
    totalrows,totalcols=paasUsage.shape
    worksheet.autofilter(0,0,totalrows,totalcols)
    return

def createSummaryPivot(paasUsage):
    paasSummary = pd.pivot_table(paasUsage, index=["resource_name"],
                                    values=["cost"],
                                    aggfunc=np.sum, margins=True, margins_name="Total",
                                    fill_value=0)
    paasSummary.to_excel(writer, 'PaaS_Summary')
    worksheet = writer.sheets['PaaS_Summary']
    format1 = workbook.add_format({'num_format': '$#,##0.00'})
    format2 = workbook.add_format({'align': 'left'})
    worksheet.set_column("A:A", 35, format2)
    worksheet.set_column("B:ZZ", 18, format1)

def createPlanPivot(paasUsage):
    paasSummaryPlan = pd.pivot_table(paasUsage, index=["resource_name", "plan_name", "unit_name"],
                                 values=["quantity", "cost"],
                                 aggfunc=np.sum, margins=True, margins_name="Total",
                                 fill_value=0)
    column_order = ["quantity", "cost"]
    paasSummaryPlan = paasSummaryPlan.reindex(column_order, axis=1)
    paasSummaryPlan.to_excel(writer, 'PaaS_Metric_Summary')
    worksheet = writer.sheets['PaaS_Metric_Summary']
    format1 = workbook.add_format({'num_format': '$#,##0.00'})
    format2 = workbook.add_format({'align': 'left'})
    format3 = workbook.add_format({'num_format': '#,##0.00000'})
    worksheet.set_column("A:A", 30, format2)
    worksheet.set_column("B:B", 40, format2)
    worksheet.set_column("C:C", 40, format2)
    worksheet.set_column("D:D", 15, format3)
    worksheet.set_column("E:E", 15, format1)
    totalrows,totalcols=paasSummaryPlan.shape
    worksheet.autofilter(0,0,totalrows,totalcols)

    return

if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description="Estimate PaaS Usage.")
    parser.add_argument("-k", "--IC_API_KEY", default=os.environ.get('IC_API_KEY', None), metavar="apikey", help="IBM Cloud API Key")
    parser.add_argument("--output", default=os.environ.get('output','paasEstimate.xlsx'), help="Filename Excel output file. (including extension of .xlsx)")
    args = parser.parse_args()

    if args.IC_API_KEY == None:
        if args.username == None or args.password == None or args.account == None:
            logging.error("You must provide IBM Cloud ApiKey with view access to usage reporting.")
            quit()
    else:
        logging.info("Using IBM Cloud Account API Key.")
        IC_API_KEY = args.IC_API_KEY
        ims_account = None

    paasUsage = accountUsage(IC_API_KEY, getAccountId(IC_API_KEY))

    # Write dataframe to excel
    writer = pd.ExcelWriter(args.output, engine='xlsxwriter')
    workbook = writer.book
    createDetailTab(paasUsage)
    createSummaryPivot(paasUsage)
    createPlanPivot(paasUsage)
    writer.save()

    logging.info("PaaS Estimate is complete.")