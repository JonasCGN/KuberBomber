import boto3
import json
import urllib3

# Minimal implementation of cfnresponse
SUCCESS = "SUCCESS"
FAILED = "FAILED"

def send_response(event, context, response_status, response_data, physical_resource_id=None, no_echo=False):
    response_url = event['ResponseURL']

    response_body = {
        'Status': response_status,
        'Reason': f'See the details in CloudWatch Log Stream: {context.log_stream_name}',
        'PhysicalResourceId': physical_resource_id or context.log_stream_name,
        'StackId': event['StackId'],
        'RequestId': event['RequestId'],
        'LogicalResourceId': event['LogicalResourceId'],
        'NoEcho': no_echo,
        'Data': response_data
    }

    json_response_body = json.dumps(response_body)

    headers = {
        'content-type': '',
        'content-length': str(len(json_response_body))
    }

    http = urllib3.PoolManager()
    response = http.request('PUT', response_url, headers=headers, body=json_response_body)
    print("Status code:", response.status)

def lambda_handler(event, context):
    try:
        emr_cluster_id = event['ResourceProperties']['ClusterId']
        emr = boto3.client('emr')

        # Get instances in the cluster
        instances = emr.list_instances(ClusterId=emr_cluster_id, InstanceGroupTypes=['MASTER', 'CORE'])

        # Collect instance details
        instance_details = []
        ec2 = boto3.client('ec2')

        for instance in instances['Instances']:
            instance_id = instance['Ec2InstanceId']
            public_ip = instance.get('PublicIpAddress', 'No Public IP')

            # Get instance name from EC2 tags
            ec2_instance = ec2.describe_instances(InstanceIds=[instance_id])
            tags = ec2_instance['Reservations'][0]['Instances'][0].get('Tags', [])
            instance_name = 'No Name'
            for tag in tags:
                if tag['Key'] == 'Name':
                    instance_name = tag['Value']
                    break

            # Format the instance details
            instance_details.append(f"{instance_id};{instance_name};{public_ip}")

        # Join the instance details into a single string
        instance_details_str = '\n'.join(instance_details)

        # Send success response with instance details to CloudFormation
        send_response(event, context, SUCCESS, {'InstanceDetails': instance_details_str})

    except KeyError as e:
        print(f"Failed to retrieve instance details: {str(e)}")
        send_response(event, context, FAILED, {'Message': f"Key {str(e)} not found in event"})
    except Exception as e:
        print(f"Failed to retrieve instance details: {str(e)}")
        send_response(event, context, FAILED, {'Message': 'Failed to retrieve instance details'})