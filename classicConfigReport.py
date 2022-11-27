##
## Account Bare Metal Configuration Report
## Place APIKEY & Username in config.ini
## or pass via commandline  (example: ConfigurationReport.py -u=userid -k=apikey)
##

import SoftLayer, json, os, argparse, logging, logging.config

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

def output(line):
    
    global f
    #print (line)
    f.write(line)
    f.write("\n")
    return

class TablePrinter(object):
    #
    # FORMAT TABLE
    #
    "Print a list of dicts as a table"

    def __init__(self, fmt, sep=' ', ul=None):
        """        
        @param fmt: list of tuple(heading, key, width)
                        heading: str, column label
                        key: dictionary key to value to print
                        width: int, column width in chars
        @param sep: string, separation between columns
        @param ul: string, character to underline column label, or None for no underlining
        """
        super(TablePrinter, self).__init__()
        self.fmt = str(sep).join('{lb}{0}:{1}{rb}'.format(key, width, lb='{', rb='}') for heading, key, width in fmt)
        self.head = {key: heading for heading, key, width in fmt}
        self.ul = {key: str(ul) * width for heading, key, width in fmt} if ul else None
        self.width = {key: width for heading, key, width in fmt}

    def row(self, data):
        return self.fmt.format(**{k: str(data.get(k, ''))[:w] for k, w in self.width.items()})

    def __call__(self, dataList):
        _r = self.row
        res = [_r(data) for data in dataList]
        res.insert(0, _r(self.head))
        if self.ul:
            res.insert(1, _r(self.ul))
        return '\n'.join(res)


if __name__ == "__main__":
    ## READ CommandLine Arguments and load configuration file
    parser = argparse.ArgumentParser(description="Configuration Report prints details of BareMetal Servers such as Network, VLAN, and hardware configuration")
    parser.add_argument("-u", "--username", default=os.environ.get('ims_username', None), metavar="username",
                        help="IMS Userid")
    parser.add_argument("-p", "--password", default=os.environ.get('ims_password', None), metavar="password",
                        help="IMS Password")
    parser.add_argument("-a", "--account", default=os.environ.get('ims_account', None), metavar="account",
                        help="IMS Account")
    parser.add_argument("-k", "--IC_API_KEY", default=os.environ.get('IC_API_KEY', None), metavar="apikey",
                        help="IBM Cloud API Key")
    parser.add_argument("-c", "--config", help="config.ini file to load")
    parser.add_argument("--output", default=os.environ.get('output', 'config-report.txt'),
                       help="Text filename for output file. (including extension of .txt)")

    args = parser.parse_args()

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

    setup_logging()
    # BUILD TABLES
    #
    networkFormat = [
        ('Iface', 'interface', 6),
        ('MAC ', 'macAddress', 17),
        ('IpAddress', 'primaryIpAddress', 16),
        ('Speed', 'speed', 5),
        ('Duplex', 'duplexMode', 6),
        ('Status', 'status', 8),
        ('Vlan', 'vlan', 5),
        ('FQDN', 'vlan_fqdn',16),
        ('Vlan Name', 'vlanName', 20),
        ('Router', 'router', 14),
        ('RouterIP', 'router_ip', 16),
        ('VRF_ID', 'vrfDefinitionId',8)
    ]

    serverFormat = [
        ('Type   ', 'devicetype', 15),
        ('Manufacturer', 'manufacturer', 15),
        ('Name', 'name', 20),
        ('Description', 'description', 30),
        ('Modify Date', 'modifydate', 25),
        ('Serial Number', 'serialnumber', 15)
    ]

    trunkFormat = [
        ('Interface', 'interface', 10),
        ('Vlan', 'fqdn', 16),
        ('VlanName', 'vlanName', 25)
    ]

    storageFormat = [
        ('StorageType', 'type', 11),
        ('Address', 'address', 40),
        ('Gb', 'capacity', 10),
        ('IOPS', 'iops', 10),
        ('Notes', 'notes', 50)
    ]

    """
    GET DETAILS OF ALL HARDWARE DEVICES IN ACCOUNT
    USE SMALL LIMIT DUE TO SIZE OF DATA RETURNED
    """

    with open(args.output, 'w') as f:

        limit = 10
        offset = 0
        while True:
            hardwarelist = client['Account'].getHardware(id=ims_account, limit=limit, offset=offset, mask='datacenterName,networkVlans,backendRouters,frontendRouters,backendNetworkComponentCount,backendNetworkComponents,'\
                    'backendNetworkComponents.router,backendNetworkComponents.router.primaryIpAddress,backendNetworkComponents.duplexMode,backendNetworkComponents.uplinkComponent,frontendNetworkComponentCount,frontendNetworkComponents,frontendNetworkComponents.router,'
                    'frontendNetworkComponents.duplexMode,frontendNetworkComponents.router.primaryIpAddress,frontendNetworkComponents.uplinkComponent,uplinkNetworkComponents,activeComponents,networkGatewayMemberFlag,softwareComponents')

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
                        #frontendnetworkcomponent = client['Network_Component'].getObject(mask="router, uplinkComponent", id=frontend['id'])
                        frontendnetworkcomponent = frontend
                        # Get trunked vlans
                        #frontendnetworkcomponent['trunkedvlans'] = client['Network_Component'].getNetworkVlanTrunks(
                        #    mask='networkVlan', id=frontendnetworkcomponent['uplinkComponent']['id'])
                        frontendnetworkcomponents.append(frontendnetworkcomponent)

                if "softwareComponents" in hardware:
                    if len(hardware["softwareComponents"])>0:
                        os = hardware["softwareComponents"][0]["softwareLicense"]["softwareDescription"]["name"]
                        osversion = hardware["softwareComponents"][0]["softwareLicense"]["softwareDescription"]["version"]
                    else:
                        os = ""
                else:
                    os = ""

                output(
                    "__________________________________________________________________________________________________________________")
                output("")
                output("Id              : %s" % (hardware['id']))
                output("Hostname        : %s" % (hardware['fullyQualifiedDomainName']))
                output("Operating System: %s" % os)
                output("OS Version      : %s" % osversion)
                output("Gateway Member  : %s" % (hardware['networkGatewayMemberFlag']))
                output("Datacenter      : %s" % (hardware['datacenterName']))
                output("Serial #        : %s" % (hardware['manufacturerSerialNumber']))
                output("Provision Date  : %s" % (hardware['provisionDate']))
                output("Notes           : %s" % (hardware['notes']))
                output("")
                #
                # POPULATE TABLE WITH COMPONENT DATA
                #

                #result = client['Hardware'].getComponents(id=hardwareid)
                data = []
                for device in hardware["activeComponents"]:
                    hwdevice = {}
                    hwdevice['devicetype'] = \
                        device['hardwareComponentModel']['hardwareGenericComponentModel']['hardwareComponentType']['type']
                    hwdevice['manufacturer'] = device['hardwareComponentModel']['manufacturer']
                    hwdevice['name'] = device['hardwareComponentModel']['name']
                    hwdevice['description'] = device['hardwareComponentModel']['hardwareGenericComponentModel'][
                        'description']
                    hwdevice['modifydate'] = device['modifyDate']
                    if 'serialNumber' in device.keys(): hwdevice['serialnumber'] = device['serialNumber']
                    data.append(hwdevice)
                output(TablePrinter(serverFormat, ul='=')(data))

                output(
                    "__________________________________________________________________________________________________________________")


                #
                # POPULATE TABLE WITH FRONTEND DATA
                #

                output("")
                output("FRONTEND NETWORK")
                data = []
                network = {}
                for frontendnetworkcomponent in frontendnetworkcomponents:
                    network = {}
                    network['interface'] = "{}{}".format(frontendnetworkcomponent['name'], frontendnetworkcomponent['port'])

                    if 'macAddress' in frontendnetworkcomponent:
                        network['macAddress'] = frontendnetworkcomponent['macAddress']

                    if 'primaryIpAddress' in frontendnetworkcomponent:
                        network['primaryIpAddress'] = frontendnetworkcomponent['primaryIpAddress']

                    if 'speed' in frontendnetworkcomponent:
                        network['speed'] = frontendnetworkcomponent['speed']

                    if 'status' in frontendnetworkcomponent:
                        network['status'] = frontendnetworkcomponent['status']

                    if 'router' in frontendnetworkcomponent:
                        network['router'] = frontendnetworkcomponent['router']['hostname']

                    if 'primaryIpAddress' in frontendnetworkcomponent['router']:
                        network['router_ip'] = frontendnetworkcomponent['router']['primaryIpAddress']

                    if 'duplexMode' in frontendnetworkcomponent:
                        network['duplexMode'] = frontendnetworkcomponent['duplexMode']['keyname']

                    if 'networkVlanId' in frontendnetworkcomponent['uplinkComponent']:
                        network['networkVlanId'] = frontendnetworkcomponent['uplinkComponent']['networkVlanId']
                    else:
                        logging.error("No networkVlanId for frontendnetworkcomponent:{}".format(frontendnetworkcomponent))

                    if len(hardware['networkVlans']) > 0:
                        for networkvlan in hardware['networkVlans']:
                            if network['networkVlanId'] == networkvlan['id']:
                                if 'vlanNumber' in networkvlan: network['vlan'] = networkvlan['vlanNumber']
                                if 'fullyQualifiedName' in networkvlan: network['vlan_fqdn'] = networkvlan['fullyQualifiedName']
                                if 'name' in networkvlan: network['vlanName'] = networkvlan['name']
                                if 'vrfDefinitionId' in networkvlan: network['vrfDefinitionId'] = networkvlan['vrfDefinitionId']
                    else:
                        logging.error("No vlans hwardware:{}".format(hardware))

                    data.append(network)
                output(TablePrinter(networkFormat, ul='=')(data))

                #
                # POPULATE TABLE WITH BACKEND DATA
                #

                interfacedata = []
                trunkdata = []
                for backendnetworkcomponent in backendnetworkcomponents:
                    network = {}
                    network['interface'] = "{}{}".format(backendnetworkcomponent['name'], backendnetworkcomponent['port'])

                    if 'macAddress' in backendnetworkcomponent:
                        network['macAddress'] = backendnetworkcomponent['macAddress']
                    if 'primaryIpAddress' in backendnetworkcomponent:
                        network['primaryIpAddress'] = backendnetworkcomponent['primaryIpAddress']
                    if 'speed' in backendnetworkcomponent:
                        network['speed'] = backendnetworkcomponent['speed']
                    if 'status' in backendnetworkcomponent:
                        network['status'] = backendnetworkcomponent['status']

                    # find matching VLAN
                    if 'networkVlanId' in backendnetworkcomponent['uplinkComponent']:
                        network['networkVlanId'] = backendnetworkcomponent['uplinkComponent']['networkVlanId']
                    else:
                        logging.error("No networkVlanId for backendnetworkcomponent:{}".format(backendnetworkcomponent))

                    if len(hardware['networkVlans']) > 0:
                        for networkvlan in hardware['networkVlans']:
                            if network['networkVlanId'] == networkvlan['id']:
                                if 'vlanNumber' in networkvlan: network['vlan'] = networkvlan['vlanNumber']
                                if 'fullyQualifiedName' in networkvlan: network['vlan_fqdn'] = networkvlan['fullyQualifiedName']
                                if 'name' in networkvlan: network['vlanName'] = networkvlan['name']
                                if 'vrfDefinitionId' in networkvlan: network['vrfDefinitionId'] = networkvlan['vrfDefinitionId']
                    else:
                        logging.error("No vlans hwardware:{}".format(hardware))

                    if 'router' in backendnetworkcomponent:
                        if 'hostname' in backendnetworkcomponent['router']:
                            network['router'] = backendnetworkcomponent['router']['hostname']

                    if 'primaryIpAddress' in backendnetworkcomponent['router']:
                        network['router_ip'] = backendnetworkcomponent['router']['primaryIpAddress']

                    if 'duplexMode' in backendnetworkcomponent:
                        network['duplexMode'] = backendnetworkcomponent['duplexMode']['keyname']

                    interfacedata.append(network)

                    for trunk in backendnetworkcomponent['networkVlanTrunks']:
                        trunkedvlan = {}
                        trunkedvlan['interface'] = network['interface']
                        trunkedvlan['vlanNumber'] = trunk['networkVlan']['vlanNumber']
                        trunkedvlan['fqdn'] = trunk['networkVlan']['fullyQualifiedName']
                        if 'name' in trunk['networkVlan']:
                            trunkedvlan['vlanName'] = trunk['networkVlan']['name']
                        trunkdata.append(trunkedvlan)

                output("")
                output("BACKEND NETWORK INTERFACE(S)")
                output(TablePrinter(networkFormat, ul='=')(interfacedata))
                output("")
                output("TAGGED VLANS BY INTERFACE")
                output(TablePrinter(trunkFormat, ul='=')(trunkdata))

                """
                GET MANAGEMENT NETWORK DETAILS FOR HARDWARE
                """""
                output("")
                output("MGMT NETWORK")
                data = []
                network = {}

                # Check if there is a Mgmt Network
                if 'name' in mgmtnetworkcomponent:
                    network['interface'] = "{}{}".format(mgmtnetworkcomponent['name'], mgmtnetworkcomponent['port'])

                    if 'ipmiMacAddress' in mgmtnetworkcomponent:
                        network['macAddress'] = mgmtnetworkcomponent['ipmiMacAddress']


                    if 'ipmiIpAddress' in mgmtnetworkcomponent:
                        network['primaryIpAddress'] = mgmtnetworkcomponent['ipmiIpAddress']
                    else:
                        network['primaryIpAddress'] = ""

                    if 'speed' in mgmtnetworkcomponent:
                        network['speed'] = mgmtnetworkcomponent['speed']

                    if 'status' in mgmtnetworkcomponent:
                        network['status'] = mgmtnetworkcomponent['status']

                    if 'duplexMode' in mgmtnetworkcomponent:
                        network['duplexMode'] = mgmtnetworkcomponent['duplexMode']['keyname']

                    # find matching VLAN

                    if 'networkVlanId' in mgmtnetworkcomponent['uplinkComponent']:
                        network['networkVlanId'] = mgmtnetworkcomponent['uplinkComponent']['networkVlanId']
                    else:
                        logging.error("No networkVlanId for mgmtnetworkcomponentt:{}".format(mgmtnetworkcomponent))


                    if len(hardware['networkVlans']) > 0:
                        for networkvlan in hardware['networkVlans']:
                            if network['networkVlanId'] == networkvlan['id']:
                                if 'vlanNumber' in networkvlan: network['vlan'] = networkvlan['vlanNumber']
                                if 'fullyQualifiedName' in networkvlan: network['vlan_fqdn'] = networkvlan['fullyQualifiedName']
                                if 'name' in networkvlan: network['vlanName'] = networkvlan['name']
                                if 'vrfDefinitionId' in networkvlan: network['vrfDefinitionId'] = networkvlan['vrfDefinitionId']
                    else:
                        logging.error("No vlans hwardware:{}".format(hardware))

                    if 'router' in mgmtnetworkcomponent:
                        if 'hostname' in mgmtnetworkcomponent['router']:
                            network['router'] = mgmtnetworkcomponent['router']['hostname']

                        if 'primaryIpAddress' in mgmtnetworkcomponent['router']:
                            network['router_ip'] = mgmtnetworkcomponent['router']['primaryIpAddress']

                    data.append(network)
                else:
                    logging.error("No Mgmt Network for hardware: {}".format(hardware))

                output(TablePrinter(networkFormat, ul='=')(data))
                output("")

                #
                # GET NETWORK STORAGE
                #

                storagealloc = client['Hardware'].getAllowedNetworkStorage(mask="iops", id=hardwareid)
                if len(storagealloc) > 0:
                    data = []
                    for storage in storagealloc:
                        storagerow = {}
                        storagerow['type'] = storage['nasType']
                        if 'serviceResourceBackendIpAddress' in storage.keys():
                            storagerow['address'] = storage['serviceResourceBackendIpAddress']
                            storagerow['capacity'] = storage['capacityGb']
                            if 'iops' in storage:
                                storagerow['iops'] = storage['iops']
                            else:
                                storagerow['iops'] = ""
                        if 'notes' in storage.keys(): storagerow['notes'] = storage['notes']
                        data.append(storagerow)
                    output("")
                    output("NETWORK STORAGE ASSOCIATED WITH HARDWARE")
                    output(TablePrinter(storageFormat, ul='=')(data))
                    output("")

                output("")
    f.close()

