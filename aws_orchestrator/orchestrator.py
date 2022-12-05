import yaml
import boto3


class AWSOrchestrator:
    def __init__(self, config_file):
        self.procs = []
        self.ec2 = boto3.resource('ec2')
        self.ec2Client = boto3.client('ec2')
        with open(config_file, 'r') as fh:
            self.config = yaml.load(fh, yaml.CSafeLoader)
        self.instances = self.config['instances']
        self.tags = []
        for key in self.config['tags'].keys():
            self.tags.append({'Key': key, 'Value': self.config['tags'][key]})

    def list_ip_addesses(self):
        filter = []
        for key in self.config['tags'].keys():
            filter.append({'Name': 'tag:%s' % key, 'Values': [self.config['tags'][key]]})
        response = self.ec2Client.describe_instances(Filters=filter)
        reservations = response['Reservations']
        if len(response['Reservations']):
            instances = response['Reservations'][0]['Instances']
            for i in range(len(reservations)):
                instances = response['Reservations'][i]['Instances']
                for k in range(len(instances)):
                    if instances[k]['State']['Name'] != 'running':
                        continue
                    tags = instances[k]['Tags']
                    name = ''
                    for i in range(len(tags)):
                        if tags[i]['Key'] == 'VMName':
                            name = tags[i]['Value']
                    print("%s: ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ubuntu@%s" % (name, instances[k]['PublicIpAddress']))

    def destroy_instances(self):
        filter = []
        for key in self.config['tags'].keys():
            filter.append({'Name': 'tag:%s' % key, 'Values': [self.config['tags'][key]]})
        response = self.ec2Client.describe_instances(Filters=filter)
        ids = []
        reservations = response['Reservations']
        if len(response['Reservations']):
            instances = response['Reservations'][0]['Instances']
            for i in range(len(reservations)):
                instances = response['Reservations'][i]['Instances']
                for k in range(len(instances)):
                    ids.append(instances[k]['InstanceId'])

        self.ec2.instances.filter(InstanceIds=ids).terminate()
        waiter = self.ec2Client.get_waiter('instance_terminated')
        waiter.wait(InstanceIds=ids)

    def destroy_environment(self):
        filter = []
        for key in self.config['tags'].keys():
            filter.append({'Name': 'tag:%s' % key, 'Values': [self.config['tags'][key]]})
        response = self.ec2Client.describe_vpcs(Filters=filter)
        vpcs = response['Vpcs']
        for i in range(len(vpcs)):
            vpcid = vpcs[i]['VpcId']
            vpc_resource = self.ec2.Vpc(vpcid)
            igws = vpc_resource.internet_gateways.all()
            for igw in igws:
                igw.detach_from_vpc(VpcId=vpcid)
                igw.delete()
            subnets = vpc_resource.subnets.all()
            for sub in subnets:
                sub.delete()
            rtbs = vpc_resource.route_tables.all()
            for rtb in rtbs:
                if len(rtb.associations_attribute) and rtb.associations_attribute[0]['Main']:
                    continue
                self.ec2.RouteTable(rtb.id).delete()
            sgps = vpc_resource.security_groups.all()
            for sg in sgps:
                if sg.group_name == 'default':
                    continue
                sg.delete()
            vpc_resource.delete()

    def create_vpc(self):
        vpc = self.ec2.create_vpc(CidrBlock='10.240.0.0/16')
        vpc.modify_attribute(EnableDnsSupport={'Value': True})
        vpc.modify_attribute(EnableDnsHostnames={'Value': True})
        intGateway = self.ec2.create_internet_gateway()
        intGateway.attach_to_vpc(VpcId=vpc.id)
        vpc.create_tags(Tags=self.tags)
        intGateway.create_tags(Tags=self.tags)
        routeTable = self.ec2.create_route_table(VpcId=vpc.id)
        self.pubSecGrp = self.ec2.create_security_group(DryRun=False,
                                                        GroupName='%s' % self.config['tags']['Environment'],
                                                        Description='Public_Security_Group',
                                                        VpcId=vpc.id
                                                        )
        self.pubSecGrp.create_tags(Tags=self.tags)
        self.ec2Client.authorize_security_group_ingress(GroupId=self.pubSecGrp.id,
                                                        IpProtocol='tcp',
                                                        FromPort=22,
                                                        ToPort=22,
                                                        CidrIp='0.0.0.0/0'
                                                        )

        self.pubsubnet = vpc.create_subnet(CidrBlock='10.240.1.0/24')
        self.pubsubnet.create_tags(Tags=self.tags)
        SubnetRoute = routeTable.associate_with_subnet(SubnetId=self.pubsubnet.id)
        intRoute = self.ec2Client.create_route(RouteTableId=routeTable.id, DestinationCidrBlock='0.0.0.0/0', GatewayId=intGateway.id)
        routeTable.create_tags(Tags=self.tags)

    def create_instance(self, vm_name, user_data):
        ec2_instance = self.ec2.create_instances(ImageId=self.instances[vm_name]['AMI_ID'],
                                                 MinCount=1,
                                                 MaxCount=1,
                                                 KeyName=self.config['KeyName'],
                                                 UserData=user_data,
                                                 InstanceType=self.instances[vm_name]['InstanceType'],
                                                 NetworkInterfaces=[
                                                    {
                                                     'SubnetId': self.pubsubnet.id,
                                                     'Groups': [self.pubSecGrp.id],
                                                     'DeviceIndex': 0,
                                                     'DeleteOnTermination': True,
                                                     'AssociatePublicIpAddress': True,
                                                    }
                                                 ]
                                                )
        return {'EC2': ec2_instance, 'VMName': vm_name}

    def deploy_environment(self):
        build = {}
        for inst in self.instances:
            build[inst] = {}
            if 'git_repos' in self.instances[inst]:
                build[inst]['git_repos'] = self.instances[inst]['git_repos']
            if 'build_scripts' in self.instances[inst]:
                build[inst]['build_scripts'] = self.instances[inst]['build_scripts']
        run = {}
        for inst in self.instances:
            run[inst] = {}
            if 'run_scripts' in self.instances[inst]:
                run[inst]['run_scripts'] = self.instances[inst]['run_scripts']
        instanceLst = []
        for vm_name in build:
            build_script = "#!/bin/bash\n\n"
            build_script = "%s%s" % (build_script, "cat > /home/ubuntu/%s_build.sh << EOF\n" % vm_name)
            build_script = "%s%s" % (build_script, "#!/bin/bash\n\n")
            build_script = "%s%s" % (build_script, "echo aws-orchestrator build started \$(date) >> /home/ubuntu/.build_out.log\n\n")
            if 'git_repos' in build[vm_name]:
                for i in range(len(build[vm_name]['git_repos'])):
                    build_script = "%s%s" % (build_script, "git clone %s\n\n" % build[vm_name]['git_repos'][i])
            if 'build_scripts' in build[vm_name]:
                for i in range(len(build[vm_name]['build_scripts'])):
                    build_cmd = "%s 2>> /home/ubuntu/.build_err.log >> /home/ubuntu/.build_out.log\n" % build[vm_name]['build_scripts'][i]
                    build_script = "%s%s" % (build_script, build_cmd)
            build_script = "%s%s" % (build_script, "echo aws-orchestrator build ended \$(date) >> /home/ubuntu/.build_out.log\n\n")
            build_script = "%s%s" % (build_script, "EOF\n\n")
            build_script = "%s%s" % (build_script, "chmod +x /home/ubuntu/%s_build.sh\n" % vm_name)
            build_script = "%s%s" % (build_script, "cat > /home/ubuntu/%s_run.sh << EOF\n" % vm_name)
            build_script = "%s%s" % (build_script, "#!/bin/bash\n\n")
            build_script = "%s%s" % (build_script, "echo aws-orchestrator run started \$(date) >> /home/ubuntu/.run_out.log\n\n")
            if 'run_scripts' in run[vm_name]:
                for i in range(len(run[vm_name]['run_scripts'])):
                    build_cmd = "%s 2>> /home/ubuntu/.run_err.log >> /home/ubuntu/.run_out.log\n" % run[vm_name]['run_scripts'][i]
                    build_script = "%s%s" % (build_script, build_cmd)
            build_script = "%s%s" % (build_script, "echo aws-orchestrator run ended \$(date) >> /home/ubuntu/.run_out.log\n\n")
            build_script = "%s%s" % (build_script, "EOF\n\n")
            build_script = "%s%s" % (build_script, "chmod +x /home/ubuntu/%s_run.sh\n" % vm_name)
            build_script = "%s%s" % (build_script, "sudo -H -u ubuntu bash -c 'cd /home/ubuntu; ./%s_build.sh'\n" % vm_name)
            build_script = "%s%s" % (build_script, "sudo -H -u ubuntu bash -c 'cd /home/ubuntu; ./%s_run.sh'\n" % vm_name)
            instanceLst.append(self.create_instance(vm_name, build_script))

        waiter = self.ec2Client.get_waiter('instance_running')
        waiter.wait(InstanceIds=[inst['EC2'][0].id for inst in instanceLst])
        self.tags.append({'Key': 'VMName', 'Value': 'name'})
        for inst in instanceLst:
            for i in range(len(self.tags)):
                if self.tags[i]['Key'] == 'VMName':
                    self.tags[i]['Value'] = inst['VMName']
            inst['EC2'][0].create_tags(Tags=self.tags)
