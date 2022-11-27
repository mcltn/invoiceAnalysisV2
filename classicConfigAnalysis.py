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

import SoftLayer, json, os, argparse, logging, logging.config
import pandas as pd
import numpy as np

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
def getinventory():
    """
    GET DETAILS OF ALL HARDWARE DEVICES IN ACCOUNT
    USE SMALL LIMIT DUE TO SIZE OF DATA RETURNED
    """
    global client

    data = []
    trunkedvlan_data = []
    limit = 10
    offset = 0

    while True:
        hardwarelist = client['Account'].getHardware(id=ims_account, limit=limit, offset=offset, mask='datacenterName,networkVlans,backendRouters,frontendRouters,backendNetworkComponentCount,backendNetworkComponents,'\
                'backendNetworkComponents.router,backendNetworkComponents.router.primaryIpAddress,backendNetworkComponents.uplinkComponent,frontendNetworkComponentCount,frontendNetworkComponents,frontendNetworkComponents.router,'
                'frontendNetworkComponents.router.primaryIpAddress,frontendNetworkComponents.uplinkComponent,uplinkNetworkComponents,networkGatewayMemberFlag,softwareComponents,frontendNetworkComponents.duplexMode,backendNetworkComponents.duplexMode')

        logging.info("Requesting Hardware for account {}, limit={} @ offset {}, returned={}".format(ims_account, limit, offset, len(hardwarelist)))
        if len(hardwarelist) == 0:
            break
        else:
            offset = offset + len(hardwarelist)
        """
        Extract hardware data from json
        """
        for hardware in hardwarelist:
            hardwareid = hardware['id']

            # FIND Index for MGMT Interface and get it's ComponentID Number
            mgmtnetworkcomponent = []
            for backend in hardware['backendNetworkComponents']:
                if backend['name'] == "mgmt":
                    mgmtnetworkcomponent = backend
                    continue

            # OBTAIN INFORMATION ABOUT PRIVATE (BACKEND) INTERFACES
            backendnetworkcomponents = []
            for backend in hardware['backendNetworkComponents']:
                if backend['name'] == "eth":
                    backendnetworkcomponent = backend
                    # Get trunked vlans because relational item doesn't return correctly
                    backendnetworkcomponent['networkVlanTrunks'] = client['Network_Component'].getNetworkVlanTrunks(mask='networkVlan', id=backendnetworkcomponent['uplinkComponent']['id'])
                    backendnetworkcomponents.append(backendnetworkcomponent)

            # FIND INFORMATION ABOUT PUBLIC (FRONTEND) INTERFACES
            frontendnetworkcomponents = []
            for frontend in hardware['frontendNetworkComponents']:
                if frontend['name'] == "eth":
                    frontendnetworkcomponent = frontend
                    frontendnetworkcomponents.append(frontendnetworkcomponent)

            # Get operating system from software components
            if "softwareComponents" in hardware:
                if len(hardware["softwareComponents"]) > 0:
                    os = hardware["softwareComponents"][0]["softwareLicense"]["softwareDescription"]["name"]
                    osversion = hardware["softwareComponents"][0]["softwareLicense"]["softwareDescription"]["version"]
                else:
                    os = ""
                    osversion = ""
            else:
                os = ""
                osversion = ""

            output = {
                "id": hardware['id'],
                "fullyQualifiedDomainName": hardware['fullyQualifiedDomainName'],
                "networkGatewayMemberFlag": hardware['networkGatewayMemberFlag'],
                "operatingSystem": os,
                "version": osversion,
                "datacenterName": hardware['datacenterName'],
                "manufacturerSerialNumber": hardware['manufacturerSerialNumber'],
                "provisionDate": hardware['provisionDate'],
                "notes": hardware['notes']
                }


            #
            # POPULATE TABLE WITH FRONTEND DATA
            #

            """
            Create Columns for each FrontEnd Interface in table
            """
            for frontendnetworkcomponent in frontendnetworkcomponents:
                network = {}
                interface = "{}{}".format(frontendnetworkcomponent['name'], frontendnetworkcomponent['port'])
                network[interface+"_mac"] = frontendnetworkcomponent['macAddress']
                if 'primaryIpAddress' in frontendnetworkcomponent:
                    network[interface+"_primaryIpAddress"] = frontendnetworkcomponent['primaryIpAddress']
                network[interface+"_speed"] = frontendnetworkcomponent['speed']
                network[interface+"_status"] = frontendnetworkcomponent['status']
                network[interface+"_router"] = frontendnetworkcomponent['router']['hostname']
                if 'primaryIpAddress' in frontendnetworkcomponent['router']:
                    network[interface+'_router_ip'] = frontendnetworkcomponent['router']['primaryIpAddress']

                if 'duplexMode' in frontendnetworkcomponent:
                    network[interface+'_duplexMode'] = frontendnetworkcomponent['duplexMode']['keyname']

                if 'networkVlanId' in frontendnetworkcomponent['uplinkComponent']:
                    networkVlanId = frontendnetworkcomponent['uplinkComponent']['networkVlanId']
                else:
                    networkVlanId = 0
                    logging.error("No networkVlanId for frontendnetworkcomponentt:{}".format(frontendnetworkcomponent))

                if len(hardware['networkVlans']) > 0:
                    for networkvlan in hardware['networkVlans']:
                        if networkVlanId == networkvlan['id']:
                            if 'fullyQualifiedName' in networkvlan: network[interface+'_vlan'] = networkvlan['fullyQualifiedName']
                            if 'name' in networkvlan: network[interface+'_vlanName'] = networkvlan['name']
                            if 'vrfDefinitionId' in networkvlan: network[interface+'_vrfId'] = networkvlan['vrfDefinitionId']
                else:
                    logging.error("No vlans hwardware:{}".format(hardware))

                output.update(network)

            """
            POPULATE TABLE WITH BACKEND DATA FOR HARDWARE
               - Private networks
               - Mgmt Network
               - VLAN Trunks
            """
            for backendnetworkcomponent in backendnetworkcomponents:
                network = {}
                interface = "{}{}".format(backendnetworkcomponent['name'], backendnetworkcomponent['port'])
                network[interface+'_mac'] = backendnetworkcomponent['macAddress']
                if 'primaryIpAddress' in backendnetworkcomponent:
                    network[interface+'_primaryIpAddress'] = backendnetworkcomponent['primaryIpAddress']
                network[interface+'_speed'] = backendnetworkcomponent['speed']
                network[interface+'_status'] = backendnetworkcomponent['status']
                if 'duplexMode' in backendnetworkcomponent:
                    network[interface+'_duplexMode'] = backendnetworkcomponent['duplexMode']['keyname']

                if 'networkVlanId' in backendnetworkcomponent['uplinkComponent']:
                    networkVlanId = backendnetworkcomponent['uplinkComponent']['networkVlanId']
                else:
                    networkVlanId = 0
                    logging.error("No networkVlanId for backendnetworkcomponentt:{}".format(backendnetworkcomponent))

                if len(hardware['networkVlans']) > 0:

                    for networkvlan in hardware['networkVlans']:
                        if networkVlanId == networkvlan['id']:
                            if 'fullyQualifiedName' in networkvlan: network[interface+'_vlan'] = networkvlan['fullyQualifiedName']
                            if 'name' in networkvlan: network[interface+'_vlanName'] = networkvlan['name']
                            if 'vrfDefinitionId' in networkvlan: network[interface+'_vrfId'] = networkvlan['vrfDefinitionId']
                else:
                    logging.error("No vlans hwardware:{}".format(hardware))

                network[interface+'_router'] = backendnetworkcomponent['router']['hostname']

                if 'primaryIpAddress' in backendnetworkcomponent['router']:
                    network[interface+'_router_ip'] = backendnetworkcomponent['router']['primaryIpAddress']
                output.update(network)

                """
                IF vlanTrunks exist; write to hardware detail dataframe + create trunkedVlan dataframe
                """
                networkvlanTrunks = ""
                for trunk in backendnetworkcomponent['networkVlanTrunks']:
                    vlanNumber = trunk['networkVlan']['vlanNumber']
                    vlan_fqdn = trunk['networkVlan']['fullyQualifiedName']
                    if 'name' in trunk['networkVlan'].keys():
                        vlanName = trunk['networkVlan']['name']
                    else:
                        vlanName = ""
                    trunkedvlan = "({}) {}".format(vlanNumber, vlanName)
                    if networkvlanTrunks == "":
                        networkvlanTrunks = trunkedvlan
                    else:
                        networkvlanTrunks = networkvlanTrunks + ", " + trunkedvlan
                    """
                    Create ROW in trunkedVLAN table
                    """
                    row = {
                        "datacenterName": output["datacenterName"],
                        "vlanNumber": vlan_fqdn,
                        "vlanName": vlanName,
                        "fullyQualifiedDomainName": output["fullyQualifiedDomainName"],
                        "networkGatewayMemberFlag": output["networkGatewayMemberFlag"],
                        "operatingSystem": output["operatingSystem"],
                        "version": output["version"],
                        "interface": interface
                    }
                    trunkedvlan_data.append(row)

                output[interface+"_networkvlanTrunks"] = networkvlanTrunks

            """
            GET MANAGEMENT NETWORK DETAILS FOR HARDWARE
            """
            network = {}
            if 'name' in mgmtnetworkcomponent:
                interface= "{}{}".format(mgmtnetworkcomponent['name'], mgmtnetworkcomponent['port'])

                if 'ipmiMacAddress' in mgmtnetworkcomponent:
                    network[interface+'_mac'] = mgmtnetworkcomponent['ipmiMacAddress']

                if 'ipmiIpAddress' in mgmtnetworkcomponent:
                    network[interface+'_primaryIpAddress'] = mgmtnetworkcomponent['ipmiIpAddress']

                if 'speed' in mgmtnetworkcomponent:
                    network[interface+'_speed'] = mgmtnetworkcomponent['speed']

                if 'status' in mgmtnetworkcomponent:
                    network[interface+'_status'] = mgmtnetworkcomponent['status']

                if 'duplexMode' in mgmtnetworkcomponent:
                    network[interface + '_duplexMode'] = mgmtnetworkcomponent['duplexMode']['keyname']

                if 'networkVlanId' in mgmtnetworkcomponent['uplinkComponent']:
                    networkVlanId = mgmtnetworkcomponent['uplinkComponent']['networkVlanId']
                else:
                    networkVlanId = ""
                    logging.error("No networkVlanId for mgmtnetworkcomponentt:{}".format(mgmtnetworkcomponent))

                if len(hardware['networkVlans']) > 0:
                    for networkvlan in hardware['networkVlans']:
                        if networkVlanId == networkvlan['id']:
                            if 'fullyQualifiedName' in networkvlan: network[interface + '_vlan'] = networkvlan['fullyQualifiedName']
                            if 'name' in networkvlan: network[interface + '_vlanName'] = networkvlan['name']
                            if 'vrfDefinitionId' in networkvlan: network[interface + '_vrfId'] = networkvlan['vrfDefinitionId']
                else:
                    logging.error("No vlans hwardware:{}".format(hardware))

                if 'router' in mgmtnetworkcomponent:
                    if 'hostname' in mgmtnetworkcomponent['router']:
                        network[interface+'_router'] = mgmtnetworkcomponent['router']['hostname']

                    if 'primaryIpAddress' in mgmtnetworkcomponent['router']:
                        network[interface+'_router_ip'] = mgmtnetworkcomponent['router']['primaryIpAddress']

                output.update(network)
            else:
                logging.error("No Mgmt Network for hardware: {}".format(hardware))

            """
            Write hardware details to table
            """
            data.append(output.copy())

    hw_columns = [
        "id",
        "networkGatewayMemberFlag",
        "fullyQualifiedDomainName",
        "operatingSystem",
        "version",
        "datacenterName",
        "manufacturerSerialNumber",
        "provisionDate",
        "notes",
        "eth1_mac",
        "eth1_primaryIpAddress",
        "eth1_speed",
        "eth1_duplexMode",
        "eth1_status",
        "eth1_router",
        "eth1_router_ip",
        "eth1_vlan",
        "eth1_vlanName",
        "eth1_vrfId",
        "eth3_mac",
        "eth3_speed",
        "eth3_status",
        "eth3_router",
        "eth3_router_ip",
        "eth3_vlan",
        "eth3_vlanName",
        "eth0_mac",
        "eth0_primaryIpAddress",
        "eth0_speed",
        "eth0_duplexMode",
        "eth0_status",
        "eth0_vlan",
        "eth0_vlanName",
        "eth0_vrfId",
        "eth0_router",
        "eth0_router_ip",
        "eth0_networkvlanTrunks",
        "eth2_mac",
        "eth2_speed",
        "eth2_duplexMode",
        "eth2_status",
        "eth2_vlan",
        "eth2_vlanName",
        "eth1_vrfId",
        "eth2_router",
        "eth2_router_ip",
        "eth2_networkvlanTrunks",
        "eth4_mac",
        "eth4_speed",
        "eth4_duplexMode",
        "eth4_status",
        "eth4_vlan",
        "eth4_vlanName",
        "eth4_vrfId",
        "eth4_router",
        "eth4_router_ip",
        "eth4_networkvlanTrunks",
        "eth5_mac",
        "eth5_duplexMode",
        "eth5_speed",
        "eth5_status",
        "eth5_vlan",
        "eth5_vlanName",
        "eth5_vrfId",
        "eth5_router",
        "eth5_router_ip",
        "eth5_networkvlanTrunks",
        "eth6_mac",
        "eth6_duplexMode",
        "eth6_speed",
        "eth6_status",
        "eth6_vlan",
        "eth6_vlanName",
        "eth6_vrfId",
        "eth6_router",
        "eth6_router_ip",
        "eth6_networkvlanTrunks",
        "eth7_mac",
        "eth7_speed",
        "eth7_duplexMode",
        "eth7_status",
        "eth7_vlan",
        "eth7_vlanName",
        "eth7_vrfId",
        "eth7_router",
        "eth7_router_ip",
        "eth7_networkvlanTrunks",
        "eth8_mac",
        "eth8_speed",
        "eth8_duplexMode",
        "eth8_status",
        "eth8_vlan",
        "eth8_vlanName",
        "eth8_vrfId",
        "eth8_router",
        "eth8_router_ip",
        "eth8_networkvlanTrunks",
        "eth9_mac",
        "eth9_speed",
        "eth9_duplexMode",
        "eth9_status",
        "eth9_vlan",
        "eth9_vlanName",
        "eth9_vrfId",
        "eth9_router",
        "eth9_router_ip",
        "eth9_networkvlanTrunks",
        "eth10_mac",
        "eth10_speed",
        "eth10_duplexMode",
        "eth10_status",
        "eth10_vlan",
        "eth10_vlanName",
        "eth10_vrfId",
        "eth10_router",
        "eth10_router_ip",
        "eth10_networkvlanTrunks",
        "mgmt0_mac",
        "mgmt0_primaryIpAddress",
        "mgmt0_speed",
        "mgmt0_duplexMode",
        "mgmt0_status",
        "mgmt0_vlan",
        "mgmt0_vlanName",
        "mgmt0_router",
        "mgmt0_router_ip",
    ]
    hardware_df = pd.DataFrame(data,columns=hw_columns)
    trunkedvlan_df = pd.DataFrame(trunkedvlan_data)

    return hardware_df, trunkedvlan_df

def createHWDetail(hardware_df):
    """
    Write detail tab to excel
    """
    logging.info("Creating detail tab from hardware dataframe.")
    # Write dataframe to excel

    hardware_df.to_excel(writer, "HW_Detail")
    worksheet = writer.sheets['HW_Detail']
    totalrows,totalcols=hardware_df.shape
    worksheet.autofilter(0,0,totalrows,totalcols)
    return

def createVlanDetail(trunkedvlan_df):
    """
    Write detail tab to excel
    """
    logging.info("Creating detail tab from Trunked VLAN dataframe.")
    # Write dataframe to excel
    trunkedvlan_df.to_excel(writer, "trunkedVLAN_Detail")
    worksheet = writer.sheets['trunkedVLAN_Detail']
    leftformat = workbook.add_format({'align': 'left'})
    worksheet.set_column("B:B", 20, leftformat)
    worksheet.set_column("C:C", 20, leftformat)
    worksheet.set_column("D:D", 40, leftformat)
    worksheet.set_column("E:E", 60, leftformat)
    worksheet.set_column("F:F", 10, leftformat)
    totalrows,totalcols=trunkedvlan_df.shape
    worksheet.autofilter(0,0,totalrows,totalcols)
    return

def createServersByTrunkedVlan(trunkedvlan_df):
    """
    Create a Pivot of list of Servers per tagged VLAN
    """

    logging.info("Creating Servers by TrunkedVLAN pivot table.")
    vlanpivot = pd.pivot_table(trunkedvlan_df, index=["datacenterName", "vlanNumber", "vlanName",  "fullyQualifiedDomainName", "networkGatewayMemberFlag", "operatingSystem", "version"],
                               values=["interface"],
                               aggfunc={"interface": "nunique"}, margins=True, margins_name="Count", fill_value=0).reset_index()
    vlanpivot.to_excel(writer, 'ServersByTrunkedVlanPivot')
    worksheet = writer.sheets['ServersByTrunkedVlanPivot']
    leftformat = workbook.add_format({'align': 'left'})
    worksheet.set_column("A:A", 5, leftformat)
    worksheet.set_column("B:B", 20, leftformat)
    worksheet.set_column("C:C", 40, leftformat)
    worksheet.set_column("D:D", 60, leftformat)
    worksheet.set_column("E:E", 60, leftformat)
    worksheet.set_column("F:I", 20, leftformat)
    totalrows,totalcols=trunkedvlan_df.shape
    worksheet.autofilter(0,0,totalrows,totalcols)

    return

def createServersbyOsPivot(hardware_df):
    """
    Create a list of server for each OS
    """
    logging.info("Creating Servers by OS table.")
    vlanpivot = pd.pivot_table(hardware_df, index=["operatingSystem", "version", "fullyQualifiedDomainName"],
                               values=["id"],
                               aggfunc={"id": "nunique"}, margins=True, margins_name="Count", fill_value=0).reset_index()
    vlanpivot.to_excel(writer, 'ServerByOSPivot')
    worksheet = writer.sheets['ServerByOSPivot']
    leftformat = workbook.add_format({'align': 'left'})
    worksheet.set_column("A:A", 10, leftformat)
    worksheet.set_column("B:B", 30, leftformat)
    worksheet.set_column("C:C", 30, leftformat)
    worksheet.set_column("D:D", 60, leftformat)
    totalrows,totalcols=trunkedvlan_df.shape
    worksheet.autofilter(0,0,totalrows,totalcols)

def createTaggedVlanbyServersPivot(hardware_df):
    """
    Create a list of server for each OS
    """
    logging.info("Creating TaggedVlan by Server table.")
    vlanpivot = pd.pivot_table(hardware_df, index=["fullyQualifiedDomainName",  "operatingSystem", "version", "datacenterName", "vlanNumber", "vlanName"],
                               values=["interface"],
                               aggfunc={"interface": "nunique"}, margins=True, margins_name="Count", fill_value=0).reset_index()
    vlanpivot.to_excel(writer, 'TaggedVlanByServer')
    worksheet = writer.sheets['TaggedVlanByServer']
    leftformat = workbook.add_format({'align': 'left'})
    worksheet.set_column("A:A", 10, leftformat)
    worksheet.set_column("B:B", 30, leftformat)
    worksheet.set_column("C:C", 30, leftformat)
    worksheet.set_column("D:D", 20, leftformat)
    worksheet.set_column("E:H", 30, leftformat)
    totalrows,totalcols=trunkedvlan_df.shape
    worksheet.autofilter(0,0,totalrows,totalcols)

if __name__ == "__main__":
    setup_logging()

    parser = argparse.ArgumentParser(description="Configuration Report prints details of BareMetal Servers such as Network, VLAN, and hardware configuration")
    parser.add_argument("-u", "--username", default=os.environ.get('ims_username', None), metavar="username",
                        help="IMS Userid")
    parser.add_argument("-p", "--password", default=os.environ.get('ims_password', None), metavar="password",
                        help="IMS Password")
    parser.add_argument("-a", "--account", default=os.environ.get('ims_account', None), metavar="account",
                        help="IMS Account")
    parser.add_argument("-k", "--IC_API_KEY", default=os.environ.get('IC_API_KEY', None), metavar="apikey",
                        help="IBM Cloud API Key")
    parser.add_argument("--output", default=os.environ.get('output', 'config-report.xlsx'), help="Excel filename for output file. (including extension of .xlsx)")
    parser.add_argument("--load", action=argparse.BooleanOptionalAction, help="load dataframes from pkl files.")
    parser.add_argument("--save", action=argparse.BooleanOptionalAction, help="Store dataframes to pkl files.")

    args = parser.parse_args()

    if args.load:
        logging.info("Retrieving Usage and Instance data stored data")
        hardware_df = pd.read_pickle("hardware.pkl")
        trunkedvlan_df = pd.read_pickle("trunkedvlan.pkl")
    else:
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

        """
        Using Account API retrieve Baremetal Server Inventory for account.
        """
        hardware_df, trunkedvlan_df = getinventory()

    if args.save:
        logging.info("Saving dataframes to pickle file.")
        hardware_df.to_pickle("hardware.pkl")
        trunkedvlan_df.to_pickle("trunkedvlan.pkl")

    logging.info("Creating {} output file.".format(args.output))
    # Write dataframe to excel

    writer = pd.ExcelWriter(args.output, engine='xlsxwriter')
    workbook = writer.book

    createHWDetail(hardware_df)
    createVlanDetail(trunkedvlan_df)
    createServersByTrunkedVlan(trunkedvlan_df)
    createTaggedVlanbyServersPivot(trunkedvlan_df)
    createServersbyOsPivot(hardware_df)
    writer.save()






