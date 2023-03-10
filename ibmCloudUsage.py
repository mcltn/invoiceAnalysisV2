
#!/usr/bin/env python3
# Author: Jon Hall
# Copyright (c) 2023
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
import os, logging, logging.config, json, os.path, argparse, calendar, time
import pandas as pd
import numpy as np
from datetime import datetime
from dateutil.relativedelta import *
from dateutil import tz
import ibm_boto3
from ibm_botocore.client import Config, ClientError
from ibm_platform_services import IamIdentityV1, UsageReportsV4, GlobalTaggingV1, GlobalSearchV2
from ibm_platform_services.resource_controller_v2 import *
from ibm_cloud_sdk_core import ApiException
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator
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

def getAccountId(IC_API_KEY):
    ##########################################################
    ## Get AccountId for this API Key
    ##########################################################

    try:
        api_key = iam_identity_service.get_api_keys_details(
          iam_api_key=IC_API_KEY
        ).get_result()
    except ApiException as e:
        logging.error("API exception {}.".format(str(e)))
        quit()

    return api_key["account_id"]

def createSDK(IC_API_KEY):
    """
       Create SDK clients
       """
    global usage_reports_service, resource_controller_service, global_tagging_service, iam_identity_service, global_search_service

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
        usage_reports_service = UsageReportsV4(authenticator=authenticator)
    except ApiException as e:
        logging.error("API exception {}.".format(str(e)))
        quit()

    try:
        resource_controller_service = ResourceControllerV2(authenticator=authenticator)
    except ApiException as e:
        logging.error("API exception {}.".format(str(e)))
        quit()

    try:
        global_tagging_service = GlobalTaggingV1(authenticator=authenticator)
    except ApiException as e:
        logging.error("API exception {}.".format(str(e)))
        quit()

    try:
        global_search_service = GlobalSearchV2(authenticator=authenticator)
    except ApiException as e:
        logging.error("API exception {}.".format(str(e)))
        quit()
def prePopulateTagCache():
    """
    Pre Populate Tagging data into cache
    """
    logging.info("Tag Cache being pre-populated with tags.")
    search_cursor = None
    items = []
    while True:
        response = global_search_service.search(query='tags:*',
                                                search_cursor=search_cursor,
                                                fields=["tags"],
                                                limit=1000)
        scan_result = response.get_result()

        items = items + scan_result["items"]
        if "search_cursor" not in scan_result:
            break
        else:
            search_cursor = scan_result["search_cursor"]

    tag_cache = {}
    for resource in items:
        resourceId = resource["crn"]

        tag_cache[resourceId] = resource["tags"]

    return tag_cache
def prePopulateResourceCache():
    """
    Retrieve all Resources for account from resource controller and pre-populate cache
    """
    logging.info("Resource_cache being pre-populated with active resources in account.")
    all_results = []
    pager = ResourceInstancesPager(
        client=resource_controller_service,
        limit=50
    )

    try:
        while pager.has_next():
            next_page = pager.get_next()
            assert next_page is not None
            all_results.extend(next_page)
        logging.debug("resource_instance={}".format(all_results))
    except ApiException as e:
        logging.error(
            "API Error.  Can not retrieve instances of type {} {}: {}".format(resource_type, str(e.code),
                                                                              e.message))
        quit()

    resource_cache = {}
    for resource in all_results:
        resourceId = resource["crn"]
        resource_cache[resourceId] = resource

    return resource_cache
def getAccountUsage(start, end):
    """
    Get IBM Cloud Service from account for range of months.
    Note: This usage will bill two months later for SLIC.  For example April Usage, will invoice on the end of June CFTS invoice.
    """

    data = []
    while start <= end:
        usageMonth = start.strftime("%Y-%m")
        logging.info("Retrieving Account Usage from {}.".format(usageMonth))
        start += relativedelta(months=+1)

        try:
            usage = usage_reports_service.get_account_usage(
                account_id=accountId,
                billingmonth=usageMonth,
                names=True
            ).get_result()
        except ApiException as e:
            if e.code == 424:
                logging.warning("API exception {}.".format(str(e)))
                continue
            else:
                logging.error("API exception {}.".format(str(e)))
                quit()

        logging.debug("usage {}={}".format(usageMonth, usage))
        for resource in usage['resources']:
            for plan in resource['plans']:
                for metric in plan['usage']:
                    row = {
                        'account_id': usage["account_id"],
                        'month': usageMonth,
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
                        'quantity': float(metric['quantity']),
                        'rateable_quantity': metric['rateable_quantity'],
                        'cost': metric['cost'],
                        'rated_cost': metric['rated_cost'],
                        }

                    if len(metric['discounts']) > 0:
                        row['discount'] = metric['discounts'][0]['discount']
                    else:
                        discount = 0

                    if len(metric['price']) > 0:
                        row['price'] = metric['price']
                    else:
                        row['price'] = "[]"
                    # add row to data
                    data.append(row.copy())


    accountUsage = pd.DataFrame(data, columns=['account_id', 'month', 'currency_code', 'billing_country', 'resource_id', 'resource_name',
                    'billable_charges', 'billable_rated_charges', 'plan_id', 'plan_name', 'metric', 'unit_name', 'quantity',
                    'rateable_quantity','cost', 'rated_cost', 'discount', 'price'])

    return accountUsage
def getInstancesUsage(start,end):
    """
    Get instances resource usage for month of specific resource_id
    """

    def getResourceInstancefromCloud(resourceId):
        """
        Retrieve Resource Details from resource controller
        """
        try:
            resource_instance = resource_controller_service.get_resource_instance(
                id=resourceId).get_result()
            logging.debug("resource_instance={}".format(resource_instance))
        except ApiException as e:
            resource_instance = {}
            if e.code == 403:
                logging.warning(
                    "You do not have the required permissions to retrieve the instance {} {}: {}".format(resourceId, str(e.code), e.message))
            else:
                logging.warning(
                    "Error: Instance {} {}: {}".format(resourceId, str(e.code),e.message))
        return resource_instance

    def getResourceInstance(resourceId):
        """
        Check Cache for Resource Details which may have been retrieved previously
        """
        if resourceId not in resource_cache:
            logging.debug("Cache miss for Resource {}".format(resourceId))
            resource_cache[resourceId] = getResourceInstancefromCloud(resourceId)
        return resource_cache[resourceId]

    def getTags(resourceId):
        """
        Check Tag Cache for Resource
        """
        if resourceId not in tag_cache:
            logging.debug("Cache miss for Tag {}".format(resourceId))
            tags = []
        else:
            tags = tag_cache[resourceId]
        return tags

    data = []
    limit = 100  ## set limit of record returned

    while start <= end:
        usageMonth = start.strftime("%Y-%m")
        logging.info("Retrieving Instances Usage from {}.".format(usageMonth))
        start += relativedelta(months=+1)
        recordstart = 1
        instances_usage = usage_reports_service.get_resource_usage_account(
            account_id=accountId,
            billingmonth=usageMonth, names=True, limit=limit).get_result()
        logging.info("Requesting Instance Usage: Start {}, Limit={}, Count={}".format(recordstart, limit, instances_usage["count"]))
        if "next" in instances_usage:
            nextoffset = instances_usage["next"]["offset"]
        else:
            nextoffset = ""
        rows_count = instances_usage["count"]

        while rows_count > recordstart:
            for instance in instances_usage["resources"]:
                logging.info("Retreiving Instance {} of {} {}".format(recordstart, rows_count, instance["resource_instance_id"]))
                logging.debug("instance={}".format(instance))

                recordstart = recordstart +1
                if "pricing_country" in instance:
                    pricing_country = instance["pricing_country"]
                else:
                    pricing_country = ""

                if "billing_country" in instance:
                    billing_country = instance["billing_country"]
                else:
                    billing_country = ""

                if "currency_code" in instance:
                    currency_code = instance["currency_code"]
                else:
                    currency_code = ""

                if "pricing_region" in instance:
                    pricing_region = instance["pricing_region"]
                else:
                    pricing_region = ""

                row = {
                    "account_id": instance["account_id"],
                    "instance_id": instance["resource_instance_id"],
                    "resource_group_id": instance["resource_group_id"],
                    "month": instance["month"],
                    "pricing_country": pricing_country,
                    "billing_country": billing_country,
                    "currency_code": currency_code,
                    "plan_id": instance["plan_id"],
                    "plan_name": instance["plan_name"],
                    "billable": instance["billable"],
                    "pricing_plan_id": instance["pricing_plan_id"],
                    "pricing_region": pricing_region,
                    "region": instance["region"],
                    "service_id": instance["resource_id"],
                    "service_name": instance["resource_name"],
                    "resource_group_name": instance["resource_group_name"],
                    "instance_name": instance["resource_instance_name"]
                }

                """
                Get additional resource instance detail
                """

                # get instance detail from cache or resource controller
                resource_instance = getResourceInstance(instance["resource_instance_id"])

                if "created_at" in resource_instance:
                    created_at = resource_instance["created_at"]
                else:
                    created_at = ""

                if "updated_at" in resource_instance:
                    updated_at = resource_instance["updated_at"]
                else:
                    updated_at = ""

                if "deleted_at" in resource_instance:
                    deleted_at = resource_instance["deleted_at"]
                else:
                    deleted_at = ""

                if "state" in resource_instance:
                    state = resource_instance["state"]
                else:
                    state = ""

                if "type" in resource_instance:
                    type = resource_instance["type"]
                else:
                    type = ""

                roks_cluster_id = ""
                roks_cluster_name = ""
                if type == "container_instance":
                    if instance["plan_id"] == "containers.kubernetes.cluster.roks":
                        """ This is the instance of the ROKS Cluster"""
                        roks_cluster_id = instance["resource_instance_name"]
                        roks_cluster_name =  instance["resource_instance_name"]
                    elif instance["plan_id"] == "containers.kubernetes.vpc.gen2.roks":
                        """ This is a worker instance """
                        roks_cluster_id = instance["resource_instance_name"][0:instance["resource_instance_name"].find('_')]
                        roks_cluster_name = instance["resource_instance_name"][0:instance["resource_instance_name"].find('_')]

                """
                For VPC Virtual Servers obtain intended profile and virtual server details
                """
                az = ""
                profile = ""
                cpuFamily = ""
                numberOfVirtualCPUs = ""
                MemorySizeMiB = ""
                NodeName = ""
                NumberOfGPUs = ""
                NumberOfInstStorageDisks = ""

                if "extensions" in resource_instance:
                    if "VirtualMachineProperties" in resource_instance["extensions"]:
                        profile = resource_instance["extensions"]["VirtualMachineProperties"]["Profile"]
                        cpuFamily = resource_instance["extensions"]["VirtualMachineProperties"]["CPUFamily"]
                        numberOfVirtualCPUs = resource_instance["extensions"]["VirtualMachineProperties"]["NumberOfVirtualCPUs"]
                        MemorySizeMiB = resource_instance["extensions"]["VirtualMachineProperties"]["MemorySizeMiB"]
                        NodeName = resource_instance["extensions"]["VirtualMachineProperties"]["NodeName"]
                        NumberOfGPUs = resource_instance["extensions"]["VirtualMachineProperties"]["NumberOfGPUs"]
                        NumberOfInstStorageDisks = resource_instance["extensions"]["VirtualMachineProperties"]["NumberOfInstStorageDisks"]

                    elif "BMServerProperties" in resource_instance["extensions"]:
                        profile = resource_instance["extensions"]["BMServerProperties"]["Profile"]
                        cpuFamily = ""

                    if "Resource" in resource_instance["extensions"]:
                        if "AvailabilityZone" in resource_instance["extensions"]["Resource"]:
                            az = resource_instance["extensions"]["Resource"]["AvailabilityZone"]

                # get tags attached to instance from cache or resource controller
                tags = getTags(instance["resource_instance_id"])

                # parse role tag into comma delimited list
                if len(tags) > 0:
                    role = ",".join([str(item.split(":")[1]) for item in tags if "role:" in item])
                else:
                    role = ""

                row_addition = {
                    "instance_created_at": created_at,
                    "instance_updated_at": updated_at,
                    "instance_deleted_at": deleted_at,
                    "instance_state": state,
                    "type": type,
                    "roks_cluster_id": roks_cluster_id,
                    "roks_cluster_name": roks_cluster_name,
                    "instance_profile": profile,
                    "cpu_family": cpuFamily,
                    "numberOfVirtualCPUs": numberOfVirtualCPUs,
                    "MemorySizeMiB":  MemorySizeMiB,
                    "NodeName":  NodeName,
                    "NumberOfGPUs": NumberOfGPUs,
                    "NumberOfInstStorageDisks": NumberOfInstStorageDisks,
                    "instance_role": role,
                    "availability_zone": az
                }

                # combine original row with additions
                row = row | row_addition

                for usage in instance["usage"]:
                    metric = usage["metric"]
                    unit = usage["unit"]
                    quantity = float(usage["quantity"])
                    cost = usage["cost"]
                    rated_cost = usage["rated_cost"]
                    rateable_quantity = float(usage["rateable_quantity"])
                    price = usage["price"]
                    discount = usage["discounts"]
                    metric_name = usage["metric_name"]
                    unit_name = usage["unit_name"]

                    # For servers estimate days of usage
                    if (instance["resource_name"] == "Virtual Server for VPC" or instance["resource_name"] == "Bare Metal Servers for VPC") and unit.find("HOUR") != -1:
                        estimated_days = np.ceil(float(quantity)/24)
                    else:
                        estimated_days = ""

                    row_addition = {
                        "metric": metric,
                        "unit": unit,
                        "quantity": quantity,
                        "cost": cost,
                        "rated_cost": rated_cost,
                        "rateable_quantity": rateable_quantity,
                        "price": price,
                        "discount": discount,
                        "metric_name": metric_name,
                        'unit_name': unit_name,
                        'estimated_days': estimated_days
                    }

                    row = row | row_addition

                    data.append(row.copy())

            instances_usage = usage_reports_service.get_resource_usage_account(
                account_id=accountId,
                billingmonth=usageMonth, names=True,limit=limit, start=nextoffset).get_result()
            if "next" in instances_usage:
                nextoffset = instances_usage["next"]["offset"]
            else:
                nextoffset = ""

            logging.debug("instance_usage {}={}".format(usageMonth, instances_usage))
            logging.info("Start {}, Limit={}, Count={}".format(recordstart, instances_usage["limit"], instances_usage["count"]))


        instancesUsage = pd.DataFrame(data, columns=['account_id', "month", "service_name", "service_id", "instance_name","instance_id", "plan_name", "plan_id", "region", "pricing_region",
                                                 "resource_group_name","resource_group_id", "billable", "pricing_country", "billing_country", "currency_code", "pricing_plan_id",
                                                 "instance_created_at", "instance_updated_at", "instance_deleted_at", "instance_state", "type", "roks_cluster_id", "roks_cluster_name", "instance_profile", "cpu_family",
                                                 "numberOfVirtualCPUs", "MemorySizeMiB", "NodeName", "NumberOfGPUs", "NumberOfInstStorageDisks", "availability_zone",
                                                 "instance_role", "metric", "metric_name", "unit", "unit_name", "quantity", "cost", "rated_cost", "rateable_quantity", "estimated_days", "price", "discount"])

    return instancesUsage

def createServiceDetail(paasUsage):
    """
    Write Service Usage detail tab to excel
    """
    logging.info("Creating ServiceUsageDetail tab.")

    paasUsage.to_excel(writer, "ServiceUsageDetail")
    worksheet = writer.sheets['ServiceUsageDetail']
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

def createInstancesDetailTab(instancesUsage):
    """
    Write detail tab to excel
    """
    logging.info("Creating instances detail tab.")

    instancesUsage.to_excel(writer, "Instances_Detail")
    worksheet = writer.sheets['Instances_Detail']
    format1 = workbook.add_format({'num_format': '$#,##0.00'})
    format2 = workbook.add_format({'align': 'left'})
    worksheet.set_column("A:C", 12, format2)
    worksheet.set_column("D:E", 25, format2)
    worksheet.set_column("F:G", 18, format1)
    worksheet.set_column("H:I", 25, format2)
    worksheet.set_column("J:J", 18, format1)
    totalrows,totalcols=instancesUsage.shape
    worksheet.autofilter(0,0,totalrows,totalcols)
    return

def createUsageSummaryTab(paasUsage):
    logging.info("Creating Usage Summary tab.")
    usageSummary = pd.pivot_table(paasUsage, index=["resource_name"],
                                    columns=["month"],
                                    values=["rated_cost", "cost"],
                                    aggfunc=np.sum, margins=True, margins_name="Total",
                                    fill_value=0)
    new_order = ["rated_cost", "cost"]
    usageSummary = usageSummary.reindex(new_order, axis=1, level=0)
    usageSummary.to_excel(writer, 'Usage_Summary')
    worksheet = writer.sheets['Usage_Summary']
    format1 = workbook.add_format({'num_format': '$#,##0.00'})
    format2 = workbook.add_format({'align': 'left'})
    worksheet.set_column("A:A", 35, format2)
    worksheet.set_column("B:ZZ", 18, format1)

def createMetricSummary(paasUsage):
    logging.info("Creating Metric Plan Summary tab.")
    metricSummaryPlan = pd.pivot_table(paasUsage, index=["resource_name", "plan_name", "metric"],
                                 columns=["month"],
                                 values=["quantity", "cost"],
                                 aggfunc=np.sum, margins=True, margins_name="Total",
                                 fill_value=0)
    new_order = ["quantity", "cost"]
    metricSummaryPlan = metricSummaryPlan.reindex(new_order, axis=1, level=0)
    metricSummaryPlan.to_excel(writer, 'MetricPlanSummary')
    worksheet = writer.sheets['MetricPlanSummary']
    format1 = workbook.add_format({'num_format': '$#,##0.00'})
    format2 = workbook.add_format({'align': 'left'})
    format3 = workbook.add_format({'num_format': '#,##0.00000'})
    worksheet.set_column("A:A", 30, format2)
    worksheet.set_column("B:B", 40, format2)
    worksheet.set_column("C:C", 40, format2)
    worksheet.set_column("D:D", 40, format2)
    worksheet.set_column("E:H", 30, format3)
    worksheet.set_column("I:ZZ", 15, format1)
    return

def createClusterTab(instancesUsage):
    """
    Create BM VCPU deployed by role, account, and az
    """

    logging.info("Calculating Clusters.")
    workers = instancesUsage.query('(service_id == "containers-kubernetes")')
    clusters = pd.pivot_table(workers, index=["region",  "roks_cluster_id", "roks_cluster_name", "instance_name", "plan_name", "metric_name", "unit_name"],
                                    columns=["month"],
                                    values=["quantity", "cost"],
                                    aggfunc={"quantity": np.sum, "cost": np.sum},
                                    margins=True, margins_name="Total",
                                    fill_value=0)

    new_order = ["quantity", "cost"]
    clusters = clusters.reindex(new_order, axis=1, level=0)
    clusters.to_excel(writer, 'ClusterDetail')
    worksheet = writer.sheets['ClusterDetail']
    format2 = workbook.add_format({'align': 'left'})
    format1 = workbook.add_format({'num_format': '$#,##0.00'})
    format3 = workbook.add_format({'num_format': '#,##0'})
    worksheet.set_column("A:A", 30, format2)
    worksheet.set_column("B:B", 40, format2)
    worksheet.set_column("C:C", 40, format2)
    worksheet.set_column("D:D", 70, format2)
    worksheet.set_column("E:G", 50, format3)

    return

if __name__ == "__main__":
    setup_logging()
    load_dotenv()
    parser = argparse.ArgumentParser(description="Calculate IBM Cloud Usage.")
    parser.add_argument("--apikey", default=os.environ.get('IC_API_KEY', None), metavar="apikey", help="IBM Cloud API Key")
    parser.add_argument("--output", default=os.environ.get('output', 'ibmCloudUsage.xlsx'), help="Filename Excel output file. (including extension of .xlsx)")
    parser.add_argument("--load", action=argparse.BooleanOptionalAction, help="load dataframes from pkl files.")
    parser.add_argument("--save", action=argparse.BooleanOptionalAction, help="Store dataframes to pkl files.")
    parser.add_argument("--start", help="Start Month YYYY-MM.")
    parser.add_argument("--end", help="End Month YYYY-MM.")
    args = parser.parse_args()
    start = datetime.strptime(args.start, "%Y-%m")
    end = datetime.strptime(args.end, "%Y-%m")
    if args.load:
        logging.info("Retrieving Usage and Instance data stored data")
        accountUsage = pd.read_pickle("accountUsage.pkl")
        instancesUsage = pd.read_pickle("instanceUsage.pkl")
    else:
        if args.apikey == None:
                logging.error("You must provide IBM Cloud ApiKey with view access to usage reporting.")
                quit()
        else:
            apikey = args.apikey
            instancesUsage = pd.DataFrame()
            accountUsage = pd.DataFrame()
            createSDK(apikey)
            accountId = getAccountId(apikey)
            logging.info("Retrieving Usage and Instance data from AccountId: {}.".format(accountId))
            """
            Pre-populate Account Data to accelerate report generation
            """
            tag_cache = prePopulateTagCache()
            resource_cache = prePopulateResourceCache()

            logging.info("Retrieving Usage and Instance data from AccountId: {}.".format(accountId))

            # Get Usage Data via API
            accountUsage = pd.concat([accountUsage, getAccountUsage(start, end)])
            instancesUsage = pd.concat([instancesUsage, getInstancesUsage(start, end)])

            if args.save:
                accountUsage.to_pickle("accountUsage.pkl")
                instancesUsage.to_pickle("instanceUsage.pkl")

    # Write dataframe to excel
    writer = pd.ExcelWriter(args.output, engine='xlsxwriter')
    workbook = writer.book
    createServiceDetail(accountUsage)
    createInstancesDetailTab(instancesUsage)
    createUsageSummaryTab(accountUsage)
    createMetricSummary(accountUsage)
    createClusterTab(instancesUsage)
    writer.close()
    logging.info("Usage Report is complete.")