# AWS Orchestrator

This is an AWS orchestrator using boto3 and it mimics https://github.com/hdumcke/multipass-orchestrator

## Installation

Ssimply run:
```
pip install git+https://github.com/hdumcke/aws-orchestrator@main#egg=aws-orchestrator
```

Or, to install from source:


Clone this repo:

```
git clone --depth=1 https://github.com/hdumcke/aws-orchestrator
```


Then run:
```
pip install -r requirements.txt
python setup.py install
```

## Usage

Usage is really simple:

Write a yaml file describing the environment you want to deploy and deploy it with:

```
aws-deploy <config.yaml>
```

And when done:

```
aws-destroy <config.yaml>
```

### How it works

Configure boto3 https://boto3.amazonaws.com/v1/documentation/api/latest/guide/configuration.html
We assume you have configured a default region and your AWS credentials

In your yaml configuration file you provide a list of VM names and attributes for each of these virtual machines. The mandatory attributes are:

- **InstanceType**: The AWS instance tyoe
- **AMI_ID**: The AWS AMI image id

Please refer to the AWS documentation if you want to know more about these parameters and their values.

To customize the instance and run scripts use these optional parameters:

- **git_repos** A list of git repos that will be cloned in the instance. You can add a -b parameter to specify a branch
- **build_scripts** A list of paths to the build scripts in the above repos
- **run_scripts** A list of paths to scripts in the above repo that will be run after the build scripts

## Examples

```
git clone --depth=1 https://github.com/hdumcke/aws-orchestrator
cd aws-orchestrator/tests
aws-deploy simple.yaml
aws-wait simple.yaml
aws-list simple.yaml
ssh .... as shown by aws-list
exit # leave vm
aws-destroy simple.yaml
aws-deploy test-environment.yaml
aws-wait test-environment.yaml
aws-list test-environment.yaml
ssh -o "IdentitiesOnly=yes" -i id_rsa -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ubuntu@192.168.64.32 # use IP addess shown with aws-list
ls -la # see injected build and run script, see build and run log files
exit # leave vm
aws-destroy test-environment.yaml
```
